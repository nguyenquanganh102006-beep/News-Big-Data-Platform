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
from .retrieval import retrieve_candidates, utc_datetime
from .profile import clean, compare_profiles


EVENT_NAMESPACE = UUID("c456c993-f92c-45a2-8b93-6046b1b9d2b8")
ARTICLE_COLUMNS = ("article_key", "source", "url", "title", "description", "published_at",
                   "province", "district", "ward", "vehicles", "fatalities", "injuries",
                   "flags", "extraction_payload", "input_fingerprint")


def _article_values(article):
    values = dict(article, vehicles=json_text(article["vehicles"]),
                  flags=json_text(article["flags"]), extraction_payload=article["payload"])
    return [values.get(column) for column in ARTICLE_COLUMNS]

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
-- Updating indexed parent columns can trigger DuckDB's FK delete/insert
-- limitation. Keep province mutable; retrieval still uses the same SQL filter.
DROP INDEX IF EXISTS event_province_time;
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
CREATE TABLE IF NOT EXISTS article_updates (
    article_key VARCHAR PRIMARY KEY REFERENCES articles(article_key),
    field_timestamps JSON NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS article_revisions (
    revision_id VARCHAR PRIMARY KEY,
    article_key VARCHAR NOT NULL REFERENCES articles(article_key),
    previous_fingerprint VARCHAR NOT NULL, previous_payload JSON NOT NULL,
    replacement_fingerprint VARCHAR NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
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
        # Finish schema migration before importing data. In DuckDB, dropping an
        # old index and updating its referenced parent in the same transaction
        # can still invoke the old index's delete/insert constraint checks.
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute(DDL)
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def _rows(self, query, parameters=None):
        cursor = self.connection.execute(query, parameters or [])
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def read_articles(self):
        rows = self._rows("SELECT a.*, u.field_timestamps FROM articles a "
                          "LEFT JOIN article_updates u USING(article_key) ORDER BY article_key")
        for row in rows:
            row["vehicles"] = json.loads(row["vehicles"])
            row["flags"] = json.loads(row["flags"])
            payload = json.loads(row["extraction_payload"])
            body = payload.get("content") or payload.get("body") or ""
            row["text"] = clean(f'{row["title"]}. {row["description"]} {body}')
            row["field_timestamps"] = {
                field: utc_datetime(value) for field, value in json.loads(row["field_timestamps"] or "{}").items()
            }
        return {row["article_key"]: row for row in rows}

    def insert_article(self, article):
        self.connection.execute(
            f"INSERT INTO articles ({', '.join(ARTICLE_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in ARTICLE_COLUMNS)})", _article_values(article))

    def update_article(self, article, previous=None, only_unassigned=False):
        from uuid import uuid4
        from .aggregation import SUMMARY_FIELDS, has_field_conflict

        previous = previous if previous is not None else self.read_articles().get(article["article_key"])
        if previous is None:
            raise ValueError(f"Cannot update missing article: {article['article_key']}")
        now = self.connection.execute("SELECT current_timestamp").fetchone()[0]
        timestamps = dict(previous.get("field_timestamps") or {})
        for field in (*SUMMARY_FIELDS, "published_at", "url", "title", "description"):
            if not article.get(field) and article.get(field) != 0 and not has_field_conflict(article, field):
                # Missing information is not a correction. Retain the last known
                # value; the original Silver payload and old version remain auditable.
                article[field] = previous.get(field)
            if field in SUMMARY_FIELDS and (article.get(field) != previous.get(field)
                    or has_field_conflict(article, field) != has_field_conflict(previous, field)):
                timestamps[field] = now
        article["field_timestamps"] = timestamps
        payload = json.loads(article.get("payload") or article.get("extraction_payload") or "{}")
        body = payload.get("content") or payload.get("body") or ""
        article["text"] = clean(f'{article["title"]}. {article["description"]} {body}')
        # Never delete/reinsert the parent row: reviews reference this key.
        guard = (
            "AND NOT EXISTS (SELECT 1 FROM event_articles l WHERE l.article_key=articles.article_key) "
            "AND NOT EXISTS (SELECT 1 FROM accident_events e WHERE e.anchor_article_key=articles.article_key)"
            if only_unassigned else ""
        )
        updated = self.connection.execute(
            f"UPDATE articles SET {', '.join(column + '=?' for column in ARTICLE_COLUMNS[1:])} "
            f"WHERE article_key=? {guard}",
            _article_values(article)[1:] + [article["article_key"]],
        ).fetchone()[0]
        # Use the affected count: UPDATE RETURNING hits DuckDB's FK rewrite
        # limitation even when the referenced article_key is left unchanged.
        if updated != 1:
            raise ValueError(f"Cannot update missing or already assigned article: {article['article_key']}")
        self.connection.execute(
            "INSERT INTO article_revisions (revision_id,article_key,previous_fingerprint,previous_payload,"
            "replacement_fingerprint) VALUES (?, ?, ?, ?, ?)",
            [str(uuid4()), article["article_key"], previous["input_fingerprint"],
             previous.get("extraction_payload") or previous.get("payload"), article["input_fingerprint"]],
        )
        self.connection.execute(
            "INSERT INTO article_updates (article_key,field_timestamps) VALUES (?, ?) "
            "ON CONFLICT (article_key) DO UPDATE SET field_timestamps=excluded.field_timestamps, "
            "updated_at=now()",
            [article["article_key"], json_text(timestamps)],
        )

    def update_unassigned_article(self, article, previous=None):
        self.update_article(article, previous=previous, only_unassigned=True)

    def resolve_reviews(self, article_key):
        # Keep old reasons/payloads for audit, but stop presenting them as open.
        self.connection.execute(
            "UPDATE match_reviews SET status='resolved' WHERE article_key=? AND status='pending'",
            [article_key],
        )

    def find_candidates(self, article, config, articles):
        radius = timedelta(hours=config.followup_radius_hours)
        catalog = self.connection.execute(
            "SELECT event_id, province, anchor_published_at FROM accident_events "
            "WHERE province = ? AND anchor_published_at BETWEEN ? AND ? "
            "ORDER BY anchor_published_at, event_id",
            [article["province"], article["published_at"] - radius, article["published_at"] + radius],
        ).pl()
        # Keep the same 3.1 rules when moving from the fake catalog to DuckDB.
        result = retrieve_candidates(article, catalog, radius_hours=config.followup_radius_hours)
        candidates = []
        for row in result.candidates.iter_rows(named=True):
            identity = self.connection.execute(
                "SELECT anchor_article_key FROM accident_events WHERE event_id = ?", [row["event_id"]]
            ).fetchone()[0]
            keys = self.connection.execute(
                "SELECT article_key FROM event_articles WHERE event_id = ? ORDER BY article_key", [row["event_id"]]
            ).fetchall()
            members = [articles[key] for (key,) in keys]
            delta = abs((article["published_at"] - row["anchor_published_at"]).total_seconds()) / 3600
            evidence = compare_profiles(article, articles[identity])
            if delta > config.radius_hours and not (
                    evidence["same_incident_date"] and evidence["shared_places"]
                    and not evidence["conflicts"]):
                continue
            candidates.append({**row, "anchor_article_key": identity,
                               "text": articles[identity]["text"], "members": members,
                               "retrieval_route": "publication_window" if delta <= config.radius_hours else "dated_followup",
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
        province = self.connection.execute(
            "SELECT province FROM accident_events WHERE event_id=?", [event_id]
        ).fetchone()[0]
        summary = aggregate_members(members, fallback_province=province)
        self.connection.execute(
            "UPDATE accident_events SET first_published_at=coalesce(?,first_published_at), "
            "last_published_at=coalesce(?,last_published_at), province=coalesce(?,province), district=?, ward=?, "
            "location_full=?, vehicles_involved=?, total_fatalities=?, total_injuries=?, article_count=?, "
            "aggregation_evidence=?, review_reasons=?, aggregation_version=?, updated_at=current_timestamp "
            "WHERE event_id=?",
            [summary["first_published_at"], summary["last_published_at"], summary["province"], summary["district"], summary["ward"],
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
            "source_reference=excluded.source_reference, status=excluded.status",
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
                  "event_articles": "event_articles", "match_reviews": "match_reviews",
                  "article_revisions": "article_revisions"}
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
