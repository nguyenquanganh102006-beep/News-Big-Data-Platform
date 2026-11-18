"""Replay canonical Silver articles through a real Redis queue and consumer."""
import json
from collections import Counter
from pathlib import Path

import polars as pl

from config import DEDUPLICATED_DATA_DIR, EXTRACT_SOURCES, EVENT_INPUT_DIR
from config.streaming import database_path, queue_name, redis_client
from events.adapter import prepare_article
from events.locking import writer_lock
from events.similarity import TextModel
from .consumer import Consumer
from .pipeline import ArticleProcessor
from .producer import enqueue_article
from .queue import ArticleQueue
from .repository import ProvisionalRepository


def replay():
    frames = [pl.read_parquet(Path(DEDUPLICATED_DATA_DIR) / f"{source}.parquet")
              for source in EXTRACT_SOURCES]
    frame = pl.concat(frames, how="diagonal_relaxed").filter(~pl.col("is_duplicate").fill_null(False))
    frame = frame.sort(["pub_date", "article_key"], nulls_last=True)
    client = redis_client()
    # A separate queue protects any regular live traffic; use the normal Gold repository.
    queue = ArticleQueue(client, queue_name() + ":history_replay")
    stats = Counter()
    try:
        client.ping()
        with writer_lock(database_path()):
            repo = ProvisionalRepository(database_path())
            try:
                repo.initialize()
                processor = ArticleProcessor(repo)
                consumer = Consumer(queue, processor)
                queue.recover()
                if client.llen(queue.name):
                    raise RuntimeError("Replay queue has pending messages; inspect them before starting another replay")
                # Prewarm the same embeddings without making any matching decisions.
                texts = []
                for source in EXTRACT_SOURCES:
                    path = Path(EVENT_INPUT_DIR) / f"{source}.parquet"
                    for row in pl.read_parquet(path).iter_rows(named=True):
                        texts.append(prepare_article(row)["text"])
                TextModel(texts, semantic_model=processor.config.semantic_model,
                          cache_dir=processor.config.semantic_cache_dir)
                for index, row in enumerate(frame.iter_rows(named=True), 1):
                    payload = {key: row.get(key) for key in
                               ("source", "title", "description", "link", "pub_date", "content")}
                    payload["content"] = payload.get("content") or ""
                    payload["description"] = payload.get("description") or ""
                    key = enqueue_article(payload, client=client, queue=queue.name)
                    result = consumer.once()
                    if result is None or result["status"] in ("failed", "invalid"):
                        raise RuntimeError(f"Streaming replay failed for {key}: {result}")
                    stats[result["status"]] += 1
                    if index % 250 == 0:
                        print(f"[Streaming replay] {index}/{frame.height} {dict(stats)}", flush=True)
                summary = {"input": frame.height, "processed": dict(stats), "database": repo.counts(),
                           "receipts": repo.connection.execute("SELECT count(*) FROM stream_receipts").fetchone()[0],
                           "queue": client.llen(queue.name), "processing": client.llen(queue.processing),
                           "dead": client.llen(queue.dead)}
                if summary["queue"] or summary["processing"] or summary["dead"]:
                    raise RuntimeError(f"Replay queue did not finish cleanly: {summary}")
                print(json.dumps(summary, ensure_ascii=False), flush=True)
                return summary
            finally:
                repo.close()
    finally:
        client.close()


if __name__ == "__main__":
    replay()
