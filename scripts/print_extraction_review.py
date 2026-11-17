"""Bounded source/evidence packets for reviewing each extraction by article key."""
import argparse
import re

import polars as pl

from config import DATA_ARTIFACTS_DIR
from pathlib import Path
from extractors.accident import clean_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("start", type=int)
    parser.add_argument("count", type=int)
    parser.add_argument("--stage", default="baseline")
    args = parser.parse_args()
    frame = pl.read_parquet(Path(DATA_ARTIFACTS_DIR) / f"extraction_review_20261117/{args.stage}.parquet")
    for index, row in enumerate(frame.slice(args.start, args.count).iter_rows(named=True), args.start):
        print(f"\n[{index}] {row['article_key'][:12]} {row['title']}")
        print("LEAD", clean_text(row.get("description"))[:420])
        print("EXTRACT", {c: row[c] for c in ["province", "district", "ward", "vehicles", "fatalities", "injuries", "incident_types"]})
        body = row.get("content") or ""
        lines = [clean_text(x) for x in re.split(r"\n|(?<=[.!?])\s+", body)]
        seen = set()
        selected = []
        for line in lines:
            if not line or line in seen:
                continue
            seen.add(line)
            if not selected or re.search(r"tử vong|thiệt mạng|bị thương|thương vong|tại km|xảy ra|phường|xã |quận|huyện|quê|trú|cao tốc", line, re.I):
                selected.append(line[:430])
            if sum(map(len, selected)) > 1700:
                break
        print("BODY", " | ".join(selected))


if __name__ == "__main__":
    main()
