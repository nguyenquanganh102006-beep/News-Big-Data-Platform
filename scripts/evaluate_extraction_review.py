"""Field-level regression references and full-corpus extraction audit ledger.

References cover selected explicitly supported facts, not every field in an
article. This is a targeted regression set, not an unbiased accuracy estimate.
"""
import json
from pathlib import Path

import polars as pl

from config import DATA_ARTIFACTS_DIR


REFERENCES = {
    0: {"province": "TP Hồ Chí Minh"},
    1: {"province": "Đồng Tháp", "ward": "Thới Sơn", "fatalities": 1, "injuries": 2},
    2: {"province": "Hà Nội", "fatalities": 1, "vehicles": ["xe máy", "xe buýt"]},
    3: {"fatalities": 1},
    6: {"fatalities": None, "injuries": None},
    8: {"fatalities": None, "injuries": None},
    9: {"province": "Thanh Hóa"},
    10: {"ward": "Núi Thành"},
    12: {"injuries": 2},
    100: {"province": "Hà Tĩnh", "ward": "Kỳ Văn"},
    103: {"province": "Gia Lai", "fatalities": 4, "injuries": 5},
    104: {"fatalities": 1},
    175: {"ward": "Ngãi Giao"},
    176: {"fatalities": None, "injuries": None},
    177: {"fatalities": 1},
    179: {"fatalities": 1},
    180: {"injuries": 2},
    250: {"province": "Đồng Tháp"},
    252: {"fatalities": 1, "vehicles": ["xe máy", "tàu hỏa"]},
    254: {"fatalities": 1},
    350: {"fatalities": 1, "injuries": 1},
    353: {"ward": "M'Đrắk"},
    355: {"fatalities": None, "injuries": None},
    356: {"fatalities": 1},
}


def main():
    directory = Path(DATA_ARTIFACTS_DIR) / "extraction_review_20261117"
    before = pl.read_parquet(directory / "baseline.parquet")
    after = pl.read_parquet(directory / "after.parquet")
    assert before["article_key"].to_list() == after["article_key"].to_list()
    references, ledger = [], []
    fields = ["province", "district", "ward", "vehicles", "fatalities", "injuries", "incident_types"]
    for index, (old, new) in enumerate(zip(before.iter_rows(named=True), after.iter_rows(named=True))):
        changes = {field: {"before": old[field], "after": new[field]}
                   for field in fields if old[field] != new[field]}
        flags = new["review_reasons"]
        # Every row is checked; these are integrity checks, not semantic truth.
        assert new["accident_label"] == old["accident_label"]
        assert new.get("content") == old.get("content")
        for field in ("fatalities", "injuries"):
            assert new[field] is None or new[field] >= 0
            if "multiple_events_in_article" in flags:
                assert new[field] is None
            if f"conflicting_{field}" in flags:
                assert new[field] is None
        if new["accident_label"] == "uncertain":
            assert "upstream_scope_uncertain" in flags
        ledger.append({"article_key": new["article_key"], "title": new["title"],
                       "scope_label": new["accident_label"], "changed": bool(changes),
                       "changes_json": json.dumps(changes, ensure_ascii=False),
                       "review_reasons": json.dumps(flags, ensure_ascii=False),
                       "review_mode": "targeted_source_excerpt" if index in REFERENCES else "automated_integrity_only"})
        for field, expected in REFERENCES.get(index, {}).items():
            references.append({"article_key": new["article_key"], "title": new["title"],
                               "field": field, "expected": expected,
                               "before": old[field], "after": new[field],
                               "before_pass": old[field] == expected, "after_pass": new[field] == expected})
    pl.DataFrame(ledger).write_csv(directory / "review_ledger_357.csv")
    (directory / "targeted_references.json").write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"rows_integrity_checked": len(ledger), "changed_articles": sum(x["changed"] for x in ledger),
               "targeted_reference_articles": len(REFERENCES), "reference_field_checks": len(references),
               "baseline_pass": sum(x["before_pass"] for x in references),
               "after_pass": sum(x["after_pass"] for x in references),
               "failures": [x for x in references if not x["after_pass"]],
               "limitation": "Targeted regression checks only; not population precision or recall. Other rows have automated integrity checks, not manual semantic approval."}
    (directory / "evaluation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
