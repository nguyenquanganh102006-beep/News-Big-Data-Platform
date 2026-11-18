"""Persist a root-read title batch after review; never use this to imply unread coverage."""
import argparse
from pathlib import Path

import polars as pl

from config import DATA_ARTIFACTS_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("start", type=int)
    parser.add_argument("stop", type=int)
    parser.add_argument("--accident", default="")
    parser.add_argument("--uncertain", default="")
    args = parser.parse_args()
    positive = {int(i) for i in args.accident.split(",") if i}
    uncertain = {int(i) for i in args.uncertain.split(",") if i}
    directory = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117" / "full_review"
    source = pl.read_parquet(directory / "root_remaining.parquet")
    path = directory / "review_root_remaining.csv"
    previous = pl.read_csv(path) if path.exists() else None
    seen = set(previous["article_key"]) if previous is not None else set()
    rows = []
    for index in range(args.start, args.stop):
        row = source.row(index, named=True)
        if row["article_key"] in seen:
            raise ValueError(f"Already reviewed: {index}")
        label = "accident" if index in positive else "uncertain" if index in uncertain else "not_accident"
        reason = {"accident": "Tiêu đề tường thuật một sự cố đường bộ cụ thể.",
                  "uncertain": "Cần đối chiếu nội dung/bối cảnh hoặc ranh giới phạm vi trước khi chốt.",
                  "not_accident": "Tiêu đề ngoài chủ đề tai nạn đường bộ hoặc thuộc phân tích, chính sách, hậu sự, xử lý sau vụ việc."}[label]
        rows.append({"root_index": index, "article_key": row["article_key"], "shard": row["shard"],
                     "review_label": label, "review_reason": reason, "review_basis": "title_only"})
    result = pl.DataFrame(rows)
    if previous is not None:
        result = pl.concat([previous, result], how="vertical_relaxed")
    result.write_csv(path)
    print(f"Root title coverage: {result.height}/{source.height}")


if __name__ == "__main__":
    main()
