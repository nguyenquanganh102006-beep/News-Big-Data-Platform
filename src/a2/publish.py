"""Publish an immutable A2 snapshot; never mix raw legacy or benchmark results."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

import polars as pl

from config import DATA_ARTIFACTS_DIR
from events.locking import writer_lock
from .config import atomic_json


def publish(settings, catalog, state_counts, stats, revision, batch_revision):
    archive = Path(DATA_ARTIFACTS_DIR)
    with writer_lock(archive / "dashboard_publication"):
        generation = archive / "dashboard_snapshots" / ("a2_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:8])
        generation.mkdir(parents=True)
        catalog.write_parquet(generation / "articles.parquet")
        for key, name in (("stream", "streaming/provisional.duckdb"), ("canonical", "batch/canonical.duckdb")):
            source = Path(settings[key])
            if source.exists():
                destination = generation / "gold" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        unique = catalog.filter(~pl.col("is_duplicate"))
        labels = {label: unique.filter(pl.col("accident_label") == label).height for label in ("accident", "uncertain", "not_accident", "skipped_video")}
        stream, batch = stats.get("stream", {}), stats.get("batch", {})
        sc, bc = stream.get("counts", {}), batch.get("counts", {})
        outbox = stats.get("bronze_inventory", {})
        counts = {"bronze": outbox,
                  "silver": {"records": catalog.height, "sources": catalog["source"].n_unique()},
                  "content_dedup": {"input": catalog.height, "duplicates": catalog.filter(pl.col("is_duplicate")).height, "retained": unique.height},
                  "filter": {"records": unique.height, **labels},
                  "extraction": {"records": labels["accident"], "sources": catalog["source"].n_unique()},
                  "gold": {"input": batch.get("input", 0), "articles": bc.get("articles", 0),
                           "events": bc.get("accident_events", 0), "event_articles": bc.get("event_articles", 0),
                           "unassigned_articles": bc.get("unassigned_articles", 0), "pending_reviews": bc.get("pending_reviews", 0)},
                  "streaming": {"receipts": stream.get("receipts", 0), "articles": sc.get("articles", 0),
                                "events": sc.get("accident_events", 0), "pending_reviews": sc.get("pending_reviews", 0)},
                  "kafka": state_counts}
        manifest = {"path": generation.relative_to(archive).as_posix(), "architecture": "A2", "topic": settings["topic"],
                    "run_id": settings["run_id"], "revision": revision, "batch_revision": batch_revision,
                    "published_at": datetime.now(timezone.utc).isoformat(), "articles": catalog.height,
                    "sources": catalog["source"].n_unique(), "unique_articles": unique.height,
                    "review_overrides_applied": catalog.filter(pl.col("review_override_applied")).height,
                    "pipeline_counts": counts, "streaming": counts["streaming"], "batch": batch,
                    "date_min": str(catalog["pub_date"].min()), "date_max": str(catalog["pub_date"].max()),
                    "coverage": "All Bronze history through Kafka, full filter/extraction and event matching; immutable dashboard snapshot"}
        atomic_json(generation / "manifest.json", manifest)
        atomic_json(archive / "dashboard_current.json", manifest)
        return manifest
