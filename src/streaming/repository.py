"""Reuse the Phase 3 repository against isolated provisional table names.

Only fixed SQL identifiers are translated; payloads remain bound parameters.
No Phase 3 tables, migrations or matching algorithms are modified.
"""
import re
from events.repository import EventRepository

TABLES = {
    name: "provisional_" + name for name in (
        "event_schema", "articles", "event_articles", "match_reviews", "event_runs",
        "article_updates", "article_revisions", "accident_event_summary", "article_event_summary",
        "event_province_time",
    )
}
TABLES["accident_events"] = "provisional_events"
PATTERN = re.compile(r"\b(" + "|".join(TABLES) + r")\b")


class ProvisionalConnection:
    def __init__(self, connection):
        self.raw = connection

    def execute(self, sql, *args):
        return self.raw.execute(PATTERN.sub(lambda m: TABLES[m.group()], sql), *args)

    def close(self):
        self.raw.close()


class ProvisionalRepository(EventRepository):
    def __init__(self, path):
        super().__init__(path)
        self.connection = ProvisionalConnection(self.connection)

    def initialize(self):
        super().initialize()
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS stream_receipts (
                article_key VARCHAR PRIMARY KEY, status VARCHAR NOT NULL,
                raw_payload JSON NOT NULL, event_id VARCHAR,
                processed_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
            )
        """)
