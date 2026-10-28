from dataclasses import dataclass
import os

from .main import DATA_DIR

FILTERED_DATA_DIR = os.path.join(DATA_DIR, "filtered")
FILTER_SOURCES = ("vnexpress", "vietnamplus", "tuoitre")


VERSION = "rules-v1"
FILTER_LABELS = ("accident", "not_accident", "uncertain")


@dataclass(frozen=True)
class Decision:
    label: str
    reason: str
    evidence: str
    version: str = VERSION
