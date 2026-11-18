"""One durable DuckDB journal. Kafka positions and raw revisions commit together."""
import hashlib
import json
import re
from pathlib import Path

import duckdb
import polars as pl

from streaming.message import normalize_article
from streaming.pipeline import clean_article
from events.adapter import json_text
from preprocessors.rss_generic import parse_rss_date


CORE = ("source", "title", "description", "content", "link", "pub_date")


def signature(row):
    return hashlib.sha256(json_text({key: row.get(key) or "" for key in CORE}).encode()).hexdigest()


def observed_at(raw, envelope):
    value = raw.get("crawled_at") or raw.get("system_created_at")
    if not value:
        match = re.search(r"/(\d{8}_\d{6})", envelope.get("bronze_reference", ""))
        if match:
            from datetime import datetime
            value = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
    return parse_rss_date(value or raw.get("pub_date"))


class State:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = duckdb.connect(str(path))
        self.db.execute("SET threads=2")
        self.db.execute("""CREATE TABLE IF NOT EXISTS raw_articles(
            article_key VARCHAR PRIMARY KEY, payload JSON NOT NULL, fingerprint VARCHAR NOT NULL,
            bronze_reference VARCHAR NOT NULL, first_seen TIMESTAMPTZ DEFAULT current_timestamp,
            last_seen TIMESTAMPTZ DEFAULT current_timestamp);
            CREATE TABLE IF NOT EXISTS kafka_messages(topic VARCHAR, partition_id INTEGER, offset_id BIGINT,
                article_key VARCHAR, status VARCHAR NOT NULL, error VARCHAR, raw_message VARCHAR,
                PRIMARY KEY(topic,partition_id,offset_id));
            CREATE TABLE IF NOT EXISTS runtime_meta(key VARCHAR PRIMARY KEY,value BIGINT NOT NULL);
            INSERT INTO runtime_meta VALUES ('revision',0),('stream_revision',-1),('batch_revision',-1),('published_revision',-1)
            ON CONFLICT DO NOTHING;""")
        self.db.execute("ALTER TABLE kafka_messages ADD COLUMN IF NOT EXISTS message_fingerprint VARCHAR")

    def meta(self, key):
        return self.db.execute("SELECT value FROM runtime_meta WHERE key=?", [key]).fetchone()[0]

    def mark(self, key, value):
        self.db.execute("UPDATE runtime_meta SET value=? WHERE key=?", [value, key])

    def ingest(self, records):
        stats = dict(received=len(records), inserted=0, updated=0, unchanged=0, replayed=0, quarantined=0)
        self.db.execute("BEGIN")
        try:
            revision = self.meta("revision")
            for record in records:
                identity = [record.topic, record.partition, record.offset]
                message_digest = hashlib.sha256(record.value).hexdigest()
                existing = self.db.execute("SELECT message_fingerprint FROM kafka_messages WHERE topic=? AND partition_id=? AND offset_id=?", identity).fetchone()
                if existing and existing[0] is not None:
                    if existing[0] is not None and existing[0] != message_digest:
                        raise RuntimeError("Kafka offset reused with different payload; restore the broker volume or use --rebuild")
                    stats["replayed"] += 1
                    continue
                key, error = None, None
                try:
                    envelope = json.loads(record.value.decode("utf-8"))
                    raw = envelope["article"]
                    captured = observed_at(raw, envelope)
                    for name in ("description", "content"):
                        raw[name] = raw.get(name) or ""
                    raw["pub_date"] = str(raw.get("pub_date") or "")
                    row = clean_article(normalize_article(raw))
                    row = {name: row.get(name) for name in (*CORE, "article_key", "normalized_url")}
                    row["pub_date"] = row["pub_date"].isoformat()
                    row["content"] = row.get("content") or ""
                    row["_bronze_observed_at"] = captured.isoformat() if captured else None
                    row["_body_observed_at"] = row["_bronze_observed_at"] if row["content"] else None
                    key = row["article_key"]
                    old = self.db.execute("SELECT payload,fingerprint FROM raw_articles WHERE article_key=?", [key]).fetchone()
                    previous = json.loads(old[0]) if old else None
                    previous_date = parse_rss_date(previous.get("_bronze_observed_at")) if previous else None
                    stale = bool(previous_date and captured and captured < previous_date)
                    if stale:
                        if row["content"] and not previous.get("content"):
                            # Older HTML can enrich a newer RSS headline without
                            # replacing that newer headline/lead/publication date.
                            row = dict(previous, content=row["content"], _body_observed_at=row["_body_observed_at"])
                        else:
                            row = previous
                    elif previous and not row["content"]:
                        row["content"] = previous.get("content") or ""
                        row["_body_observed_at"] = previous.get("_body_observed_at")
                    digest = signature(row)
                    if old and old[1] == digest:
                        stats["unchanged"] += 1
                        status = "stale_snapshot" if stale else "unchanged"
                        # Capture provenance still advances when text is identical.
                        self.db.execute("UPDATE raw_articles SET payload=? WHERE article_key=?", [json_text(row), key])
                    else:
                        status = "updated" if old else "inserted"
                        stats[status] += 1
                        self.db.execute("""INSERT INTO raw_articles(article_key,payload,fingerprint,bronze_reference)
                            VALUES (?,?,?,?) ON CONFLICT(article_key) DO UPDATE SET payload=excluded.payload,
                            fingerprint=excluded.fingerprint,bronze_reference=excluded.bronze_reference,last_seen=now()""",
                            [key, json_text(row), digest, envelope["bronze_reference"]])
                        revision += 1
                except (ValueError, TypeError, KeyError) as failure:
                    status, error = "quarantined", str(failure)
                    stats["quarantined"] += 1
                self.db.execute("""INSERT INTO kafka_messages VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(topic,partition_id,offset_id) DO UPDATE SET article_key=excluded.article_key,
                    status=excluded.status,error=excluded.error,raw_message=excluded.raw_message,
                    message_fingerprint=excluded.message_fingerprint""", identity + [key, status, error,
                                record.value.decode('utf-8', errors='replace') if error else None, message_digest])
            self.mark("revision", revision)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return stats

    def frame(self):
        rows = [dict(json.loads(payload), input_fingerprint=digest) for payload, digest in
                self.db.execute("SELECT payload,fingerprint FROM raw_articles ORDER BY article_key").fetchall()]
        return pl.DataFrame(rows, infer_schema_length=None)

    def counts(self):
        return {"articles": self.db.execute("SELECT count(*) FROM raw_articles").fetchone()[0],
                "messages": self.db.execute("SELECT count(*) FROM kafka_messages").fetchone()[0],
                "quarantined": self.db.execute("SELECT count(*) FROM kafka_messages WHERE status='quarantined'").fetchone()[0]}

    def close(self):
        self.db.close()
