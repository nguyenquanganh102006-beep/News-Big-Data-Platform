import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from events.repository import EventRepository
from events.adapter import prepare_article
from streaming.consumer import Consumer, writer_lock
from streaming.message import normalize_article, parse_message
from streaming.pipeline import ArticleProcessor, clean_article
from streaming.producer import enqueue_article
from streaming.queue import ArticleQueue
from streaming.repository import ProvisionalRepository


def article(link="https://www.vietnamplus.vn/test-1.html", **changes):
    row = dict(source="vietnamplus", link=link, pub_date="2026-11-10T08:00:00+07:00",
               title="Xe tải va chạm xe máy tại Hà Nội",
               description="Xe tải va chạm xe máy tại quận Cầu Giấy, Hà Nội khiến 2 người tử vong.")
    row.update(changes)
    return row


class StreamingTests(unittest.TestCase):
    def test_vietnamplus_related_articles_do_not_pollute_location(self):
        payload = article(
            title="Thành phố Hồ Chí Minh: Xe ben va chạm xe máy, hai người tử vong",
            description='<a href="image"><img src="image.jpg"></a>'
                        '<p>Xe ben va chạm xe máy khiến hai người tử vong.</p>'
                        '<a href="other">Xe tải gây tai nạn tại Hà Nội</a>')
        cleaned = clean_article(normalize_article(payload))
        self.assertNotIn("Hà Nội", cleaned["description"])
        self.assertEqual(cleaned["description"], "Xe ben va chạm xe máy khiến hai người tử vong.")
        result = self.processor.process(normalize_article(payload))
        self.assertEqual(result["status"], "new_event")
        self.assertEqual(self.repo.connection.execute(
            "SELECT province FROM provisional_events").fetchall(), [("TP Hồ Chí Minh",)])

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "test.duckdb"
        self.repo = ProvisionalRepository(self.db)
        self.addCleanup(self.repo.close)
        self.repo.initialize()
        self.processor = ArticleProcessor(self.repo)

    def test_new_matching_replay_and_official_isolation(self):
        official = EventRepository(self.db)
        official.initialize()
        official_article = prepare_article(dict(normalize_article(article()), province="Hà Nội",
                                                 vehicles=["xe tải", "xe máy"]))
        official.insert_article(official_article)
        official.save_assignment(official_article, {"decision": "new_event"}, "test", "test")
        before = official.connection.execute("SELECT * FROM accident_events").fetchall()
        official.close()
        first = self.processor.process(normalize_article(article()))
        self.assertEqual(first["status"], "new_event")
        second = self.processor.process(normalize_article(article("https://www.vietnamplus.vn/test-2.html")))
        self.assertEqual(second["status"], "matched")
        self.assertEqual(first["event_id"], second["event_id"])
        replay = self.processor.process(normalize_article(article()))
        self.assertEqual(replay["status"], "already_processed")
        self.assertEqual(self.repo.connection.raw.execute(
            "SELECT article_count,total_fatalities FROM provisional_events").fetchall(), [(2, 2)])
        self.assertEqual(self.repo.connection.raw.execute("SELECT * FROM accident_events").fetchall(), before)

    def test_not_accident_and_uncertain_are_retained_without_events(self):
        for index, title in enumerate(("Quy định xử phạt giao thông mới", "Tai nạn giao thông")):
            self.processor.process(normalize_article(article(f"https://example.com/{index}", title=title,
                                                            description="")))
        self.assertEqual(self.repo.counts()["accident_events"], 0)
        self.assertEqual(self.repo.connection.execute("SELECT count(*) FROM stream_receipts").fetchone()[0], 2)

    def test_transaction_rollback_and_retry(self):
        row = normalize_article(article())
        with patch.object(self.repo, "refresh_event", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.processor.process(row)
        self.assertEqual(self.repo.counts()["articles"], 0)
        self.assertEqual(self.repo.counts()["accident_events"], 0)
        self.assertEqual(self.processor.process(row)["status"], "new_event")

    def test_missing_province_is_reviewed(self):
        result = self.processor.process(normalize_article(article(description="Xe tải va chạm xe máy.",
                                                                 title="Xe tải va chạm xe máy")))
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(self.repo.counts()["accident_events"], 0)

    def test_validation_and_stable_identity(self):
        first = normalize_article(article())
        tracked = normalize_article(article(article()["link"] + "?utm_source=test#abc", article_key="fake"))
        self.assertEqual(first["article_key"], tracked["article_key"])
        for invalid in ([], {}, article(source="unknown"), article(link="bad"), article(title=5)):
            with self.assertRaises(ValueError):
                normalize_article(invalid)
        with self.assertRaises(ValueError):
            parse_message("not json")

    def test_source_dates_and_cleaning(self):
        for source, date in (("tuoitre", "11/10/2026 08:00:00 AM"),
                             ("vietnamplus", "Tue, 10 Nov 2026 08:00:00 +0700")):
            row = clean_article(normalize_article(article(source=source, pub_date=date,
                                                          title="<b>Xe tải</b><script>bad()</script>")))
            self.assertEqual(row["title"], "Xe tải")
            self.assertEqual(row["pub_date"].hour, 1)

    def test_writer_lock_rejects_second_writer(self):
        with writer_lock(self.db):
            with self.assertRaises(OSError):
                with writer_lock(self.db):
                    self.fail("second writer acquired lock")


@unittest.skipUnless(os.getenv("STREAM_TEST_REDIS_URL"), "requires a real Redis: STREAM_TEST_REDIS_URL")
class RedisIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = redis.Redis.from_url(os.environ["STREAM_TEST_REDIS_URL"], decode_responses=True,
                                          socket_connect_timeout=2, socket_timeout=5)
        self.addCleanup(self.client.close)
        self.assertTrue(self.client.ping())
        self.queue = ArticleQueue(self.client, "test:stream:" + uuid4().hex)
        self.addCleanup(lambda: self.client.delete(self.queue.name, self.queue.processing,
                                                   self.queue.dead, self.queue.attempts))
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = ProvisionalRepository(Path(self.tmp.name) / "test.duckdb")
        self.addCleanup(self.repo.close)
        self.repo.initialize()
        self.consumer = Consumer(self.queue, ArticleProcessor(self.repo), retry_seconds=0)

    def put(self, row):
        return enqueue_article(row, self.client, self.queue.name)

    def test_producer_to_continuous_consumer(self):
        errors = []
        def run():
            try:
                self.consumer.run()
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            start = time.monotonic()
            self.put(article())
            deadline = start + 5
            while time.monotonic() < deadline:
                # Ack is sent only after the database transaction commits.
                if self.client.llen(self.queue.name) + self.client.llen(self.queue.processing) == 0:
                    break
                time.sleep(0.02)
            elapsed = time.monotonic() - start
        finally:
            self.consumer.stop.set()
            worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertLess(elapsed, 5)
        self.assertEqual(self.repo.counts()["accident_events"], 1)
        print(f"Redis -> Consumer -> provisional_events: {elapsed:.3f}s")

    def test_matching_duplicate_nontraffic_and_malformed(self):
        self.put(article())
        self.assertEqual(self.consumer.once()["status"], "new_event")
        self.put(article("https://example.com/second"))
        self.assertEqual(self.consumer.once()["status"], "matched")
        self.put(article())
        self.assertEqual(self.consumer.once()["status"], "already_processed")
        self.put(article("https://example.com/other", title="Quy định giao thông", description=""))
        self.assertEqual(self.consumer.once()["status"], "not_accident")
        self.client.lpush(self.queue.name, "broken")
        self.assertEqual(self.consumer.once()["status"], "invalid")
        self.assertEqual(self.client.llen(self.queue.dead), 1)
        self.assertEqual(self.repo.counts()["accident_events"], 1)

    def test_crash_after_commit_before_ack(self):
        self.put(article())
        raw = self.queue.take()
        self.consumer.processor.process(parse_message(raw))
        self.queue.recover()
        self.assertEqual(self.consumer.once()["status"], "already_processed")
        self.assertEqual(self.repo.counts()["accident_events"], 1)
        self.assertEqual(self.client.llen(self.queue.processing), 0)

    def test_transient_failure_retry_and_dead_letter(self):
        self.put(article())
        with patch.object(self.consumer.processor, "process", side_effect=RuntimeError("module failed")):
            for _ in range(3):
                self.assertEqual(self.consumer.once()["status"], "failed")
        self.assertEqual(self.client.llen(self.queue.name), 0)
        self.assertEqual(self.client.llen(self.queue.dead), 1)
        self.assertEqual(self.repo.counts()["articles"], 0)
        self.put(article())
        self.assertEqual(self.consumer.once()["status"], "new_event")

    def test_connection_error_is_explicit(self):
        bad = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2,
                          retry=Retry(NoBackoff(), 0))
        self.addCleanup(bad.close)
        with self.assertRaises(redis.exceptions.RedisError):
            enqueue_article(article(), bad, self.queue.name)
