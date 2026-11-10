"""Deterministic full rebuild; publish only a validated, closed staging database."""
import argparse
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import duckdb

from config import EVENT_INPUT_DIR, DATA_GOLD_DIR, EXTRACT_SOURCES
from events.adapter import json_text, fingerprint
from events.run import load_silver_articles
from events.service import MatchingService
from events.similarity import TextModel
from events.locking import writer_lock
from .repository import CanonicalRepository

DEFAULT_DATABASE = Path(DATA_GOLD_DIR) / "batch" / "canonical.duckdb"


def run_batch(input_paths=None, database_path=DEFAULT_DATABASE, config=None):
    paths = {source: Path(path) for source, path in (input_paths if input_paths is not None else {
        source: Path(EVENT_INPUT_DIR) / f"{source}.parquet" for source in EXTRACT_SOURCES
    }).items()}
    if not paths:
        raise ValueError("Explicit input sources are required")
    database = Path(database_path).resolve()
    if database in {p.resolve() for p in paths.values()}:
        raise ValueError("Output database must not overwrite an input")
    with writer_lock(database):
        if database.exists():
            with duckdb.connect(str(database), read_only=True) as existing:
                tables = {r[0] for r in existing.execute("SHOW TABLES").fetchall()}
                if not {"canonical_events", "canonical_event_schema"} <= tables or any(
                        not name.startswith("canonical_") for name in tables):
                    raise ValueError("Refusing to replace a database outside the canonical batch schema")
        # Hash before/after loading to reject concurrently changing input snapshots.
        manifest = [{"source": source, "path": str(p.resolve()),
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                    for source, p in sorted(paths.items())]
        incoming = load_silver_articles(paths)
        # Invalid-key payloads have no article identity; retain one identical payload for review.
        unique, seen = [], set()
        for article in incoming:
            identity = ("key", article["article_key"]) if article["article_key"] is not None else (
                "payload", article["input_fingerprint"])
            if identity not in seen:
                unique.append(article)
                seen.add(identity)
        incoming = unique
        for entry in manifest:
            if hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("Silver changed during input loading")
        if not incoming:
            raise ValueError("Empty Silver snapshot; refusing to replace canonical data")
        service = MatchingService(config)
        model = TextModel([a["text"] for a in incoming])
        stats = {"input": len(incoming), "new_event": 0, "matched": 0, "needs_review": 0,
                 "database_path": str(database), "input_manifest": manifest,
                 "input_fingerprint": fingerprint(manifest)}
        with TemporaryDirectory(prefix="canonical-stage-", dir=database.parent) as staging:
            staged = Path(staging) / "canonical.duckdb"
            repo = CanonicalRepository(staged)
            try:
                repo.initialize()
                repo.connection.execute("BEGIN TRANSACTION")
                try:
                    stored = {}
                    for article in incoming:
                        key = article["article_key"]
                        if key is not None:
                            repo.insert_article(article)
                            stored[key] = article
                        decision = service.decide(article, repo, stored, model)
                        stats[decision["decision"]] += 1
                        if decision["decision"] == "needs_review":
                            repo.save_review(article, decision)
                        else:
                            event_id = repo.save_assignment(article, decision, service.config_id, model.fingerprint)
                            repo.refresh_event(event_id, stored)
                    stats["counts"] = repo.counts()
                    counts = stats["counts"]
                    if counts["event_articles"] + counts["pending_reviews"] != len(incoming):
                        raise RuntimeError("Canonical input accounting failed")
                    repo.connection.execute(
                        "INSERT INTO event_runs (run_id,summary,config,model_fingerprint) VALUES (?,?,?,?)",
                        [str(uuid4()), json_text(stats), json_text(service.config_values), model.fingerprint])
                    repo.connection.execute("COMMIT")
                    repo.connection.execute("CHECKPOINT")
                except BaseException:
                    # Closing also rolls back when an error occurs before commit.
                    raise
            finally:
                repo.close()
            staged.replace(database)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path(EVENT_INPUT_DIR))
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--sources", nargs="+", default=list(EXTRACT_SOURCES),
                        help="Explicit subset of source filenames without .parquet")
    args = parser.parse_args()
    if any(Path(s).name != s or s in (".", "..") for s in args.sources):
        parser.error("sources must be simple filenames")
    result = run_batch({s: args.input_dir / f"{s}.parquet" for s in args.sources}, args.database)
    print(json_text(result))


if __name__ == "__main__":
    main()
