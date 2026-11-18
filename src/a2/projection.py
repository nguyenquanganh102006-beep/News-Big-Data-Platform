"""Rebuild a closed provisional projection; shared Phase 3 matching/aggregation."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import polars as pl

from config import MatchConfig
from events.adapter import json_text
from events.run import load_silver_articles
from events.service import MatchingService
from events.similarity import TextModel
from events.locking import writer_lock
from streaming.repository import ProvisionalRepository
from batch.repository import CanonicalRepository
from batch.run import run_batch


def stream_projection(paths, catalog, destination, config=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    config = config or MatchConfig(radius_hours=24)
    incoming = load_silver_articles(paths)
    model = TextModel([a["text"] for a in incoming], semantic_model=config.semantic_model, cache_dir=config.semantic_cache_dir)
    service = MatchingService(config, past_only=True)
    stats = {"input": len(incoming), "new_event": 0, "matched": 0, "needs_review": 0}
    with writer_lock(destination), TemporaryDirectory(dir=destination.parent, prefix="a2-stream-stage-") as directory:
        staged = Path(directory) / "provisional.duckdb"
        repo = ProvisionalRepository(staged)
        try:
            repo.initialize()
            repo.connection.execute("BEGIN")
            stored, decisions = {}, {}
            for article in incoming:
                key = article["article_key"]
                repo.insert_article(article)
                stored[key] = article
                decision = service.decide(article, repo, stored, model)
                kind = decision["decision"]
                stats[kind] += 1
                event_id = None
                if kind == "needs_review":
                    repo.save_review(article, decision)
                else:
                    event_id = repo.save_assignment(article, decision, service.config_id, model.fingerprint)
                    repo.refresh_event(event_id, stored)
                decisions[key] = (kind, event_id)
            receipts = [{"article_key": row["article_key"], "status": decisions.get(row["article_key"], (row["accident_label"], None))[0],
                         "raw_payload": json_text(row), "event_id": decisions.get(row["article_key"], (None, None))[1]}
                        for row in catalog.iter_rows(named=True)]
            frame = pl.DataFrame(receipts, schema={"article_key": pl.String, "status": pl.String, "raw_payload": pl.String, "event_id": pl.String})
            repo.connection.raw.register("receipt_batch", frame.to_arrow())
            repo.connection.execute("INSERT INTO stream_receipts SELECT article_key,status,raw_payload,event_id,current_timestamp FROM receipt_batch")
            stats["counts"] = repo.counts()
            stats["receipts"] = catalog.height
            repo.connection.execute("INSERT INTO event_runs(run_id,summary,config,model_fingerprint) VALUES (?,?,?,?)",
                                    [str(uuid4()), json_text(stats), json_text(service.config_values), model.fingerprint])
            repo.connection.execute("COMMIT")
            repo.connection.execute("CHECKPOINT")
        finally:
            repo.close()
        staged.replace(destination)
    return stats


def canonical_projection(paths, destination, config=None):
    if any(pl.scan_parquet(path).select(pl.len()).collect().item() for path in paths.values()):
        return run_batch(paths, destination, config=config)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with writer_lock(destination), TemporaryDirectory(dir=destination.parent) as directory:
        staged = Path(directory) / "canonical.duckdb"
        repo = CanonicalRepository(staged)
        try:
            repo.initialize()
            counts = repo.counts()
        finally:
            repo.close()
        staged.replace(destination)
    return {"input": 0, "counts": counts}
