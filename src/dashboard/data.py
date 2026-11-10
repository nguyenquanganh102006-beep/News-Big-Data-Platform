"""Read the single published historical dataset and its event database."""
import json
from pathlib import Path

import duckdb
import pandas as pd
import polars as pl


def discover_datasets(data_root, artifacts_root=None):
    root = Path(data_root).resolve()
    artifact_root = Path(artifacts_root).resolve() if artifacts_root else root.parent / "data_artifacts"
    pointer = artifact_root / "dashboard_current.json"
    pointer_root = artifact_root
    if not pointer.is_file():
        # Read legacy locations so existing local dashboards keep working before migration.
        pointer = root / "dashboard_current.json"
        pointer_root = root
    if pointer.is_file():
        target = (pointer_root / json.loads(pointer.read_text(encoding="utf-8"))["path"]).resolve()
        if not target.is_relative_to(pointer_root.resolve()) or not target.is_dir():
            raise ValueError("Invalid current dataset path")
        root = target
    return {"Toàn bộ lịch sử · bản hiện hành": root}


def load_articles(root):
    catalog = Path(root) / "articles.parquet"
    if catalog.exists():
        try:
            return pl.read_parquet(catalog).to_pandas(), []
        except Exception as error:
            return pd.DataFrame(), [str(error)]
    frames, errors = [], []
    for path in sorted((Path(root) / "silver" / "filtered").glob("*/classified.parquet")):
        try:
            frame = pl.read_parquet(path).to_pandas()
            frame["source"] = path.parent.name
            frames.append(frame)
        except Exception as error:
            errors.append(f"{path.parent.name}: {error}")
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), errors


def load_pipeline_counts(root):
    """Read per-stage row counts from the manifest for the published snapshot."""
    manifest = Path(root) / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        counts = json.loads(manifest.read_text(encoding="utf-8")).get("pipeline_counts")
    except (OSError, ValueError, TypeError):
        return None
    return counts if isinstance(counts, dict) else None


def discover_databases(root):
    gold = Path(root) / "gold"
    return {str(path.relative_to(gold)): path for path in sorted(gold.rglob("*.duckdb"))
            if not any("stage" in part for part in path.relative_to(gold).parts)}


def read_database(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    # Fixed identifiers only; never accept SQL or writable paths from query parameters.
    with duckdb.connect(str(path), read_only=True) as c:
        tables = {r[0] for r in c.execute("SHOW TABLES").fetchall()}
        for prefix, event_table, kind in (
                ("canonical_", "canonical_events", "Canonical · Batch"),
                ("provisional_", "provisional_events", "Provisional · Streaming"),
                ("", "accident_events", "Giai đoạn 3")):
            if event_table not in tables:
                continue
            events = c.execute(f"SELECT * FROM {event_table} ORDER BY anchor_published_at DESC").fetchdf()
            articles = c.execute(f"SELECT * FROM {prefix}articles ORDER BY published_at DESC").fetchdf()
            links = c.execute(f"SELECT * FROM {prefix}event_articles").fetchdf()
            reviews = c.execute(f"SELECT * FROM {prefix}match_reviews WHERE status='pending'").fetchdf()
            titles = dict(zip(articles.get("article_key", []), articles.get("title", [])))
            urls = dict(zip(articles.get("article_key", []), articles.get("url", [])))
            sources = dict(zip(articles.get("article_key", []), articles.get("source", [])))
            for column, lookup in (("title", titles), ("url", urls), ("source", sources)):
                reviews[column] = reviews["article_key"].map(lookup)
            # Review entries without article keys still retain their original payload.
            for index, review in reviews.iterrows():
                try:
                    payload = json.loads(review["input_payload"])
                    for column, fallback in (("title", "title"), ("url", "link"), ("source", "source")):
                        if pd.isna(reviews.at[index, column]):
                            reviews.at[index, column] = payload.get(fallback)
                except (TypeError, ValueError):
                    pass
            return {"kind": kind, "events": events, "articles": articles,
                    "links": links, "reviews": reviews}
    raise ValueError("Database chưa có schema sự kiện được hỗ trợ.")


def filter_articles(frame, sources=(), labels=(), query="", dates=None):
    result = frame.copy()
    if result.empty:
        return result
    if sources:
        result = result[result["source"].isin(sources)]
    if labels and "accident_label" in result:
        result = result[result["accident_label"].isin(labels)]
    if query.strip():
        text = result.get("title", pd.Series("", index=result.index)).fillna("").astype(str)
        if "description" in result:
            text = text + " " + result["description"].fillna("").astype(str)
        result = result[text.str.contains(query.strip(), case=False, regex=False)]
    if dates and len(dates) == 2 and "pub_date" in result:
        times = pd.to_datetime(result["pub_date"], utc=True, errors="coerce").dt.tz_convert("Asia/Ho_Chi_Minh").dt.date
        result = result[(times >= dates[0]) & (times <= dates[1])]
    return result
