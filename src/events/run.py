"""Read Silver articles and write the event database and exports into Gold."""

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import polars as pl

from config import (
    EVENT_INPUT_DIR, EXTRACT_SOURCES, EVENT_DATABASE_PATH, EVENT_EXPORT_DIR,
    MATCH_WEIGHTS, MATCH_VERSION, AGGREGATION_VERSION, MatchConfig,
)
from .adapter import REQUIRED_ARTICLE_COLUMNS, fingerprint, json_text, prepare_article
from .matching import decide_match
from .repository import EventRepository
from .similarity import TextModel


def load_silver_articles(input_paths):
    # Validate all files/schema/rows before opening a database for writes.
    for path in input_paths.values():
        if not Path(path).is_file():
            raise FileNotFoundError(f"Missing extracted Silver articles: {path}. Run extraction first (--step=4).")
    articles, seen = [], {}
    for source, path in sorted(input_paths.items()):
        frame = pl.read_parquet(path)
        missing = REQUIRED_ARTICLE_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"{path}: missing Silver article columns: {', '.join(sorted(missing))}")
        for index, row in enumerate(frame.iter_rows(named=True)):
            if row["source"] != source:
                raise ValueError(f"{path}: unexpected source in row {index}")
            article = prepare_article(row, reference=f"{path}:row={index}")
            key = article["article_key"]
            if key is not None and key in seen:
                if seen[key] != article["input_fingerprint"]:
                    raise ValueError(f"Conflicting Silver rows for article_key {key}")
                continue
            if key is not None:
                seen[key] = article["input_fingerprint"]
            articles.append(article)
    fallback = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(articles, key=lambda a: (a["published_at"] or fallback,
                                         a["article_key"] or a["input_fingerprint"]))


def run_events(input_paths=None, database_path=None, export_dir=None, config=None):
    paths = input_paths if input_paths is not None else {
        source: EVENT_INPUT_DIR / f"{source}.parquet" for source in EXTRACT_SOURCES
    }
    incoming = load_silver_articles(paths)
    config = config or MatchConfig()
    config_values = {**asdict(config), "weights": MATCH_WEIGHTS, "match_version": MATCH_VERSION}
    config_id = fingerprint(config_values)
    repo = EventRepository(database_path if database_path is not None else EVENT_DATABASE_PATH)
    stats = {"input": len(incoming), "new_event": 0, "matched": 0, "needs_review": 0,
             "already_processed": 0, "changed_input": 0, "updated_unassigned": 0,
             "updated_assigned": 0, "refreshed_events": 0}
    try:
        repo.initialize()
        repo.connection.execute("BEGIN TRANSACTION")
        try:
            stored = repo.read_articles()
            linked = dict(repo.connection.execute("SELECT article_key,event_id FROM event_articles").fetchall())
            updated_keys = set()
            affected_events = {event_id for (event_id,) in repo.connection.execute(
                "SELECT event_id FROM accident_events WHERE aggregation_version<>?", [AGGREGATION_VERSION]
            ).fetchall()}
            # Apply corrections first so retrieval for new articles sees the
            # corrected event data, irrespective of source/publication order.
            for article in incoming:
                key = article["article_key"]
                if key in linked and stored[key]["input_fingerprint"] != article["input_fingerprint"]:
                    repo.update_article(article, previous=stored[key])
                    stored[key] = article
                    repo.resolve_reviews(key)
                    updated_keys.add(key)
                    affected_events.add(linked[key])
                    stats["updated_assigned"] += 1
            for event_id in sorted(affected_events):
                repo.refresh_event(event_id, stored)
            stats["refreshed_events"] = len(affected_events)
            effective = dict(stored)
            effective.update({a["article_key"] or ("unkeyed", a["input_fingerprint"]): a
                              for a in incoming})
            model = TextModel([a["text"] for a in effective.values()])
            for article in incoming:
                key = article["article_key"]
                if key in updated_keys:
                    continue
                if key in stored:
                    if stored[key]["input_fingerprint"] != article["input_fingerprint"]:
                        repo.update_unassigned_article(article, previous=stored[key])
                        stored[key] = article
                        stats["updated_unassigned"] += 1
                    if key in linked:
                        # Any legacy changed_input review is obsolete once the
                        # current Silver version is already applied to this link.
                        repo.resolve_reviews(key)
                        stats["already_processed"] += 1
                        continue
                elif key is not None:
                    repo.insert_article(article)
                    stored[key] = article
                if key is not None:
                    repo.resolve_reviews(key)
                candidates = [] if article["reasons"] else repo.find_candidates(article, config, stored)
                decision = decide_match(article, candidates, model, config)
                decision.update(config_fingerprint=config_id, model_fingerprint=model.fingerprint)
                kind = decision["decision"]
                stats[kind] += 1
                if kind == "needs_review":
                    repo.save_review(article, decision)
                else:
                    event_id = repo.save_assignment(article, decision, config_id, model.fingerprint)
                    linked[key] = event_id
                    repo.refresh_event(event_id, stored)
            stats["database"] = repo.counts()
            repo.connection.execute(
                "INSERT INTO event_runs (run_id, summary, config, model_fingerprint) VALUES (?, ?, ?, ?)",
                [str(uuid4()), json_text(stats), json_text(config_values), model.fingerprint],
            )
            repo.connection.execute("COMMIT")
        except BaseException:
            repo.connection.execute("ROLLBACK")
            raise
        repo.export(export_dir if export_dir is not None else EVENT_EXPORT_DIR)
    finally:
        repo.close()
    print("[Events] " + json_text(stats))
    return stats


if __name__ == "__main__":
    run_events()
