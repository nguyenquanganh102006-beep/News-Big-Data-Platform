"""Freeze real historical Silver, with provenance; never invent 20K accidents."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import polars as pl
from config import DATA_ARTIFACTS_DIR


def main():
    base = Path(__file__).resolve().parent
    source = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117/full_review/reviewed_classified.parquet"
    extraction = Path(DATA_ARTIFACTS_DIR) / "extraction_review_20261117/after.parquet"
    frame = pl.read_parquet(source).sort(["pub_date", "article_key"], nulls_last=True)
    assert frame["article_key"].n_unique() == frame.height
    extracted = {row["article_key"]: row for row in pl.read_parquet(extraction).iter_rows(named=True)}
    target = base / "data"
    target.mkdir(exist_ok=True)
    output = target / "articles.jsonl"
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for original in frame.iter_rows(named=True):
            facts = extracted.get(original["article_key"], {})
            row = {key: original.get(key) or "" for key in ("article_key", "source", "title", "description", "content", "accident_label")}
            row["published_at"] = str(original.get("pub_date") or "")
            for key in ("province", "fatalities", "injuries"):
                row[key] = facts.get(key)
            row["event_id"] = None
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    metadata = {
        "articles": frame.height, "labels": frame.group_by("accident_label").len().to_dicts(),
        "sources": frame["source"].n_unique(), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "extraction_sha256": hashlib.sha256(extraction.read_bytes()).hexdigest(),
        "scope": "Kafka -> JSON parse -> identical Python/Polars transform -> commit. No runtime filtering, extraction, embedding or event matching.",
        "dataset": "Real reviewed historical Silver articles; extraction precomputed for 357 candidate articles. event_id unknown, not fabricated.",
        "workloads": {"smoke": 100, "T1": 1000, "T2": 10000, "T3": 20000},
    }
    assert frame.height >= 20000
    (target / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
