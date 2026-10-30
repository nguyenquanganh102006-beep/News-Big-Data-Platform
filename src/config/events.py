"""Configuration and result contract for candidate event retrieval (task 3.1)."""

from dataclasses import dataclass
from typing import Literal

import polars as pl


# A 24-hour radius means a 48-hour-wide window, including both endpoints.
RETRIEVAL_RADIUS_HOURS = 24
RETRIEVAL_EVENT_COLUMNS = ("event_id", "province", "anchor_published_at")


@dataclass(frozen=True)
class RetrievalResult:
    article_key: str | None
    status: Literal["ok", "needs_review"]
    candidates: pl.DataFrame
    reasons: tuple[str, ...] = ()
