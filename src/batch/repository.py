"""Reuse Phase 3 persistence with fixed canonical SQL identifiers."""
import re

from events.repository import EventRepository

TABLES = {name: "canonical_" + name for name in (
    "event_schema", "articles", "event_articles", "match_reviews", "event_runs",
    "article_updates", "article_revisions", "accident_event_summary",
    "article_event_summary", "event_province_time")}
TABLES["accident_events"] = "canonical_events"
PATTERN = re.compile(r"\b(" + "|".join(TABLES) + r")\b")


class CanonicalConnection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, *args):
        return self.raw.execute(PATTERN.sub(lambda m: TABLES[m.group()], sql), *args)

    def close(self):
        self.raw.close()


class CanonicalRepository(EventRepository):
    def __init__(self, path):
        super().__init__(path)
        self.connection = CanonicalConnection(self.connection)
