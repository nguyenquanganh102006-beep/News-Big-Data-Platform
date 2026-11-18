import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import time

import duckdb
import polars as pl

from a2.state import State, signature
from a2.processing import prepare, review_annotations
from a2.projection import stream_projection, canonical_projection
from a2.producer import publish_bronze
from a2.runtime import Runtime
from config import MatchConfig


def record(offset=0, **changes):
    raw = dict(source="tuoitre", title="Xe tải va chạm xe máy tại Hà Nội, 2 người tử vong",
               description="Tại quận Cầu Giấy, Hà Nội, xe tải va chạm xe máy.", content="",
               pub_date="2026-11-17T08:00:00+07:00", link="https://tuoitre.vn/a2-test.htm")
    raw.update(changes)
    return SimpleNamespace(topic="test", partition=0, offset=offset,
                           value=json.dumps({"article": raw, "bronze_reference": "test:0"}).encode())


class A2Tests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state = State(self.root / "state.duckdb")
        self.addCleanup(self.state.close)

    def test_replay_and_empty_rss_body_do_not_erase_history(self):
        r = record(content="Thân bài đầy đủ")
        self.assertEqual(self.state.ingest([r])["inserted"], 1)
        self.assertEqual(self.state.ingest([r])["replayed"], 1)
        self.state.ingest([record(1)])
        self.assertEqual(self.state.frame()["content"][0], "Thân bài đầy đủ")
        self.assertEqual(self.state.meta("revision"), 1)
        self.state.ingest([record(2, title="Xe tải va chạm xe máy tại Hà Nội, 3 người tử vong")])
        self.assertEqual(self.state.meta("revision"), 2)
        self.assertEqual(self.state.counts()["articles"], 1)

    def test_invalid_record_is_durably_quarantined(self):
        r = SimpleNamespace(topic="test", partition=0, offset=0, value=b"not-json")
        self.state.ingest([r])
        self.assertEqual(self.state.counts(), {"articles": 0, "messages": 1, "quarantined": 1})
        self.assertEqual(self.state.db.execute("SELECT raw_message FROM kafka_messages").fetchone()[0], "not-json")
        self.assertEqual(self.state.ingest([r])["replayed"], 1)

    def test_offset_reuse_cannot_silently_discard_new_payload(self):
        self.state.ingest([record()])
        with self.assertRaisesRegex(RuntimeError, "offset reused"):
            self.state.ingest([record(title="Different payload at the same Kafka offset")])
        self.assertEqual(self.state.counts()["articles"], 1)

    def test_old_capture_does_not_replace_newer_headline(self):
        self.state.ingest([record(crawled_at="2026-11-17T10:00:00+07:00", content="Latest body")])
        self.state.ingest([record(1, crawled_at="2026-11-10T10:00:00+07:00", title="Obsolete headline")])
        self.assertNotEqual(self.state.frame()["title"][0], "Obsolete headline")
        self.assertEqual(self.state.frame()["content"][0], "Latest body")

    def test_legacy_offset_migration_reconciles_capture_order(self):
        self.state.ingest([record(crawled_at="2026-11-16T10:00:00+07:00", content="HTML body")])
        self.state.db.execute("UPDATE kafka_messages SET message_fingerprint=NULL")
        self.state.ingest([record(crawled_at="2026-11-16T10:00:00+07:00", content="HTML body")])
        self.assertEqual(self.state.counts()["messages"], 1)
        self.assertEqual(self.state.ingest([record(crawled_at="2026-11-16T10:00:00+07:00", content="HTML body")])["replayed"], 1)

    def test_journal_atomic_rollback(self):
        with patch.object(self.state, "mark", side_effect=RuntimeError("disk failure")):
            with self.assertRaises(RuntimeError):
                self.state.ingest([record()])
        self.assertEqual(self.state.counts()["messages"], 0)
        self.assertEqual(self.state.counts()["articles"], 0)

    def test_update_rebuild_removes_old_event_and_silver_matches_both_paths(self):
        self.state.ingest([record()])
        paths_dir = self.root / "silver"
        frame, paths = prepare(self.state.frame(), paths_dir, enrich=False)
        config = MatchConfig(radius_hours=24, semantic_model=None)
        first = stream_projection(paths, frame, self.root / "stream.duckdb", config)
        self.assertEqual(first["counts"]["accident_events"], 1)
        batch = canonical_projection(paths, self.root / "batch.duckdb", config)
        self.assertEqual(batch["counts"]["accident_events"], 1)
        self.state.ingest([record(1, title="Quy định đăng ký xe mới", description="Hướng dẫn thủ tục hành chính")])
        frame, paths = prepare(self.state.frame(), paths_dir, enrich=False)
        second = stream_projection(paths, frame, self.root / "stream.duckdb", config)
        self.assertEqual(second["counts"]["accident_events"], 0)
        self.assertEqual(second["receipts"], 1)
        self.assertEqual(canonical_projection(paths, self.root / "batch.duckdb", config)["counts"]["accident_events"], 0)

    def test_review_override_requires_unchanged_fingerprint(self):
        self.state.ingest([record()])
        raw = self.state.frame().row(0, named=True)
        annotations = {raw["article_key"]: (raw["input_fingerprint"], "uncertain", "reviewed")}
        frame, _ = prepare(self.state.frame(), self.root / "silver", annotations, enrich=False)
        self.assertEqual(frame["accident_label"][0], "uncertain")
        self.state.ingest([record(1, description="Tại Hà Nội, xe tải va chạm xe máy khiến 4 người tử vong.")])
        changed, _ = prepare(self.state.frame(), self.root / "silver", annotations, enrich=False)
        self.assertFalse(changed["review_override_applied"][0])
        self.assertEqual(changed["accident_label"][0], "accident")

    def test_null_metadata_does_not_discard_review_annotations(self):
        raw = json.loads(record().value)["article"]
        raw.update(system_created_at=None, accident_label="uncertain", filter_reason="reviewed")
        review = self.root / "review.parquet"
        pl.DataFrame([raw]).write_parquet(review)
        with patch("a2.processing.REVIEW", review):
            annotations = review_annotations()
        self.assertEqual(len(annotations), 1)
        self.assertEqual(next(iter(annotations.values()))[1], "uncertain")

    def test_bronze_checkpoint_waits_for_broker_ack(self):
        file = self.root / "20261117_080000.parquet"
        pl.DataFrame([{"title": "raw Bronze", "content": "raw body"}]).write_parquet(file)
        class Future:
            def get(self, **kwargs):
                raise RuntimeError("Kafka unavailable")
        client = SimpleNamespace(send=lambda *a, **k: Future(), close=lambda **k: None)
        settings = {"outbox": str(self.root / "outbox.json"), "topic": "test"}
        with patch("a2.producer.bronze_snapshots", return_value={"tuoitre": [file]}), patch("a2.producer.producer", return_value=client):
            with self.assertRaises(RuntimeError):
                publish_bronze(settings)
        self.assertFalse(Path(settings["outbox"]).exists())

    def test_default_producer_persists_bronze_without_publishing_silver(self):
        from config import RSS_SOURCES
        from a2.producer import stage_article
        sources = {key: dict(value) for key, value in RSS_SOURCES.items()}
        sources["tuoitre"]["bronze_dir"] = str(self.root / "bronze")
        raw = json.loads(record(content="Original body").value)["article"]
        with patch("config.RSS_SOURCES", sources), patch("a2.producer.producer") as sender:
            key = stage_article(raw)
        sender.assert_not_called()
        files = list((self.root / "bronze").glob("*.parquet"))
        self.assertEqual(len(files), 1)
        saved = pl.read_parquet(files[0]).row(0, named=True)
        self.assertEqual(saved["article_key"], key)
        self.assertEqual(saved["content"], "Original body")

    def test_stream_publishes_before_scheduled_batch_then_batch_catches_up(self):
        config = MatchConfig(radius_hours=24, semantic_model=None)
        runtime = Runtime.__new__(Runtime)
        runtime.state, runtime.batch_seconds, runtime.enrich = self.state, 900, False
        runtime.last_batch, runtime.annotations, runtime.stats = 0, {}, {}
        runtime.settings = {"run_id": "test", "topic": "test", "silver": str(self.root / "silver"),
                            "stream": str(self.root / "stream.duckdb"), "canonical": str(self.root / "canonical.duckdb")}
        runtime.heartbeat = lambda *a, **k: None
        with patch("a2.runtime.HOME", self.root / "artifacts"), patch("a2.publish.DATA_ARTIFACTS_DIR", self.root / "artifacts"), \
             patch("a2.runtime.stream_projection", side_effect=lambda p, f, d: stream_projection(p, f, d, config)), \
             patch("a2.runtime.canonical_projection", side_effect=lambda p, d: canonical_projection(p, d, config)):
            self.state.ingest([record()])
            runtime.materialize(True)
            self.state.ingest([record(1, link="https://tuoitre.vn/a2-next.htm",
                                      title="Ô tô khách lật xuống vực tại Lâm Đồng, 4 người chết",
                                      description="Xe khách lao xuống vực tại đèo Bảo Lộc, Lâm Đồng.")])
            runtime.last_batch = time.monotonic()
            stream_only = runtime.materialize(False)
            self.assertLess(stream_only["batch_revision"], stream_only["revision"])
            self.assertEqual(self.state.meta("stream_revision"), 2)
            runtime.last_batch = time.monotonic() - 901
            reconciled = runtime.materialize(False)
            self.assertEqual(reconciled["batch_revision"], reconciled["revision"])
            self.assertEqual(reconciled["pipeline_counts"]["gold"]["articles"], 2)

    def test_projection_failure_does_not_ack_kafka(self):
        consumer = SimpleNamespace(end_offsets=lambda x: {"tp": 1}, position=lambda x: 0,
                                   poll=lambda **k: {"tp": [record()]},
                                   commit=lambda: self.fail("Offset ACK before projection"))
        runtime = Runtime.__new__(Runtime)
        runtime.consumer, runtime.tp, runtime.state = consumer, "tp", self.state
        runtime.heartbeat = lambda *a, **k: None
        runtime.materialize = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("projection failed"))
        # First poll advances position as a real Kafka consumer does.
        def poll(**kwargs):
            consumer.position = lambda x: 1
            return {"tp": [record()]}
        consumer.poll = poll
        with self.assertRaisesRegex(RuntimeError, "projection failed"):
            runtime.drain()
        self.assertEqual(self.state.counts()["articles"], 1)
        self.assertEqual(self.state.meta("stream_revision"), -1)

    def test_poll_past_watermark_never_silently_drops_a_message(self):
        acknowledged = []
        consumer = SimpleNamespace(end_offsets=lambda x: {"tp": 1}, position=lambda x: 0,
                                   commit=lambda: acknowledged.append(True), committed=lambda x: 2)
        def poll(**kwargs):
            consumer.position = lambda x: 2
            return {"tp": [record(), record(1, link="https://tuoitre.vn/a2-second.htm")]}
        consumer.poll = poll
        runtime = Runtime.__new__(Runtime)
        runtime.consumer, runtime.tp, runtime.state = consumer, "tp", self.state
        runtime.heartbeat = lambda *a, **k: None
        runtime.materialize = lambda *a: None
        runtime.drain()
        self.assertEqual(self.state.counts()["messages"], 2)
        self.assertEqual(len(acknowledged), 1)


if __name__ == "__main__":
    unittest.main()
