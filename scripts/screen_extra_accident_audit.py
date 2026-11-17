"""Screen a frozen extra-5,000 selection; cues are retrieval, never truth labels."""
from pathlib import Path
import html
import json
import re
import unicodedata

import polars as pl

from config import DATA_ARTIFACTS_DIR


def fold(text):
    text = html.unescape(text or "").lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(c))


EVENT = re.compile(
    r"va quet|va cham|tong|dam (?:vao|trung|nhau)|can (?:qua|trung)|"
    r"(?:sup|sut|lot) ho|(?:nguoi|xe).{0,50}(?:truot nga|te nga|gap nan|tu nan)|"
    r"(?:roi|lat|lao|cuon).{0,50}(?:xe|o to|tai xe)|"
    r"(?:xe|o to|tai xe).{0,50}(?:roi|lat|lao|cuon|chay rui|boc chay|nghieng)|tai nan|tngt"
)
ACTOR = re.compile(r"\bxe\b|o to|oto|taxi|container|tai xe|nguoi di bo")
TOPIC = re.compile(
    r"khoi to|truy to|xet xu|tuyen an|xu phat|bi phat|bat.{0,25}(?:doi tuong|nghi pham)|"
    r"tham hoi|ho tro.{0,20}trieu|ra mat|doanh so|phan khuc|gia xe|mau xe|trieu hoi|"
    r"dien tap|thu nghiem|phong tranh|nguy co|canh bao|thong xe|khoi cong|du an|"
    r"sua chua|de xuat|quy dinh|chinh sach|thi truong|xe dien|xe hybrid|oto dien"
)


def main():
    base = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117"
    output = base / "extra_5000"
    selected = pl.read_parquet(output / "selected_5000.parquet")
    assert selected.height == selected["article_key"].n_unique() == 5000
    frame = selected.join(pl.read_parquet(base / "before_classified.parquet")
                          .select("article_key", "content"), on="article_key")
    rows = []
    for row in frame.iter_rows(named=True):
        title = fold(row["title"])
        opening = title + ". " + fold(row.get("description"))
        full = opening + ". " + fold(row.pop("content", None))
        contexts = []
        for match in EVENT.finditer(full):
            context = full[max(0, match.start() - 100):match.end() + 160]
            if ACTOR.search(context):
                contexts.append(context)
        row.update(event_context_count=len(contexts), evidence=" | ".join(contexts[:4]),
                   topic_flag=bool(TOPIC.search(title)), opening_event=bool(EVENT.search(opening)),
                   screen_result="needs_context" if contexts else "no_independent_event_cue")
        rows.append(row)
    result = pl.DataFrame(rows)
    result.write_parquet(output / "screened_5000.parquet")
    result.drop("description").write_csv(output / "screened_5000.csv")
    queue = result.filter((pl.col("event_context_count") > 0) & ~pl.col("topic_flag"))
    queue.sort(["opening_event", "audit_rank_score"], descending=True).write_csv(output / "context_queue.csv")
    summary = {"selected_unique": result.height,
               "full_text_cues": result.filter(pl.col("event_context_count") > 0).height,
               "no_independent_cue": result.filter(pl.col("event_context_count") == 0).height,
               "context_queue": queue.height,
               "limits": "Machine screening of available text; no-cue is not a verified negative."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
