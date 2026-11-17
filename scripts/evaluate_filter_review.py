"""Compare rules on the frozen real-data review set; never treat unreviewed rows as truth."""
from collections import Counter
import json
from pathlib import Path

import polars as pl

from config import DATA_ARTIFACTS_DIR
from filters.accident import classify_accident


def main():
    output = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117"
    baseline = pl.read_parquet(output / "before_classified.parquet")
    rows = []
    for index, row in enumerate(baseline.iter_rows(named=True), 1):
        decision = classify_accident(row["title"], row.get("description"), row.get("content"))
        rows.append({"article_key": row["article_key"], "source": row["source"],
                     "title": row["title"], "description": row.get("description"), "link": row["link"],
                     "before": row["accident_label"], "before_reason": row["filter_reason"],
                     "after": decision.label, "after_reason": decision.reason,
                     "after_evidence": decision.evidence, "version": decision.version})
        if index % 5000 == 0:
            print(f"[Filter evaluation] {index}/{baseline.height}", flush=True)
    predictions = pl.DataFrame(rows)
    predictions.write_parquet(output / "after_predictions.parquet")
    classified = baseline.drop([c for c in ("accident_label", "filter_reason", "filter_evidence", "filter_version") if c in baseline.columns]).join(
        predictions.select("article_key", pl.col("after").alias("accident_label"), pl.col("after_reason").alias("filter_reason"),
                           pl.col("after_evidence").alias("filter_evidence"), pl.col("version").alias("filter_version")), on="article_key", how="left")
    classified.write_parquet(output / "classified_v4.parquet")
    changes = predictions.filter(pl.col("before") != pl.col("after"))
    changes.write_csv(output / "changed_articles.csv")
    predictions.filter(pl.col("before") == "accident").write_csv(output / "review_original_325.csv")
    predictions.filter((pl.col("before") != "accident") & (pl.col("after") == "accident")).write_csv(output / "found_missed_accidents.csv")
    predictions.filter((pl.col("before") == "accident") & (pl.col("after") != "accident")).write_csv(output / "removed_original_accidents.csv")
    predictions.filter(pl.col("after") == "uncertain").write_csv(output / "remaining_review.csv")
    labels_path = output / "review_labels.csv"
    summary = {"rows": baseline.height, "before": dict(Counter(baseline["accident_label"].to_list())),
               "after": dict(Counter(row["after"] for row in rows)),
               "transitions": {f"{before}->{after}": count for (before, after), count in Counter((r['before'], r['after']) for r in rows).items()}}
    if labels_path.exists():
        labels = pl.read_csv(labels_path).select("article_key", "review_label", "review_reason")
        reviewed = predictions.join(labels, on="article_key", how="inner")
        reviewed.write_csv(output / "reviewed_predictions.csv")
        annotated = predictions.join(labels, on="article_key", how="left")
        annotated.filter(pl.col("before") == "accident").write_csv(output / "review_original_325.csv")
        annotated.filter((pl.col("before") != "accident") & (pl.col("after") == "accident")).write_csv(output / "found_missed_accidents.csv")
        annotated.filter((pl.col("before") == "accident") & (pl.col("after") != "accident")).write_csv(output / "removed_original_accidents.csv")
        annotated.filter((pl.col("before") == "accident") & (pl.col("review_label") == "not_accident")).write_csv(output / "confirmed_non_accidents_original_325.csv")
        annotated.filter((pl.col("before") != "accident") & (pl.col("review_label") == "accident")).write_csv(output / "confirmed_missed_accidents.csv")
        annotated.filter(pl.col("review_label") == "accident").write_csv(output / "confirmed_accident_articles.csv")
        annotated.filter((pl.col("after") == "uncertain") | (pl.col("review_label") == "uncertain")).write_csv(output / "priority_review.csv")
        known = reviewed.filter(pl.col("review_label").is_in(["accident", "not_accident"]))
        for field in ["before", "after"]:
            tp = known.filter((pl.col(field) == "accident") & (pl.col("review_label") == "accident")).height
            fp = known.filter((pl.col(field) == "accident") & (pl.col("review_label") == "not_accident")).height
            fn = known.filter((pl.col(field) != "accident") & (pl.col("review_label") == "accident")).height
            summary[field + "_reviewed_metrics"] = {"tp": tp, "fp": fp, "fn": fn,
                                                      "precision": tp / (tp + fp) if tp + fp else None,
                                                      "recall": tp / (tp + fn) if tp + fn else None}
        summary["reviewed_rows"] = reviewed.height
        summary["known_labels"] = known.height
        summary["metrics_scope"] = "Targeted reviewed subset; not a random or independent estimate for all 20k articles."
    (output / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
