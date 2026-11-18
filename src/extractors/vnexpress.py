"""Read VnExpress's article dateline during stage-2 information extraction."""

import re
import time
import unicodedata
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import requests

from config import (
    ArticleLocation, PROVINCE_ALIASES, VNEXPRESS_LOCATION_SELECTOR,
    VNEXPRESS_FETCH_TIMEOUT, VNEXPRESS_MAX_HTML_BYTES, VNEXPRESS_REQUEST_DELAY,
)


def _token(text):
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


_ALIASES = {_token(alias): province for province, aliases in PROVINCE_ALIASES.items()
            for alias in (province, *aliases)}


def parse_vnexpress_location(html, url=None) -> ArticleLocation:
    """Use the dedicated lead dateline, never arbitrary province mentions."""
    soup = BeautifulSoup(html, "html.parser")
    labels = sorted({node.get_text(" ", strip=True)
                     for node in soup.select(VNEXPRESS_LOCATION_SELECTOR)
                     if node.get_text(" ", strip=True)})
    if not labels:
        return ArticleLocation("missing", url=url)
    provinces = set()
    for label in labels:
        normalized = _token(label)
        # VnExpress can write 'TP Huế' whereas the vocabulary contains 'Huế'.
        name = _ALIASES.get(normalized)
        if name is None:
            normalized = re.sub(r"^(?:tp\.?|thành phố|tỉnh)\s+", "", normalized)
            name = _ALIASES.get(normalized)
        if name is None:
            return ArticleLocation("unknown", text=" | ".join(labels), url=url)
        provinces.add(name)
    if len(provinces) != 1:
        return ArticleLocation("ambiguous", text=" | ".join(labels), url=url)
    return ArticleLocation("ok", province=next(iter(provinces)), text=" | ".join(labels), url=url)


def _valid_url(url):
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname in {"vnexpress.net", "www.vnexpress.net"}
                and parts.username is None and parts.password is None and parts.port in (None, 443))
    except ValueError:
        return False


def fetch_vnexpress_location(url, session) -> ArticleLocation:
    """Fetch bounded HTML; bad URLs, HTTP errors and timeouts are auditable."""
    if not _valid_url(url):
        return ArticleLocation("invalid_url", url=url if isinstance(url, str) else None)
    current = url
    try:
        for _ in range(4):
            response = session.get(
                current, timeout=VNEXPRESS_FETCH_TIMEOUT, allow_redirects=False, stream=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBigDataPlatform/0.1)"},
            )
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    target = urljoin(current, response.headers.get("Location", ""))
                    if not response.headers.get("Location") or not _valid_url(target):
                        return ArticleLocation("invalid_redirect", url=current)
                    current = target
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > VNEXPRESS_MAX_HTML_BYTES:
                        return ArticleLocation("too_large", url=current)
                    chunks.append(chunk)
                return parse_vnexpress_location(b"".join(chunks), url=current)
            finally:
                response.close()
        return ArticleLocation("too_many_redirects", url=current)
    except requests.RequestException:
        return ArticleLocation("fetch_error", url=current)


def fetch_vnexpress_locations(frame) -> list[ArticleLocation]:
    if "link" not in frame.columns:
        raise ValueError("VnExpress extraction input must contain link")
    results, cache = [], {}
    with requests.Session() as session:
        for url in frame["link"].to_list():
            if url not in cache:
                if cache:
                    time.sleep(VNEXPRESS_REQUEST_DELAY)
                cache[url] = fetch_vnexpress_location(url, session)
            results.append(cache[url])
    return results
