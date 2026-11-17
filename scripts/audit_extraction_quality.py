"""Reproduce extraction checks on the frozen 322+35 reviewed articles."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import polars as pl

from config import DATA_ARTIFACTS_DIR
from extractors.accident import extract_frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["baseline", "after"])
    args = parser.parse_args()
    output = Path(DATA_ARTIFACTS_DIR) / "extraction_review_20261117"
    output.mkdir(parents=True, exist_ok=True)
    source = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117/full_review/reviewed_classified.parquet"
    input_path = output / "input_357.parquet"
    if not input_path.exists():
        frame = pl.read_parquet(source).filter(pl.col("accident_label").is_in(["accident", "uncertain"])).sort("article_key")
        assert frame.height == frame["article_key"].n_unique() == 357
        assert frame.filter(pl.col("accident_label") == "accident").height == 322
        frame.write_parquet(input_path)
    frame = pl.read_parquet(input_path)
    path = output / f"{args.stage}.parquet"
    if args.stage == "baseline" and path.exists():
        result = pl.read_parquet(path)
    else:
        result = extract_frame(frame)
        result.write_parquet(path)
    fields = ["article_key", "source", "title", "description", "link", "accident_label",
              "province", "district", "ward", "vehicles", "fatalities", "injuries",
              "incident_types", "evidence_json", "review_reasons", "extraction_version"]
    result.select([pl.col(c).map_elements(lambda values: json.dumps(values.to_list(), ensure_ascii=False), return_dtype=pl.String) if result[c].dtype.base_type() == pl.List else pl.col(c)
                   for c in fields]).write_csv(output / f"{args.stage}.csv")
    stats = {"rows": result.height, "labels": dict(Counter(frame["accident_label"])),
             "missing_body": frame.filter(pl.col("content").fill_null("").str.strip_chars() == "").height,
             "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
             "version": result["extraction_version"].unique().to_list(),
             "coverage": {}, "flags": dict(Counter(flag for flags in result["review_reasons"] for flag in flags)),
             "note": "Coverage is not accuracy. Network dateline enrichment is not fetched in this offline comparison."}
    for c in ["province", "district", "ward", "fatalities", "injuries"]:
        stats["coverage"][c] = result[c].is_not_null().sum()
    for c in ["vehicles", "incident_types"]:
        stats["coverage"][c] = (result[c].list.len() > 0).sum()
    (output / f"{args.stage}_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
