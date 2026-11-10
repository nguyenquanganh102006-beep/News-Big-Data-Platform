"""Configuration and result contract for candidate event retrieval (task 3.1)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl

from .main import DATA_GOLD_DIR
from .extractors import EXTRACT_OUTPUT_DIR


# A 48-hour radius means a 96-hour-wide window, including both endpoints.
RETRIEVAL_RADIUS_HOURS = 48
RETRIEVAL_EVENT_COLUMNS = ("event_id", "province", "anchor_published_at")
EVENT_INPUT_DIR = Path(EXTRACT_OUTPUT_DIR)
EVENT_DATABASE_PATH = Path(DATA_GOLD_DIR) / "events" / "accident_events.duckdb"
EVENT_EXPORT_DIR = EVENT_DATABASE_PATH.parent / "exports"
MATCH_VERSION = "hybrid-evidence-v2"
AGGREGATION_VERSION = "latest-field-v1"
MATCH_WEIGHTS = {"text": 0.35, "location": 0.20, "identity": 0.25, "vehicles": 0.10, "time": 0.10}


@dataclass(frozen=True)
class MatchConfig:
    radius_hours: float = RETRIEVAL_RADIUS_HOURS
    threshold: float = 0.75
    review_threshold: float = 0.60
    min_margin: float = 0.10
    min_coverage: float = 0.70
    min_text_score: float = 0.60
    min_evidence_text_score: float = 0.25
    semantic_model: str | None = None
    semantic_cache_dir: str | None = None
    followup_radius_hours: float = 168

    def __post_init__(self):
        import math

        if (isinstance(self.radius_hours, bool) or not isinstance(self.radius_hours, (int, float))
                or not math.isfinite(self.radius_hours) or self.radius_hours <= 0):
            raise ValueError("radius_hours must be finite and positive")
        if (isinstance(self.followup_radius_hours, bool) or not isinstance(self.followup_radius_hours, (int, float))
                or not math.isfinite(self.followup_radius_hours) or self.followup_radius_hours < self.radius_hours):
            raise ValueError("followup_radius_hours must be finite and at least radius_hours")
        for name in ("threshold", "review_threshold", "min_margin", "min_coverage", "min_text_score", "min_evidence_text_score"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"{name} must be between 0 and 1")
        if self.review_threshold > self.threshold:
            raise ValueError("review_threshold must not exceed threshold")
        for name in ("semantic_model", "semantic_cache_dir"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty text or None")


@dataclass(frozen=True)
class RetrievalResult:
    article_key: str | None
    status: Literal["ok", "needs_review"]
    candidates: pl.DataFrame
    reasons: tuple[str, ...] = ()
