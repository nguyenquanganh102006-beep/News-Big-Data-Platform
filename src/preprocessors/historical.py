"""Adapt historical HTML Bronze to the accumulated RSS-compatible Silver."""
import polars as pl
from bs4 import BeautifulSoup

from config import RSS_SOURCES
from .rss_generic import parse_rss_date
from .utils import dedup_add_article_identity, dedup_update_silver_history


def preprocess_historical_files(source, paths):
    rows = []
    for path in paths:
        for row in pl.read_parquet(path).iter_rows(named=True):
            if row.get("source", source) != source:
                raise ValueError(f"Unexpected source in {path}")
            date = parse_rss_date(row.get("pub_date"))
            if date is None:
                raise ValueError(f"Invalid historical publication date in {path}")
            rows.append({
                "title": BeautifulSoup(row.get("title") or "", "html.parser").get_text(" ", strip=True),
                "description": BeautifulSoup(row.get("description") or "", "html.parser").get_text(" ", strip=True),
                "content": row.get("content") or "",
                "link": row.get("link"), "pub_date": date,
            })
    if not rows:
        return
    frame = pl.DataFrame(rows).with_columns(pl.col("pub_date").cast(pl.Datetime("us", "UTC")))
    frame = dedup_add_article_identity(frame, source)
    new = dedup_update_silver_history(frame, RSS_SOURCES[source]["silver_save_path"], source)
    print(f"[Historical Silver] source={source} input={frame.height} new={new.height}", flush=True)
