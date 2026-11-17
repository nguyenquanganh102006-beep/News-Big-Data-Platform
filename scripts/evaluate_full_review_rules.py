"""Evaluate rules on frozen audit shards, without publishing production layers."""
from collections import Counter
from pathlib import Path
import json

import polars as pl

from config import DATA_ARTIFACTS_DIR
from filters.accident import classify_accident


def main():
    directory = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117" / "full_review"
    baseline = pl.concat([pl.read_parquet(directory / f"shard_{i}.parquet") for i in range(1, 4)])
    assert baseline.height == baseline["article_key"].n_unique() == 20745
    rows = []
    for index, row in enumerate(baseline.iter_rows(named=True), 1):
        decision = classify_accident(row["title"], row.get("description"), row.get("content"))
        rows.append({"article_key": row["article_key"], "rules_label": decision.label,
                     "rules_reason": decision.reason, "rules_evidence": decision.evidence,
                     "rules_version": decision.version})
        if index % 5000 == 0:
            print(f"Rules evaluation: {index}/20745", flush=True)
    result = baseline.join(pl.DataFrame(rows), on="article_key")
    result.write_parquet(directory / "rules_evaluation.parquet")
    changes = result.filter(pl.col("current_label") != pl.col("rules_label"))
    changes.drop("content").write_csv(directory / "rules_changes.csv")
    summary = {"rows": result.height,
               "before": dict(Counter(result["current_label"].to_list())),
               "after": dict(Counter(result["rules_label"].to_list())),
               "changes": changes.height,
               "production_published": False}
    (directory / "rules_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
