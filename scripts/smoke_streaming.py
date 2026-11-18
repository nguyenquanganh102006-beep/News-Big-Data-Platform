"""Replay one real Bronze accident through a continuously running consumer.

Creates a new output directory and unique Redis queue; never overwrites a run.
Run after pip install -e . from the project root.
"""
import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import threading
import time
from uuid import uuid4

import polars as pl
import redis

from filters.accident import classify_accident
from streaming.consumer import Consumer, writer_lock
from streaming.pipeline import ArticleProcessor
from streaming.producer import enqueue_article
from streaming.queue import ArticleQueue
from streaming.repository import ProvisionalRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bronze", required=True, type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(level=logging.INFO)
    row = next(row for row in pl.read_parquet(args.bronze).iter_rows(named=True)
               if classify_accident(row.get("title"), row.get("description")).label == "accident")
    row["source"] = args.source
    (args.output / "article.json").write_text(json.dumps(row, ensure_ascii=False, default=str), encoding="utf-8")
    client = redis.Redis.from_url(args.redis_url, decode_responses=True,
                                  socket_connect_timeout=3, socket_timeout=5)
    queue = ArticleQueue(client, "smoke:stream:" + uuid4().hex)
    errors = []
    database = args.output / "provisional.duckdb"
    with writer_lock(database):
        repo = ProvisionalRepository(database)
        repo.initialize()
        consumer = Consumer(queue, ArticleProcessor(repo))
        def run():
            try:
                consumer.run()
            except BaseException as error:
                errors.append(str(error))
        worker = threading.Thread(target=run)
        worker.start()
        try:
            start = time.monotonic()
            key = enqueue_article(row, client, queue.name)
            deadline = start + 30
            while time.monotonic() < deadline:
                if errors:
                    raise RuntimeError(errors)
                if client.llen(queue.name) + client.llen(queue.processing) == 0:
                    break
                time.sleep(0.02)
            elapsed = time.monotonic() - start
        finally:
            consumer.stop.set()
            worker.join(15)
        if worker.is_alive():
            raise RuntimeError("consumer did not stop")
        try:
            receipts = repo.connection.execute("SELECT article_key,status,event_id FROM stream_receipts").fetchall()
            counts = repo.counts()
            report = dict(bronze=str(args.bronze), source=args.source, article_key=key,
                          elapsed_seconds=elapsed, receipts=receipts, counts=counts,
                          redis_version=client.info("server")["redis_version"], errors=errors,
                          queue=queue.name, queue_remaining=client.llen(queue.name),
                          in_flight=client.llen(queue.processing), dead=client.llen(queue.dead))
            (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if errors or counts["accident_events"] != 1 or len(receipts) != 1 or elapsed >= 30:
                raise RuntimeError(f"Smoke did not create one provisional event: {report}")
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            repo.close()
            client.close()


if __name__ == "__main__":
    main()
