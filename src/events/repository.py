"""DuckDB persistence. The runner owns the transaction for each import."""

from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid5

import duckdb

from config import AGGREGATION_VERSION, MATCH_VERSION
from .adapter import fingerprint, json_text
from .aggregation import aggregate_members
from .retrieval import retrieve_candidates


EVENT_NAMESPACE = UUID("c456c993-f92c-45a2-8b93-6046b1b9d2b8")

DDL = """
CREATE TABLE IF NOT EXISTS event_schema (version INTEGER PRIMARY KEY CHECK (version = 1));
INSERT INTO event_schema VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS articles (
    article_key VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, url VARCHAR,
    title VARCHAR NOT NULL, description VARCHAR NOT NULL, published_at TIMESTAMPTZ,
    province VARCHAR, district VARCHAR, ward VARCHAR, vehicles JSON NOT NULL,
    fatalities BIGINT CHECK (fatalities >= 0), injuries BIGINT CHECK (injuries >= 0),
    flags JSON NOT NULL, extraction_payload JSON NOT NULL, input_fingerprint VARCHAR NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS accident_events (
    event_id VARCHAR PRIMARY KEY,
    anchor_article_key VARCHAR NOT NULL UNIQUE REFERENCES articles(article_key),
    province VARCHAR NOT NULL, anchor_published_at TIMESTAMPTZ NOT NULL,
    first_published_at TIMESTAMPTZ NOT NULL, last_published_at TIMESTAMPTZ NOT NULL,
    time_occurred TIMESTAMPTZ, district VARCHAR, ward VARCHAR, location_full VARCHAR,
    vehicles_involved JSON NOT NULL,
    total_fatalities BIGINT CHECK (total_fatalities >= 0),
    total_injuries BIGINT CHECK (total_injuries >= 0),
    article_count BIGINT NOT NULL CHECK (article_count >= 1),
    aggregation_evidence JSON NOT NULL, review_reasons JSON NOT NULL,
    aggregation_version VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE INDEX IF NOT EXISTS event_province_time ON accident_events(province, anchor_published_at);
CREATE TABLE IF NOT EXISTS event_articles (
    article_key VARCHAR PRIMARY KEY REFERENCES articles(article_key),
    event_id VARCHAR NOT NULL REFERENCES accident_events(event_id),
    decision VARCHAR NOT NULL CHECK (decision IN ('new_event', 'matched')),
    match_score DOUBLE CHECK (match_score BETWEEN 0 AND 1), score_details JSON NOT NULL,
    match_version VARCHAR NOT NULL, config_fingerprint VARCHAR NOT NULL,
    model_fingerprint VARCHAR NOT NULL, assigned_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS match_reviews (
    review_id VARCHAR PRIMARY KEY, article_key VARCHAR REFERENCES articles(article_key),
    source_reference VARCHAR NOT NULL, input_fingerprint VARCHAR NOT NULL,
    reasons JSON NOT NULL, decision_details JSON NOT NULL, input_payload JSON NOT NULL,
    match_version VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'resolved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS event_runs (
    run_id VARCHAR PRIMARY KEY, summary JSON NOT NULL, config JSON NOT NULL,
    model_fingerprint VARCHAR NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE OR REPLACE VIEW accident_event_summary AS
SELECT e.*, (SELECT list(DISTINCT a.url ORDER BY a.url)
             FROM event_articles l JOIN articles a USING(article_key)
             WHERE l.event_id = e.event_id) AS list_article_urls
FROM accident_events e;
CREATE OR REPLACE VIEW article_event_summary AS
SELECT a.*, l.event_id, l.decision, l.match_score
FROM articles a LEFT JOIN event_articles l USING(article_key);
"""


class EventRepository:
    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(str(path))
        self.connection.execute("SET TimeZone='UTC'")

    def close(self):
        self.connection.close()

    def initialize(self):
        self.connection.execute(DDL)

    def _rows(self, query, parameters=None):
        cursor = self.connection.execute(query, parameters or [])
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def read_articles(self):
        rows = self._rows("SELECT * FROM articles ORDER BY article_key")
        for row in rows:
            row["vehicles"] = json.loads(row["vehicles"])
            row["flags"] = json.loads(row["flags"])
            row["text"] = f'{row["title"]}. {row["description"]}'.strip()
        return {row["article_key"]: row for row in rows}

    def insert_article(self, article):
        columns = ("article_key", "source", "url", "title", "description", "published_at",
                   "province", "district", "ward", "vehicles", "fatalities", "injuries",
                   "flags", "extraction_payload", "input_fingerprint")
        values = [article.get(c) for c in columns]
        values[9] = json_text(article["vehicles"])
        values[12] = json_text(article["flags"])
        values[13] = article["payload"]
        self.connection.execute(
            f"INSERT INTO articles ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", values)

    def find_candidates(self, article, config, articles):
        radius = timedelta(hours=config.radius_hours)
        catalog = self.connection.execute(
            "SELECT event_id, province, anchor_published_at FROM accident_events "
            "WHERE province = ? AND anchor_published_at BETWEEN ? AND ? "
            "ORDER BY anchor_published_at, event_id",
            [article["province"], article["published_at"] - radius, article["published_at"] + radius],
        ).pl()
        # Keep the same 3.1 rules when moving from the fake catalog to DuckDB.
        result = retrieve_candidates(article, catalog, radius_hours=config.radius_hours)
        candidates = []
        for row in result.candidates.iter_rows(named=True):
            identity = self.connection.execute(
                "SELECT anchor_article_key FROM accident_events WHERE event_id = ?", [row["event_id"]]
            ).fetchone()[0]
            keys = self.connection.execute(
                "SELECT article_key FROM event_articles WHERE event_id = ? ORDER BY article_key", [row["event_id"]]
            ).fetchall()
            members = [articles[key] for (key,) in keys]
            candidates.append({**row, "text": articles[identity]["text"], "members": members,
                               "vehicles": sorted({v for member in members for v in member["vehicles"]})})
        return candidates

    def save_assignment(self, article, decision, config_fingerprint, model_fingerprint):
        key = article["article_key"]
        if decision["decision"] == "new_event":
            event_id = str(uuid5(EVENT_NAMESPACE, key))
            self.connection.execute(
                "INSERT INTO accident_events (event_id, anchor_article_key, province, anchor_published_at, "
                "first_published_at, last_published_at, vehicles_involved, article_count, "
                "aggregation_evidence, review_reasons, aggregation_version) "
                "VALUES (?, ?, ?, ?, ?, ?, '[]', 1, '{}', '[]', ?)",
                [event_id, key, article["province"], article["published_at"], article["published_at"],
                 article["published_at"], AGGREGATION_VERSION],
            )
        else:
            event_id = decision["event_id"]
        self.connection.execute(
            "INSERT INTO event_articles (article_key, event_id, decision, match_score, score_details, "
            "match_version, config_fingerprint, model_fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [key, event_id, decision["decision"], decision.get("score"), json_text(decision),
             MATCH_VERSION, config_fingerprint, model_fingerprint],
        )
        return event_id

    def refresh_event(self, event_id, articles):
        keys = self.connection.execute(
            "SELECT article_key FROM event_articles WHERE event_id = ? ORDER BY article_key", [event_id]
        ).fetchall()
        members = [articles[key] for (key,) in keys]
        summary = aggregate_members(members)
        self.connection.execute(
            "UPDATE accident_events SET first_published_at=?, last_published_at=?, district=?, ward=?, "
            "location_full=?, vehicles_involved=?, total_fatalities=?, total_injuries=?, article_count=?, "
            "aggregation_evidence=?, review_reasons=?, aggregation_version=?, updated_at=current_timestamp "
            "WHERE event_id=?",
            [summary["first_published_at"], summary["last_published_at"], summary["district"], summary["ward"],
             summary["location_full"], json_text(summary["vehicles"]), summary["fatalities"], summary["injuries"],
             len(members), json_text(summary["evidence"]), json_text(summary["reasons"]),
             AGGREGATION_VERSION, event_id],
        )

    def save_review(self, article, decision):
        # Missing upstream keys retain their original payload without inventing an article ID.
        review_id = fingerprint({"key": article["article_key"], "input": article["input_fingerprint"],
                                 "reasons": decision["reasons"], "version": MATCH_VERSION})
        self.connection.execute(
            "INSERT INTO match_reviews (review_id, article_key, source_reference, input_fingerprint, reasons, "
            "decision_details, input_payload, match_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (review_id) DO UPDATE SET decision_details=excluded.decision_details, "
            "source_reference=excluded.source_reference",
            [review_id, article["article_key"], article["reference"], article["input_fingerprint"],
             json_text(decision["reasons"]), json_text(decision), article["payload"], MATCH_VERSION],
        )

    def counts(self):
        counts = {name: self.connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                  for name in ("articles", "accident_events", "event_articles", "match_reviews")}
        counts["unassigned_articles"] = self.connection.execute(
            "SELECT count(*) FROM articles a WHERE NOT EXISTS "
            "(SELECT 1 FROM event_articles l WHERE l.article_key=a.article_key)"
        ).fetchone()[0]
        counts["pending_reviews"] = self.connection.execute(
            "SELECT count(*) FROM match_reviews WHERE status='pending'"
        ).fetchone()[0]
        return counts

    def export(self, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        tables = {"accident_events": "accident_event_summary", "articles": "article_event_summary",
                  "event_articles": "event_articles", "match_reviews": "match_reviews"}
        # Each file is replaced only after a complete write. DuckDB remains the
        # source of truth if export is interrupted; rerunning regenerates files.
        with TemporaryDirectory(dir=output_dir) as tmp:
            for filename, table in tables.items():
                path = Path(tmp, f"{filename}.parquet")
                self.connection.table(table).write_parquet(str(path))
                path.replace(output_dir / path.name)
            manifest = Path(tmp, "manifest.json")
            manifest.write_text(json_text(self.counts()) + "\n")
            manifest.replace(output_dir / manifest.name)
