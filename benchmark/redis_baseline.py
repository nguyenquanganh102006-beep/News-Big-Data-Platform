"""Use the production reliable queue, isolated Redis namespace and shared payload."""
import json
import sys
import time

import redis

sys.path.insert(0, "/project/src")
from streaming.queue import ArticleQueue


def client():
    return redis.Redis(host="redis", port=6379, decode_responses=True, socket_timeout=10)


def produce_redis(rows, name, run_id, rate, state):
    connection = client()
    try:
        start = time.perf_counter()
        for index, original in enumerate(rows):
            if rate:
                delay = start + index / rate - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            row = dict(original, run_id=run_id, sent_at=time.time())
            state.setdefault("first_sent_at", row["sent_at"])
            state["last_sent_at"] = row["sent_at"]
            connection.lpush(name, json.dumps(row, ensure_ascii=False))
        state["sent_count"] = len(rows)
    except BaseException as error:
        state["error"] = repr(error)
    finally:
        connection.close()
        state["done"] = True


class RedisConsumer:
    def __init__(self, name):
        self.connection = client()
        self.queue = ArticleQueue(self.connection, name)
        if any(self.connection.exists(key) for key in (name, self.queue.processing, self.queue.dead, self.queue.attempts)):
            raise RuntimeError("Benchmark queue namespace already exists")
        self.pending = []

    def take(self):
        raw = self.queue.take(timeout=1)
        if raw is not None:
            self.pending.append(raw)
            return json.loads(raw)

    def ack(self):
        for raw in self.pending:
            self.queue.ack(raw)
        self.pending.clear()

    def verify_empty(self):
        assert not self.pending
        assert self.connection.llen(self.queue.name) == 0
        assert self.connection.llen(self.queue.processing) == 0
        assert self.connection.llen(self.queue.dead) == 0

    def close(self):
        self.connection.close()
