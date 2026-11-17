"""Independent retrieval plus a reproducible random sample of rejected articles.

Ranking is an audit aid, not a calibrated probability or an automatic label.
"""
from pathlib import Path
import json
import re
import unicodedata

import numpy as np
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion

from config import DATA_ARTIFACTS_DIR
from filters.accident import normalize


def fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.replace("đ", "d")) if not unicodedata.combining(c))


ACTOR = re.compile(r"\b(?:xe|oto|o to|moto|mo to|taxi|container|nguoi di bo|tai xe|cabin|phuong tien)\b")
EVENT = re.compile(r"\b(?:tai nan|tngt|tu nan|va cham|va quet|tong|dam|huc|can|lat|truot nga|truc banh|roi banh|no lop|dut phanh|mat phanh|lot gam|quang|hat|quat|cuon|phi|lao|chay|boc lua|bep dum|vo nat|nam duong|chet|tu vong|thuong vong|thiet mang|bi thuong|gap nan|sap cau|cau sap)\b")


def main():
    base = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117"
    output = base / "deep_audit"
    output.mkdir(parents=True, exist_ok=True)
    frame = pl.read_parquet(base / "classified_v4.parquet").sort("article_key")
    labels = {r["article_key"]: r for r in pl.read_csv(base / "review_labels.csv").to_dicts()}
    documents, metadata = [], []
    for index, row in enumerate(frame.iter_rows(named=True), 1):
        title = normalize(row["title"])
        description = normalize(row.get("description"))
        body = normalize(row.get("content"))
        opening = title + ". " + description
        documents.append(title + ". " + opening + ". " + body[:1600])
        head = fold(opening)
        full = fold(opening + ". " + body)
        evidence = []
        for match in EVENT.finditer(full):
            context = full[max(0, match.start()-110):match.end()+110]
            if ACTOR.search(context):
                evidence.append(full[max(0, match.start()-100):match.end()+150])
        metadata.append({"article_key": row["article_key"], "source": row["source"],
                         "title": row["title"], "description": row.get("description"), "link": row["link"],
                         "filter_label": row["accident_label"], "filter_reason": row["filter_reason"],
                         "independent_headline_cue": bool(EVENT.search(fold(title)) and ACTOR.search(head)),
                         "independent_opening_cue": bool(EVENT.search(head) and ACTOR.search(head)),
                         "full_body_cue_count": len(evidence), "first_full_body_evidence": evidence[0] if evidence else "",
                         "previously_reviewed": row["article_key"] in labels})
        if index % 5000 == 0:
            print(f"[Deep audit] full-text scan {index}/{frame.height}", flush=True)
    print("[Deep audit] fit independent title/lead/body ranking model", flush=True)
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=80000, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=80000, sublinear_tf=True)),
    ])
    vectors = features.fit_transform(documents)
    train = [i for i, row in enumerate(metadata) if labels.get(row["article_key"], {}).get("review_label") in ("accident", "not_accident")]
    target = np.array([labels[metadata[i]["article_key"]]["review_label"] == "accident" for i in train])
    model = LogisticRegression(class_weight="balanced", max_iter=500, random_state=20261117)
    model.fit(vectors[train], target)
    scores = model.decision_function(vectors)
    for row, score in zip(metadata, scores):
        row["audit_rank_score"] = float(score)
    results = pl.DataFrame(metadata)
    results.write_parquet(output / "all_article_scan.parquet")
    rejected = results.filter(pl.col("filter_label") != "accident")
    # Keep previously reviewed cases for coverage, but rank new cases separately.
    new = rejected.filter(~pl.col("previously_reviewed"))
    ranked = new.sort("audit_rank_score", descending=True)
    ranked.head(400).write_csv(output / "model_top_400.csv")
    new.filter(pl.col("independent_headline_cue")).sort("audit_rank_score", descending=True).write_csv(output / "headline_candidates.csv")
    new.filter(pl.col("independent_opening_cue")).sort("audit_rank_score", descending=True).write_csv(output / "opening_candidates.csv")
    new.filter(pl.col("full_body_cue_count") > 0).sort("audit_rank_score", descending=True).write_csv(output / "body_candidates.csv")
    rejected.filter(pl.col("filter_label") == "uncertain").write_csv(output / "all_33_uncertain.csv")
    # Uniform sample from all rejected rows, irrespective of keywords or model score.
    sample = rejected.sample(n=min(200, rejected.height), seed=20261117)
    sample.write_csv(output / "random_200_rejected.csv")
    summary = {"scanned": results.height, "rejected_or_uncertain": rejected.height,
               "previously_reviewed": int(results["previously_reviewed"].sum()),
               "unreviewed_headline_candidates": new.filter(pl.col("independent_headline_cue")).height,
               "unreviewed_opening_candidates": new.filter(pl.col("independent_opening_cue")).height,
               "unreviewed_full_body_candidates": new.filter(pl.col("full_body_cue_count") > 0).height,
               "model_review_queue": min(400, new.height), "random_rejected_sample": sample.height,
               "ranking_training_rows": len(train), "random_seed": 20261117,
               "note": "Independent candidate ranking only, no calibrated probabilities or accuracy claim. Random sample is unfiltered by retrieval cues."}
    (output / "coverage.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
