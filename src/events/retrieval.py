"""Find candidate events in memory without a crawler or event database."""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import math
import unicodedata

import polars as pl

from config import (
    PROVINCE_ALIASES,
    RETRIEVAL_EVENT_COLUMNS,
    RETRIEVAL_RADIUS_HOURS,
    RetrievalResult,
)


def _province_token(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


# Reuse extraction vocabulary; do not infer administrative boundary changes.
_PROVINCE_LOOKUP = {
    _province_token(alias): canonical
    for canonical, aliases in PROVINCE_ALIASES.items()
    for alias in (canonical, *aliases)
}


def _normalize_province(value: object) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("missing")
    if not isinstance(value, str):
        raise ValueError("invalid")
    canonical = _PROVINCE_LOOKUP.get(_province_token(value))
    if canonical is None:
        raise ValueError("unknown")
    return canonical


def _utc_datetime(value: object) -> datetime:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("missing")
    if isinstance(value, str):
        value = value.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("invalid") from None
    if not isinstance(value, datetime):
        raise ValueError("invalid")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_required")
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("invalid") from None


def _retrieval_radius(hours: float) -> timedelta:
    if isinstance(hours, bool) or not isinstance(hours, (int, float)):
        raise ValueError("radius_hours must be a finite positive number")
    try:
        if not math.isfinite(hours) or hours <= 0:
            raise ValueError
        radius = timedelta(hours=hours)
        if radius <= timedelta(0):
            raise ValueError
    except (ValueError, OverflowError):
        raise ValueError("radius_hours must be a finite positive, representable duration") from None
    return radius


def retrieve_candidates(
    article: Mapping[str, object],
    events: pl.DataFrame,
    radius_hours: float = RETRIEVAL_RADIUS_HOURS,
) -> RetrievalResult:
    """Return same-province events within an inclusive publication-time radius.

    Article fields: article_key, province, published_at. Event columns: event_id,
    province, anchor_published_at. Times accept aware datetime or ISO 8601 text
    with an explicit offset. Comparison uses UTC; returned rows preserve the
    original event schema/values and sort by UTC anchor time, then event_id.

    Incomplete/invalid articles return needs_review. Invalid configuration or
    event catalog raises ValueError rather than silently hiding candidates.
    Inputs are never modified and no storage or network access is performed.
    """
    radius = _retrieval_radius(radius_hours)
    missing_columns = set(RETRIEVAL_EVENT_COLUMNS) - set(events.columns)
    if missing_columns:
        raise ValueError(f"Event catalog missing columns: {', '.join(sorted(missing_columns))}")

    reasons = []
    article_key = article.get("article_key")
    if not isinstance(article_key, str) or not article_key.strip():
        article_key = None
        reasons.append("article_key_missing_or_invalid")
    try:
        province = _normalize_province(article.get("province"))
    except ValueError as error:
        reasons.append(f"province_{error}")
    try:
        published_at = _utc_datetime(article.get("published_at"))
    except ValueError as error:
        reasons.append(f"published_at_{error}")
    if reasons:
        return RetrievalResult(article_key, "needs_review", events.head(0), tuple(reasons))

    seen_ids = set()
    matches = []
    for index, row in enumerate(events.iter_rows(named=True)):
        event_id = row["event_id"]
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"Event row {index}: event_id must be a non-empty string")
        if event_id in seen_ids:
            raise ValueError(f"Event catalog contains duplicate event_id: {event_id}")
        seen_ids.add(event_id)
        try:
            event_province = _normalize_province(row["province"])
            anchor = _utc_datetime(row["anchor_published_at"])
        except ValueError as error:
            raise ValueError(f"Event {event_id}: invalid province/anchor_published_at ({error})") from None
        if event_province == province and abs(anchor - published_at) <= radius:
            matches.append((anchor, event_id, row))

    matches.sort(key=lambda match: (match[0], match[1]))
    candidates = (
        pl.DataFrame([row for _, _, row in matches], schema=events.schema)
        if matches else events.head(0)
    )
    return RetrievalResult(article_key, "ok", candidates)
