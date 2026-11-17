"""Fetch article bodies only for RSS leads that may describe road accidents."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import polars as pl
import requests


ALLOWED_HOSTS = {
    "vnexpress": {"vnexpress.net", "www.vnexpress.net"},
    "vietnamplus": {"vietnamplus.vn", "www.vietnamplus.vn"},
    "tuoitre": {"tuoitre.vn", "www.tuoitre.vn"},
    "dantri": {"dantri.com.vn", "www.dantri.com.vn"},
    "thanhnien": {"thanhnien.vn", "www.thanhnien.vn"},
    "baoxaydung": {"baoxaydung.vn", "www.baoxaydung.vn"},
    "tienphong": {"tienphong.vn", "www.tienphong.vn"},
}

BODY_SELECTORS = {
    "vnexpress": (".fck_detail", ".article-content"),
    "vietnamplus": (".article__body", ".article-body", ".cms-body", ".story__body"),
    "tuoitre": ("#main-detail-body", ".detail-content", ".content-detail"),
    "dantri": ("#articleContent", ".singular-content", ".dt-news__content", ".e-magazine__body"),
    "thanhnien": (".detail-content", ".article__body", ".cms-body"),
    "baoxaydung": (".detail-content", ".content-detail", ".article__body"),
    "tienphong": (".article__body", ".article-body", ".content-detail"),
}

MAX_HTML_BYTES = 2_000_000
MAX_BODY_CHARS = 40_000
FETCH_TIMEOUT = (5, 10)
REQUEST_DELAY = 0.2
MISSING_BODY_RETRY_AFTER = timedelta(days=1)


def valid_article_url(url: str | None, source: str) -> bool:
    if source not in ALLOWED_HOSTS or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname in ALLOWED_HOSTS[source]
                and parts.username is None and parts.password is None
                and parts.port in (None, 443))
    except ValueError:
        return False


def _plain_text(value: str) -> str:
    return " ".join(BeautifulSoup(value, "html.parser").get_text(" ", strip=True).split())


def _json_body(value, expected_url: str | None):
    if isinstance(value, list):
        for item in value:
            found = _json_body(item, expected_url)
            if found:
                return found
    if isinstance(value, dict):
        reference = value.get("mainEntityOfPage") or value.get("url")
        if isinstance(reference, dict):
            reference = reference.get("@id") or reference.get("url")
        if expected_url and isinstance(reference, str) and reference.startswith("https://"):
            expected = urlsplit(expected_url)
            actual = urlsplit(reference)
            if (expected.hostname, expected.path) != (actual.hostname, actual.path):
                return None
        body = value.get("articleBody")
        if isinstance(body, str) and len(_plain_text(body)) >= 100:
            return _plain_text(body)[:MAX_BODY_CHARS]
        for key in ("@graph", "mainEntity"):
            found = _json_body(value.get(key), expected_url)
            if found:
                return found
    return None


def parse_article_body(html: bytes | str, source: str, expected_url: str | None = None) -> str | None:
    """Use a real article container; never treat the whole page as body text."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            body = _json_body(json.loads(script.string or script.get_text()), expected_url)
        except (ValueError, TypeError):
            continue
        if body:
            return body

    selectors = BODY_SELECTORS.get(source, ())
    for selector in selectors:
        for node in soup.select(selector):
            # Work on a copy so a later selector can inspect the original DOM.
            fragment = BeautifulSoup(str(node), "html.parser")
            for unwanted in fragment.select(
                "script, style, nav, aside, footer, form, figure, .related, .related-news, "
                ".box-related, .advertisement, .ads, .social"
            ):
                unwanted.decompose()
            paragraphs = [" ".join(p.get_text(" ", strip=True).split())
                          for p in fragment.select("p")]
            paragraphs = [p for p in paragraphs if p]
            body = "\n".join(paragraphs)
            if len(body) >= 100:
                return body[:MAX_BODY_CHARS]
    return None


def fetch_article_body(url: str | None, source: str, session: requests.Session):
    """Return (body, status, final_url), with bounded same-site redirects."""
    if not valid_article_url(url, source):
        return None, "invalid_url", url
    current = url
    try:
        for _ in range(4):
            response = session.get(
                current, timeout=FETCH_TIMEOUT, allow_redirects=False, stream=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBigDataPlatform/0.1)"},
            )
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    target = urljoin(current, location) if location else ""
                    if not valid_article_url(target, source):
                        return None, "invalid_redirect", current
                    current = target
                    continue
                if response.status_code != 200:
                    return None, "http_error", current
                if "html" not in response.headers.get("Content-Type", "").lower():
                    return None, "not_html", current
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > MAX_HTML_BYTES:
                        return None, "too_large", current
                    chunks.append(chunk)
                body = parse_article_body(b"".join(chunks), source, current)
                return body, "ok" if body else "body_missing", current
            finally:
                response.close()
        return None, "too_many_redirects", current
    except requests.RequestException:
        return None, "fetch_error", current


def enrich_candidate_bodies(frame: pl.DataFrame, cache_path: Path) -> pl.DataFrame:
    """Fill missing bodies for likely accidents; keep failed fetches auditable."""
    if "link" not in frame.columns or "source" not in frame.columns:
        return frame
    bodies = frame["content"].to_list() if "content" in frame.columns else [None] * frame.height
    statuses = ["existing" if isinstance(body, str) and body.strip() else "skipped"
                for body in bodies]
    urls = [None] * frame.height
    cache = {}
    if cache_path.is_file():
        cached = pl.read_parquet(cache_path)
        cache = {row["link"]: (row["content"], row.get("status") or "ok", row.get("checked_at"))
                 for row in cached.iter_rows(named=True)}

    cache_changed = False
    last_request = None
    with requests.Session() as session:
        for index, row in enumerate(frame.iter_rows(named=True)):
            if statuses[index] == "existing" or row["accident_label"] not in ("accident", "uncertain"):
                continue
            link, source = row.get("link"), row.get("source")
            if not valid_article_url(link, source):
                statuses[index] = "invalid_url"
                continue
            if link in cache:
                cached_body, cached_status, checked_at = cache[link]
                if cached_body:
                    bodies[index], statuses[index], urls[index] = cached_body, "cached", link
                    continue
                if cached_status == "body_missing" and checked_at is not None:
                    checked = datetime.fromisoformat(checked_at)
                    if datetime.now(timezone.utc) - checked < MISSING_BODY_RETRY_AFTER:
                        statuses[index], urls[index] = "cached_missing", link
                        continue
            if last_request is not None:
                time.sleep(max(0, REQUEST_DELAY - (time.monotonic() - last_request)))
            body, status, final_url = fetch_article_body(link, source, session)
            last_request = time.monotonic()
            statuses[index], urls[index] = status, final_url
            if body:
                bodies[index] = body
            if body or status == "body_missing":
                cache[link] = (body, status, datetime.now(timezone.utc).isoformat())
                cache_changed = True

    if cache_changed:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=cache_path.parent, suffix=".parquet", delete=False) as tmp:
            temporary = Path(tmp.name)
        try:
            pl.DataFrame({
                "link": list(cache),
                "content": [entry[0] for entry in cache.values()],
                "status": [entry[1] for entry in cache.values()],
                "checked_at": [entry[2] for entry in cache.values()],
            }).write_parquet(temporary)
            temporary.replace(cache_path)
        finally:
            temporary.unlink(missing_ok=True)
    result = frame.with_columns(
        pl.Series("content", bodies, dtype=pl.String),
        pl.Series("body_fetch_status", statuses, dtype=pl.String),
        pl.Series("body_fetch_url", urls, dtype=pl.String),
    )
    return result
