from dataclasses import dataclass
import os

from .main import DATA_SILVER_DIR
from .crawlers import RSS_SOURCES

FILTERED_DATA_DIR = os.path.join(DATA_SILVER_DIR, "filtered")
DEDUPLICATED_DATA_DIR = os.path.join(DATA_SILVER_DIR, "deduplicated")
FILTER_SOURCES = tuple(RSS_SOURCES)


VERSION = "rules-v3-road"
FILTER_LABELS = ("accident", "not_accident", "uncertain")
DUPLICATE_SIMILARITY_THRESHOLD = 0.85
DUPLICATE_WINDOW_HOURS = 24
DUPLICATE_ALGORITHM_VERSION = "tfidf-charwb-3to5-v1"


@dataclass(frozen=True)
class Decision:
    label: str
    reason: str
    evidence: str
    version: str = VERSION
