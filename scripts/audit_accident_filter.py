"""Save a reproducible filter baseline and independently retrieve possible misses."""
from pathlib import Path
from collections import Counter
import json
import re

import polars as pl

from config import DATA_ARTIFACTS_DIR, FILTERED_DATA_DIR
from filters.accident import normalize, description_lead


EVENT = re.compile(r"tai nạn|tngt|va chạm|va quẹt|tông|đâm|đụng|húc|cán|lật|mất lái|mất phanh|gặp nạn|gây nạn|bốc cháy|cháy rụi|bốc lửa|văng|lao xuống|rơi xuống|sập cầu|cầu sập|gãy cầu|cây đổ|cây gãy|đè trúng|rơi trúng|chết|tử vong|thiệt mạng|thương vong|nguy kịch|thoát chết|thoát nạn")
VEHICLE = re.compile(r"\bxe\b|ô tô|ôtô|mô tô|môtô|taxi|container|cao tốc|quốc lộ|đường bộ|giao thông|tài xế|người đi bộ|đường sắt|tàu hỏa|tàu hoả")


def main():
    output = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117"
    output.mkdir(parents=True, exist_ok=True)
    baseline = output / "before_classified.parquet"
    if baseline.exists():
        frame = pl.read_parquet(baseline)
    else:
        frame = pl.concat([pl.read_parquet(p) for p in sorted(Path(FILTERED_DATA_DIR).glob("*/classified.parquet"))], how="diagonal_relaxed")
        frame.write_parquet(baseline)
    candidates = []
    for row in frame.iter_rows(named=True):
        title = normalize(row["title"])
        lead = description_lead(row.get("description"))
        body = normalize(row.get("content"))
        tier = None
        if EVENT.search(title) and VEHICLE.search(title + " " + lead):
            tier = "headline"
        elif EVENT.search(lead) and VEHICLE.search(title + " " + lead):
            tier = "lead"
        elif EVENT.search(body) and VEHICLE.search(title + " " + lead + " " + body):
            tier = "body"
        if row["accident_label"] == "accident" or tier:
            row["audit_tier"] = "accepted" if row["accident_label"] == "accident" else tier
            candidates.append(row)
    retrieved = pl.DataFrame(candidates, infer_schema_length=None)
    retrieved.write_parquet(output / "review_candidates.parquet")
    retrieved.select(["article_key", "source", "title", "description", "link", "accident_label", "filter_reason", "audit_tier"]).write_csv(output / "review_candidates.csv")
    summary = {"baseline_rows": frame.height, "labels": dict(Counter(frame["accident_label"].to_list())),
               "candidate_tiers": dict(Counter(row["audit_tier"] for row in candidates)),
               "note": "Broad independent retrieval only; candidates are not confirmed accident labels."}
    (output / "baseline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
