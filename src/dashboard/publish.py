"""Publish one historical snapshot, deduplicated by source and canonical URL."""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import html
import json
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup
import polars as pl

from config import DATA_DIR, EXTRACT_SOURCES
from filters.accident import classify_accident
from preprocessors.content_dedup import detect_duplicate_articles
from preprocessors.utils import dedup_normalize_article_url, dedup_make_article_key
from batch.run import run_batch
from events.locking import writer_lock


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        date = value
    else:
        value = " ".join(str(value).split())
        date = None
        for parse in (datetime.fromisoformat, parsedate_to_datetime,
                      lambda x: datetime.strptime(x, "%m/%d/%Y %I:%M:%S %p")):
            try:
                date = parse(value)
                break
            except (ValueError, TypeError):
                pass
        if date is None:
            return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone(timedelta(hours=7)))
    return date.astimezone(timezone.utc)


def plain(value, paragraph=False):
    soup = BeautifulSoup(html.unescape(value or ""), "html.parser")
    for tag in soup(["ul", "ol", "script", "style", "aside", "nav"]):
        tag.decompose()
    if paragraph:
        soup = soup.find("p") or soup
    return " ".join(soup.get_text(" ", strip=True).split())


def publish(data_root=DATA_DIR, artifacts_root=None):
    root = Path(data_root).resolve()
    archive = Path(artifacts_root).resolve() if artifacts_root else root.parent / "data_artifacts"
    archive.mkdir(parents=True, exist_ok=True)
    with writer_lock(archive / "dashboard_publication"):
        diagnostic_roots = (archive / "diagnostics", root / "diagnostics")
        diagnostic_inputs = [path for base in diagnostic_roots for path in sorted(base.glob("*/data"))]
        # The active data/ Silver files must win over archived diagnostics when
        # the same article has been extracted again with newer rules.
        inputs = [*diagnostic_inputs, root]
        # Same crawl filenames in copied runs refer to one snapshot, not new articles.
        files = {}
        for base in inputs:
            for path in (base / "bronze").glob("*/*.parquet"):
                identity = (path.parent.name, path.name)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if identity in files and files[identity][1] != digest:
                    raise ValueError(f"Conflicting Bronze snapshot: {identity}")
                files[identity] = (path, digest)
        rows = {}
        for (source, filename), (path, _) in sorted(files.items(), key=lambda item: (item[0][1], item[0][0])):
            for row in pl.read_parquet(path).iter_rows(named=True):
                url = dedup_normalize_article_url(row.get("link"))
                key = dedup_make_article_key(source, url)
                if not key:
                    raise ValueError(f"Missing article URL in {path}")
                decision = classify_accident(row.get("title"), row.get("description"))
                rows[key] = dict(article_key=key, source=source, title=plain(row.get("title")),
                                 description=plain(row.get("description"), True), link=url,
                                 pub_date=parse_date(row.get("pub_date")), accident_label=decision.label,
                                 filter_reason=decision.reason, filter_version=decision.version)
        if not rows:
            raise ValueError("No historical Bronze data; keeping existing dashboard snapshot")
        generation = archive / "dashboard_snapshots" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8])
        generation.mkdir(parents=True)
        catalog = pl.DataFrame(list(rows.values())).with_columns(pl.col("pub_date").cast(pl.Datetime("us", "UTC")))
        catalog = detect_duplicate_articles(catalog)
        rows = {row["article_key"]: row for row in catalog.iter_rows(named=True)}
        catalog.write_parquet(generation / "articles.parquet")
        # Reuse extracted history from all RSS sources, retaining the most recent
        # extraction for each identity, then apply the current scope before matching.
        paths = {}
        for source in EXTRACT_SOURCES:
            frames, seen = [], set()
            for base in inputs:
                path = base / "silver" / "accidents" / f"{source}.parquet"
                if path.exists():
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest not in seen:
                        frames.append(pl.read_parquet(path)); seen.add(digest)
            if not frames:
                raise FileNotFoundError(f"Missing extraction history for {source}")
            frame = pl.concat(frames, how="diagonal_relaxed").unique(subset=["article_key"], keep="last", maintain_order=True)
            allowed = [k for k, r in rows.items()
                       if r['source'] == source and r['accident_label'] == 'accident'
                       and not r['is_duplicate']]
            frame = frame.filter(pl.col("article_key").is_in(allowed))
            path = generation / "silver" / "accidents" / f"{source}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.write_parquet(path); paths[source] = path
        stats = run_batch(paths, generation / "gold" / "batch" / "canonical.duckdb")
        duplicate_articles = int(catalog.filter(pl.col("is_duplicate")).height)
        metadata = {"path": str(generation.relative_to(archive)), "articles": catalog.height,
                    "unique_articles": catalog.height - duplicate_articles,
                    "sources": catalog['source'].n_unique(), "date_min": str(catalog['pub_date'].min()),
                    "date_max": str(catalog['pub_date'].max()),
                    "duplicate_articles": duplicate_articles,
                    "batch": stats,
                    "coverage": "Article catalog, accident filtering, extraction, and event matching cover all seven RSS sources."}
        (generation / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary = archive / ("dashboard_current_" + uuid4().hex + ".json")
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(archive / "dashboard_current.json")
        return metadata


if __name__ == "__main__":
    print(json.dumps(publish(), ensure_ascii=False, indent=2))
