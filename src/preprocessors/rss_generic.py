"""Shared Silver normalization for RSS sources without a custom parser."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import re

import polars as pl

from config import DEBUG, RSS_SOURCES, latest_bronze_path
from .utils import dedup_add_article_identity, dedup_update_silver_history


VN_TZ = timezone(timedelta(hours=7))


def parse_email_date(value):
    # A few RSS feeds emit a truncated numeric zone (for example, +07).
    normalized = re.sub(r"([+-]\d{2})$", r"\g<1>00", value)
    return parsedate_to_datetime(normalized)


def parse_rss_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        parsed = None
        for parser in (
            lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
            parse_email_date,
            lambda item: datetime.strptime(item, "%m/%d/%Y %I:%M:%S %p"),
        ):
            try:
                parsed = parser(text)
                break
            except (TypeError, ValueError, OverflowError):
                continue
        if parsed is None:
            if DEBUG:
                print(f"[Preprocess] unrecognized RSS date: {text!r}")
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VN_TZ)
    return parsed.astimezone(timezone.utc)


def preprocess_rss_source(source: str, save_file=True, crawled_date: str | None = None,
                          bronze_path=None) -> pl.DataFrame:
    if source not in RSS_SOURCES:
        raise ValueError(f"Unknown RSS source: {source}")
    raw_path = Path(bronze_path) if bronze_path is not None else latest_bronze_path(source, crawled_date)
    if not raw_path.is_file():
        raise FileNotFoundError(f"Missing Bronze snapshot for {source}: {raw_path}")
    frame = pl.read_parquet(raw_path)
    required = {"title", "description", "pub_date", "link"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{raw_path}: missing RSS columns: {', '.join(sorted(missing))}")
    dates = [parse_rss_date(value) for value in frame["pub_date"].to_list()]
    frame = frame.with_columns(pl.Series("pub_date", dates, dtype=pl.Datetime("us", "UTC")))
    frame = dedup_add_article_identity(frame, source)
    new = dedup_update_silver_history(
        frame, RSS_SOURCES[source]["silver_save_path"], source, save_file=save_file,
    )
    if DEBUG:
        print(f"[Preprocess] source={source}, input={frame.height}, new={new.height}")
    return new
