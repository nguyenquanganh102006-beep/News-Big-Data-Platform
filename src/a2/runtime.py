"""Single-owner A2 service: Bronze outbox, real Kafka, shared streaming and batch."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import time

from kafka import KafkaConsumer, TopicPartition
import polars as pl

from config import RSS_SOURCES
from crawlers.rss_crawler import crawl_rss_sources
from events.locking import writer_lock
from .config import current, HOME, BOOTSTRAP, atomic_json
from .producer import ensure_topic, publish_bronze
from .state import State
from .processing import prepare, review_annotations, version
from .projection import stream_projection, canonical_projection
from .publish import publish

STOP = HOME / "stop.request"
STATUS = HOME / "live_status.json"


def crawl_once():
    results, errors = {}, {}
    def fetch_source(source):
        for attempt in range(3):
            try:
                return crawl_rss_sources([source])
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch_source, source): source for source in RSS_SOURCES}
        for future in as_completed(futures):
            source = futures[future]
            try:
                results.update(future.result())
            except Exception as error:
                errors[source] = str(error)
    return {"sources": results, "errors": errors, "records": sum(row["records"] for row in results.values())}


class Runtime:
    def __init__(self, settings, batch_seconds=900, enrich=True):
        self.settings, self.batch_seconds, self.enrich = settings, batch_seconds, enrich
        ensure_topic(settings["topic"])
        self.state = State(settings["state"])
        self.consumer = KafkaConsumer(bootstrap_servers=BOOTSTRAP, group_id=settings["group"],
                                      api_version_auto_timeout_ms=15000,
                                      enable_auto_commit=False, auto_offset_reset="none", max_poll_records=512,
                                      max_poll_interval_ms=1800000, max_partition_fetch_bytes=8388608,
                                      request_timeout_ms=40000, session_timeout_ms=30000)
        self.tp = TopicPartition(settings["topic"], 0)
        self.consumer.assign([self.tp])
        self.last_ack = self.consumer.committed(self.tp) or 0
        self.consumer.seek(self.tp, self.last_ack)
        # One-time upgrade of the first journal format: re-read retained Bronze
        # envelopes to reconcile capture ordering and populate offset fingerprints.
        if self.state.db.execute("SELECT count(*) FROM kafka_messages WHERE message_fingerprint IS NULL").fetchone()[0]:
            self.consumer.seek(self.tp, 0)
            self.last_ack = 0
        self.annotations = review_annotations()
        self.last_batch = 0.0
        previous = HOME / settings["run_id"] / "materialization.json"
        self.stats = json.loads(previous.read_text(encoding="utf-8")) if previous.exists() else {}
        stamp_file = Path(settings["silver"]) / "processing_version.json"
        if not stamp_file.exists() or json.loads(stamp_file.read_text())["version"] != version():
            for key in ("stream_revision", "batch_revision", "published_revision"):
                self.state.mark(key, -1)
        self.heartbeat("starting")

    def heartbeat(self, phase, **extra):
        value = {"architecture": "A2", "pid": os.getpid(), "run_id": self.settings["run_id"],
                 "phase": phase, "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                 "topic": self.settings["topic"], "revision": self.state.meta("revision"),
                 "stream_revision": self.state.meta("stream_revision"), "batch_revision": self.state.meta("batch_revision"),
                 "counts": self.state.counts(), **extra}
        atomic_json(STATUS, value)
        return value

    def outbox(self):
        self.heartbeat("publishing_bronze")
        result = publish_bronze(self.settings)
        inventory = json.loads(Path(self.settings["outbox"]).read_text(encoding="utf-8"))
        self.stats["bronze_inventory"] = {"records": sum(row["rows"] for row in inventory.values()),
                                         "snapshots": len(inventory), "sources": len({key.split('/')[0] for key in inventory})}
        return result

    def materialize(self, force_batch=False):
        revision = self.state.meta("revision")
        cache = Path(self.settings["silver"]) / "catalog.parquet"
        stream_changed = self.state.meta("stream_revision") != revision or not cache.exists()
        due = force_batch or time.monotonic() - self.last_batch >= self.batch_seconds or not Path(self.settings["canonical"]).exists()
        if (not stream_changed and self.state.meta("published_revision") == revision
                and not (due and self.state.meta("batch_revision") != revision)):
            if due:
                self.last_batch = time.monotonic()
            return None
        if stream_changed:
            self.heartbeat("dedup_filter_extract", target_revision=revision)
            frame = self.state.frame()
            if frame.is_empty():
                return None
            catalog, paths = prepare(frame, self.settings["silver"], self.annotations, self.enrich)
            self.heartbeat("stream_matching", target_revision=revision)
            self.stats["stream"] = stream_projection(paths, catalog, self.settings["stream"])
            atomic_json(HOME / self.settings["run_id"] / "materialization.json", self.stats)
            self.state.mark("stream_revision", revision)
        else:
            catalog = pl.read_parquet(cache)
            paths = {source: Path(self.settings["silver"]) / "accidents" / f"{source}.parquet" for source in RSS_SOURCES}
        batch_changed = due and self.state.meta("batch_revision") != revision
        if batch_changed:
            self.heartbeat("batch_matching", target_revision=revision)
            self.stats["batch"] = canonical_projection(paths, self.settings["canonical"])
            atomic_json(HOME / self.settings["run_id"] / "materialization.json", self.stats)
            self.state.mark("batch_revision", revision)
        if due:
            self.last_batch = time.monotonic()
        atomic_json(HOME / self.settings["run_id"] / "materialization.json", self.stats)
        if stream_changed or batch_changed or self.state.meta("published_revision") != revision:
            self.heartbeat("publishing_dashboard")
            metadata = publish(self.settings, catalog, self.state.counts(), self.stats, revision, self.state.meta("batch_revision"))
            self.state.mark("published_revision", revision)
            return metadata
        return None

    def drain(self, force_batch=True):
        target = self.consumer.end_offsets([self.tp])[self.tp]
        totals = {"received": 0, "inserted": 0, "updated": 0, "unchanged": 0, "replayed": 0, "quarantined": 0}
        while self.consumer.position(self.tp) < target:
            messages = self.consumer.poll(timeout_ms=1000, max_records=512)
            # Poll can include messages produced after the initial watermark;
            # process every returned record before committing its position.
            records = [record for group in messages.values() for record in group]
            if not records:
                continue
            stats = self.state.ingest(records)
            for key, count in stats.items():
                totals[key] += count
            self.heartbeat("consuming", kafka_target=target, kafka_position=self.consumer.position(self.tp), batch=stats)
            print(f"[A2 Consume] {self.consumer.position(self.tp)}/{target} {stats}", flush=True)
        metadata = self.materialize(force_batch)
        # All journal + Silver + provisional projection commits have succeeded.
        # A crash before this point replays Kafka records; the offset ledger is idempotent.
        self.consumer.commit()
        self.last_ack = self.consumer.position(self.tp)
        self.heartbeat("ready", kafka_target=target, kafka_committed=self.last_ack, lag=0)
        return {"consumed": totals, "counts": self.state.counts(), "kafka_target": target,
                "kafka_committed": self.last_ack, "dashboard": metadata}

    def live_tick(self):
        messages = self.consumer.poll(timeout_ms=1000, max_records=512)
        records = [record for group in messages.values() for record in group]
        if records:
            self.state.ingest(records)
        self.materialize(False)
        if records:
            self.consumer.commit()
            self.last_ack = self.consumer.position(self.tp)
        self.heartbeat("running", kafka_committed=self.last_ack)

    def warm_models(self):
        from events.run import load_silver_articles
        from events.similarity import TextModel
        from config import MatchConfig
        paths = {source: Path(self.settings["silver"]) / "accidents" / f"{source}.parquet" for source in RSS_SOURCES}
        if not all(path.exists() for path in paths.values()):
            return
        self.heartbeat("warming_matching")
        articles = load_silver_articles(paths)
        config = MatchConfig()
        TextModel([article["text"] for article in articles], semantic_model=config.semantic_model,
                  cache_dir=config.semantic_cache_dir)

    def close(self):
        self.heartbeat("stopped")
        self.consumer.close()
        self.state.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="New Kafka namespace and derived generation; original Bronze stays intact")
    parser.add_argument("--history", action="store_true", help="Replay all Bronze snapshots (never Silver) before watching live")
    parser.add_argument("--crawl-once", action="store_true")
    parser.add_argument("--once", action="store_true", help="Drain/publish and exit instead of running the continuous service")
    parser.add_argument("--stop", action="store_true", help="Request graceful shutdown of the current A2 service")
    parser.add_argument("--crawl-seconds", type=int, default=300)
    parser.add_argument("--scan-seconds", type=int, default=5)
    parser.add_argument("--batch-seconds", type=int, default=900)
    parser.add_argument("--no-network-enrichment", action="store_true")
    args = parser.parse_args()
    if min(args.crawl_seconds, args.scan_seconds, args.batch_seconds) < 1:
        parser.error("schedule intervals must be positive")
    HOME.mkdir(parents=True, exist_ok=True)
    if args.stop:
        STOP.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        print("A2 graceful stop requested; the active transaction/projection will finish first.")
        return
    with writer_lock(HOME / "runtime"):
        STOP.unlink(missing_ok=True)
        settings = current(args.rebuild)
        runtime = Runtime(settings, args.batch_seconds, not args.no_network_enrichment)
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, stop)
        progress = {"run_id": settings["run_id"], "settings": settings, "started_at": datetime.now(timezone.utc).isoformat()}
        try:
            progress["history_producer"] = runtime.outbox()
            progress["history"] = runtime.drain(True)
            atomic_json(HOME / "last_run.json", progress)
            if args.crawl_once:
                runtime.heartbeat("crawling_new")
                progress["new_crawl"] = crawl_once()
                atomic_json(HOME / "last_crawl.json", progress["new_crawl"])
                progress["new_producer"] = runtime.outbox()
                progress["new_data"] = runtime.drain(True)
                atomic_json(HOME / "last_run.json", progress)
            if args.once:
                progress["completed_at"] = datetime.now(timezone.utc).isoformat()
                atomic_json(HOME / "last_run.json", progress)
                print(json.dumps(progress, ensure_ascii=False, default=str), flush=True)
                return
            runtime.warm_models()
            last_scan = last_crawl = time.monotonic()
            # Slow RSS sites must not block Kafka consumption or the batch clock.
            with ThreadPoolExecutor(max_workers=1) as crawl_pool:
                crawl_job = None
                while not stopping and not STOP.exists():
                    try:
                        now = time.monotonic()
                        if now - last_crawl >= args.crawl_seconds and crawl_job is None:
                            crawl_job = crawl_pool.submit(crawl_once)
                        if crawl_job is not None and crawl_job.done():
                            try:
                                atomic_json(HOME / "last_crawl.json", crawl_job.result())
                            except Exception as error:
                                atomic_json(HOME / "last_crawl.json", {"sources": {}, "errors": {"crawler": repr(error)}})
                            finally:
                                crawl_job = None
                                last_crawl = time.monotonic()
                        if now - last_scan >= args.scan_seconds:
                            runtime.outbox()
                            last_scan = time.monotonic()
                        runtime.live_tick()
                    except Exception as error:
                        runtime.heartbeat("retrying", error=repr(error))
                        print(f"[A2 Retry] {error!r}", flush=True)
                        # Restore the last ACK; durable journal/projection flags
                        # permit retry after a crash between DB commit and ACK.
                        runtime.consumer.seek(runtime.tp, runtime.last_ack)
                        time.sleep(5)
        except BaseException as error:
            progress["error"] = repr(error)
            atomic_json(HOME / "last_run.json", progress)
            raise
        finally:
            runtime.close()


if __name__ == "__main__":
    main()
