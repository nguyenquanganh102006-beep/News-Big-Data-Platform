"""Bronze is the durable filesystem outbox; Kafka acknowledgements checkpoint it."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone

import polars as pl
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

from .config import BOOTSTRAP, atomic_json
from preprocessors.run import bronze_snapshots

_FINGERPRINT_CACHE = {}


def ensure_topic(topic):
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP, api_version_auto_timeout_ms=15000)
    try:
        try:
            admin.create_topics([NewTopic(topic, 1, 1)])
        except TopicAlreadyExistsError:
            pass
    finally:
        admin.close()


def producer():
    return KafkaProducer(bootstrap_servers=BOOTSTRAP, acks="all", retries=10,
                         api_version_auto_timeout_ms=15000,
                         max_in_flight_requests_per_connection=1, max_request_size=8388608,
                         value_serializer=lambda value: json.dumps(value, ensure_ascii=False, default=str, allow_nan=False).encode("utf-8"))


def publish_bronze(settings):
    path = Path(settings["outbox"])
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    files = [(source, file) for source, paths in bronze_snapshots(fingerprint_cache=_FINGERPRINT_CACHE).items() for file in paths]
    # Historical capture first; RSS snapshots can then update the same URL.
    files.sort(key=lambda item: (not item[1].name.startswith("history_"), item[1].name, item[0]))
    stats = dict(snapshots=0, messages=0, skipped_snapshots=0)
    client = None
    metadata_changed = False
    try:
        for source, file in files:
            identity = source + "/" + file.name
            stamp = file.stat()
            previous = state.get(identity, {})
            if previous.get("size") == stamp.st_size and previous.get("mtime_ns") == stamp.st_mtime_ns:
                stats["skipped_snapshots"] += 1
                continue
            raw_bytes = file.read_bytes()
            digest = hashlib.sha256(raw_bytes).hexdigest()
            if state.get(identity, {}).get("sha256") == digest:
                state[identity].update(size=stamp.st_size, mtime_ns=stamp.st_mtime_ns)
                metadata_changed = True
                stats["skipped_snapshots"] += 1
                continue
            if client is None:
                client = producer()
            frame = pl.read_parquet(BytesIO(raw_bytes))
            if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Bronze changed during reading; retry later: {file}")
            pending = []
            for index, row in enumerate(frame.iter_rows(named=True)):
                row["source"] = source
                envelope = {"schema_version": 1, "article": row, "bronze_reference": identity + f":{index}",
                            "bronze_sha256": digest, "sent_at": datetime.now(timezone.utc).isoformat()}
                pending.append(client.send(settings["topic"], value=envelope))
                if len(pending) >= 512:
                    for future in pending:
                        future.get(timeout=120)
                    pending.clear()
                stats["messages"] += 1
            for future in pending:
                future.get(timeout=120)
            client.flush(timeout=120)
            state[identity] = {"sha256": digest, "rows": frame.height,
                               "size": stamp.st_size, "mtime_ns": stamp.st_mtime_ns,
                               "acknowledged_at": datetime.now(timezone.utc).isoformat()}
            atomic_json(path, state)
            stats["snapshots"] += 1
            print(f"[A2 Bronze->Kafka] {identity} total_sent={stats['messages']}", flush=True)
    finally:
        if client:
            client.close(timeout=15)
    if metadata_changed:
        atomic_json(path, state)
    return stats


def stage_article(article):
    """External crawler interface: persist Bronze first; running service sends it."""
    from config import RSS_SOURCES
    from streaming.message import normalize_article
    from uuid import uuid4
    import os
    row = normalize_article(article)
    directory = Path(RSS_SOURCES[row["source"]]["bronze_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    staged = directory / (uuid4().hex + ".tmp")
    try:
        pl.DataFrame([row], infer_schema_length=None).write_parquet(staged)
        while True:
            name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".parquet"
            try:
                os.link(staged, directory / name)
                break
            except FileExistsError:
                continue
    finally:
        staged.unlink(missing_ok=True)
    return row["article_key"]
