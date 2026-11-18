"""Regression checks runnable with `docker compose exec worker python check.py`."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from common import transform, digest, percentile
from sinks import SqlSink


def article(key, fatalities=None):
    return dict(run_id="test", article_key=key, source="TEST", published_at="2026-01-01",
                title="  Xe   va chạm ", content="Nội dung", description="Tin", sent_at=1.0,
                accident_label="accident", province=None, fatalities=fatalities, injuries=None, event_id=None)


class BenchmarkTests(unittest.TestCase):
    def test_nulls_after_first_hundred_rows(self):
        rows = [article(str(i)) for i in range(120)] + [article("last", 4)]
        result = transform(rows)
        self.assertEqual(result[-1]["fatalities"], 4)
        self.assertEqual(result[0]["title"], "Xe va chạm")
        self.assertEqual(result[0]["source"], "test")
        self.assertIsNone(result[0]["event_id"])

    def test_digest_ignores_run_and_clock_not_facts(self):
        a = transform([article("a")])
        b = transform([dict(article("a"), run_id="other", sent_at=3.0)])
        self.assertEqual(digest(a), digest(b))
        b[0]["fatalities"] = 2
        self.assertNotEqual(digest(a), digest(b))

    def test_duckdb_retry_and_nulls(self):
        with TemporaryDirectory() as directory:
            sink = SqlSink("A2", Path(directory))
            try:
                output = transform([article("a"), article("b", 2)])
                sink.write(output, 0)
                sink.write(output, 0)
                self.assertEqual(len(sink.rows()), 2)
                self.assertEqual(digest(output), digest(sink.rows()))
            finally:
                sink.close()

    def test_percentile(self):
        self.assertEqual(percentile([0, 10], .95), 9.5)
        self.assertIsNone(percentile([], .95))

    def test_redis_baseline_recovery_after_database_commit(self):
        import json
        import uuid
        from redis_baseline import RedisConsumer, client
        name = "bench-unit-" + uuid.uuid4().hex
        connection = client()
        consumer = RedisConsumer(name)
        try:
            connection.lpush(name, json.dumps(article("a")))
            with TemporaryDirectory() as directory:
                sink = SqlSink("B0", Path(directory))
                try:
                    output = transform([consumer.take()])
                    sink.write(output, 0)
                    self.assertEqual(connection.llen(consumer.queue.processing), 1)
                    # Consumer exits after commit and before ACK; recover uses
                    # the production queue implementation, then deliver again.
                    consumer.close()
                    from redis_baseline import ArticleQueue
                    ArticleQueue(connection, name).recover()
                    consumer = RedisConsumer.__new__(RedisConsumer)
                    consumer.connection = client()
                    consumer.queue = ArticleQueue(consumer.connection, name)
                    consumer.pending = []
                    sink.write(transform([consumer.take()]), 0)
                    consumer.ack()
                    consumer.verify_empty()
                    self.assertEqual(len(sink.rows()), 1)
                    self.assertEqual(digest(output), digest(sink.rows()))
                finally:
                    sink.close()
        finally:
            consumer.close()
            connection.delete(name, name + ":processing", name + ":attempts", name + ":dead")
            connection.close()


if __name__ == "__main__":
    unittest.main()
