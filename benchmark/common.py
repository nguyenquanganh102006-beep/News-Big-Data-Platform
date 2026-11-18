"""Identical deterministic transform shared by A2/A4/A5."""
import hashlib
import json
import time

import polars as pl

FIELDS = ["run_id", "article_key", "source", "published_at", "title", "content_hash",
          "province", "fatalities", "injuries", "event_id", "status", "sent_at", "processed_at"]
SQL_COLUMNS = "run_id VARCHAR, article_key VARCHAR, source VARCHAR, published_at VARCHAR, title VARCHAR, content_hash VARCHAR, province VARCHAR, fatalities BIGINT, injuries BIGINT, event_id VARCHAR, status VARCHAR, sent_at DOUBLE PRECISION, processed_at DOUBLE PRECISION"
QUERIES = {
    "articles_by_source": "SELECT source, count(*) AS n FROM output GROUP BY source ORDER BY source",
    "articles_by_status": "SELECT status, count(*) AS n FROM output GROUP BY status ORDER BY status",
    "articles_by_province_publication_day": "SELECT province, substr(published_at,1,10) AS day, count(*) AS n FROM output WHERE province IS NOT NULL GROUP BY province, substr(published_at,1,10) ORDER BY province, day",
}


def transform(rows):
    if not rows:
        return []
    frame = pl.DataFrame(rows, infer_schema_length=None).with_columns(
        pl.col("title").fill_null("").str.replace_all(r"\s+", " ").str.strip_chars(),
        pl.col("source").fill_null("").str.to_lowercase(),
    )
    results = []
    for row in frame.iter_rows(named=True):
        combined = "\n".join(row.get(k) or "" for k in ("title", "description", "content"))
        row["content_hash"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        row["status"] = row.get("accident_label") or "unknown"
        row["processed_at"] = time.time()
        results.append({k: row.get(k) for k in FIELDS})
    return results


def digest(rows):
    fields = [k for k in FIELDS if k not in ("run_id", "sent_at", "processed_at")]
    canonical = [{k: r[k] for k in fields} for r in sorted(rows, key=lambda r: r["article_key"])]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)
