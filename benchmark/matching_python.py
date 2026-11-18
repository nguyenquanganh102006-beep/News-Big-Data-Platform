"""Separate production Python matching timing; never fold this into A2/A4/A5."""
import argparse
import csv
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from batch.run import run_batch
from config import DATA_ARTIFACTS_DIR, MatchConfig
from events.run import load_silver_articles
from events.similarity import TextModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    phase = base / "work/phase.json"
    if phase.exists() and json.loads(phase.read_text()).get("active"):
        raise RuntimeError("Wait for architecture suite to finish before matching benchmark")
    source = Path(DATA_ARTIFACTS_DIR) / "extraction_review_20261117/after.parquet"
    work = base / "work" / ("matching-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    work.mkdir(parents=True, exist_ok=False)
    frame = pl.read_parquet(source).filter(pl.col("accident_label") == "accident")
    assert frame.height == 322
    paths = {}
    for (name,), partition in frame.partition_by("source", as_dict=True).items():
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("Invalid source filename")
        path = work / f"{name}.parquet"
        partition.write_parquet(path)
        paths[name] = path
    config = MatchConfig()
    tick = time.perf_counter()
    articles = load_silver_articles(paths)
    model = TextModel([a["text"] for a in articles], semantic_model=config.semantic_model,
                      cache_dir=config.semantic_cache_dir)
    warmup_s = time.perf_counter() - tick
    metadata = {"scope": "Python production canonical batch matching only, on Windows host. No Kafka/Spark comparison. Load/fit/retrieval/scoring/aggregation/storage are included; embedding caches prewarmed.",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "articles": len(articles),
                "config": asdict(config), "model_fingerprint": model.fingerprint, "warmup_s": warmup_s}
    (work / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    results = []
    for index in range(args.repeats):
        tick = time.perf_counter()
        stats = run_batch(paths, work / f"matching_{index}.duckdb", config=config)
        duration = time.perf_counter() - tick
        assert stats["input"] == 322
        assert stats["counts"]["event_articles"] + stats["counts"]["pending_reviews"] == 322
        row = {"repeat": index + 1, "input_count": 322, "duration_s": duration,
               "articles_s": 322 / duration, "new_event": stats["new_event"], "matched": stats["matched"],
               "needs_review": stats["needs_review"], "warmup_s_excluded": warmup_s,
               "model_fingerprint": model.fingerprint}
        results.append(row)
        (work / f"run_{index}.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(row), flush=True)
    assert len({(r["new_event"], r["matched"], r["needs_review"]) for r in results}) == 1
    output = base / "results/matching_python.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    (base / "results/matching_python_manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import socket
    with socket.socket() as suite_lock:
        suite_lock.bind(("127.0.0.1", 19666))
        main()
