"""Shared deterministic Bronze normalization -> dedup -> filter -> extraction."""
import hashlib
import json
from pathlib import Path

import polars as pl

from config import DATA_ARTIFACTS_DIR, EXTRACT_SOURCES
from config.extractors import EXTRACT_SCHEMA
from extractors.accident import extract_frame
from extractors.vnexpress import fetch_vnexpress_locations
from filters.accident import classify_accident
from filters.body_fetch import enrich_candidate_bodies
from filters.run import write_parquet_atomic
from preprocessors.content_dedup import detect_duplicate_articles
from streaming.pipeline import clean_article
from streaming.message import normalize_article
from .state import signature
from .config import atomic_json

OUTPUT = ["content", "body_fetch_status", "body_fetch_url", "accident_label", "filter_reason", "filter_evidence", "filter_version", "review_override_applied", *EXTRACT_SCHEMA]
REVIEW = Path(DATA_ARTIFACTS_DIR) / "filter_review_20261117/full_review/reviewed_classified.parquet"


def version():
    root = Path(__file__).resolve().parents[1]
    paths = [root / name for name in ("a2/processing.py", "filters/accident.py", "filters/body_fetch.py", "config/filters.py", "extractors/accident.py", "config/extractors.py", "preprocessors/content_dedup.py", "streaming/message.py", "streaming/pipeline.py", "a2/state.py", "events/profile.py", "events/matching.py", "events/service.py", "config/events.py")]
    digest = hashlib.sha256(b"".join(path.read_bytes() for path in paths))
    if REVIEW.exists():
        digest.update(REVIEW.read_bytes())
    return digest.hexdigest()


def review_annotations():
    result = {}
    if not REVIEW.exists():
        return result
    for raw in pl.read_parquet(REVIEW).iter_rows(named=True):
        try:
            raw["pub_date"] = str(raw.get("pub_date") or "")
            raw["description"] = raw.get("description") or ""
            row = clean_article(normalize_article(raw))
            row["pub_date"] = row["pub_date"].isoformat()
            result[row["article_key"]] = (signature(row), raw["accident_label"], raw.get("filter_reason") or "reviewed_scope")
        except (ValueError, TypeError):
            continue
    return result


def prepare(frame, directory, annotations=None, enrich=True):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = version()
    cache_path, stamp_path = directory / "catalog.parquet", directory / "processing_version.json"
    cached = {}
    if cache_path.exists() and stamp_path.exists() and json.loads(stamp_path.read_text())["version"] == stamp:
        cached = {r["article_key"]: r for r in pl.read_parquet(cache_path).iter_rows(named=True)}
    annotations = annotations or {}
    tagged = detect_duplicate_articles(frame)
    results, vne_new = [], []
    for row in tagged.iter_rows(named=True):
        old = cached.get(row["article_key"])
        if old and old["input_fingerprint"] == row["input_fingerprint"] and old["is_duplicate"] == row["is_duplicate"]:
            row.update({name: old.get(name) for name in OUTPUT})
        else:
            decision = classify_accident(row["title"], row.get("description"), row.get("content"))
            row.update(accident_label=decision.label, filter_reason=decision.reason,
                       filter_evidence=decision.evidence, filter_version=decision.version,
                       review_override_applied=False)
            reviewed = annotations.get(row["article_key"])
            if reviewed and reviewed[0] == row["input_fingerprint"]:
                row.update(accident_label=reviewed[1], filter_reason=reviewed[2],
                           filter_version=decision.version + "+reviewed-input", review_override_applied=True)
            if row["is_duplicate"]:
                row.update(accident_label="duplicate", filter_reason="content_duplicate")
            # Use the upstream body evidence before extraction/matching. Keep
            # Bronze and its fingerprint intact; fetched text belongs to Silver.
            if enrich and row["accident_label"] in ("accident", "uncertain"):
                row = enrich_candidate_bodies(
                    pl.DataFrame([row], infer_schema_length=None),
                    directory / "body_cache" / f"{row['source']}.parquet",
                ).row(0, named=True)
                if not row["review_override_applied"]:
                    decision = classify_accident(row["title"], row.get("description"), row.get("content"))
                    row.update(accident_label=decision.label, filter_reason=decision.reason,
                               filter_evidence=decision.evidence, filter_version=decision.version)
                if row.get("body_fetch_status") in ("video_without_body", "cached_video_without_body"):
                    row.update(accident_label="skipped_video", filter_reason="video_without_body")
            if row["accident_label"] == "accident":
                row = extract_frame(pl.DataFrame([row], infer_schema_length=None)).row(0, named=True)
                if row["source"] == "vnexpress":
                    vne_new.append(len(results))
            else:
                for name, dtype in EXTRACT_SCHEMA.items():
                    row[name] = [] if dtype.base_type() == pl.List else None
        results.append(row)
    if enrich and vne_new:
        incoming = pl.DataFrame([results[index] for index in vne_new], infer_schema_length=None)
        locations = fetch_vnexpress_locations(incoming)
        enriched = extract_frame(incoming, locations)
        for index, row in zip(vne_new, enriched.iter_rows(named=True)):
            results[index] = row
    catalog = pl.DataFrame(results, infer_schema_length=None).with_columns(
        [pl.col(name).cast(dtype) for name, dtype in EXTRACT_SCHEMA.items()])
    write_parquet_atomic(catalog, cache_path)
    atomic_json(stamp_path, {"version": stamp, "review_reference": str(REVIEW) if REVIEW.exists() else None})
    paths = {}
    for source in EXTRACT_SOURCES:
        part = catalog.filter(pl.col("source") == source)
        write_parquet_atomic(part, directory / "deduplicated" / f"{source}.parquet")
        write_parquet_atomic(part.filter(~pl.col("is_duplicate")), directory / "filtered" / source / "classified.parquet")
        path = directory / "accidents" / f"{source}.parquet"
        write_parquet_atomic(part.filter((~pl.col("is_duplicate")) & (pl.col("accident_label") == "accident")), path)
        paths[source] = path
    return catalog, paths
