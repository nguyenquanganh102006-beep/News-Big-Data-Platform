"""Prepare extracted articles without modifying their Gold files."""

from datetime import datetime
import hashlib
import json

from .retrieval import normalize_province, utc_datetime


REQUIRED_GOLD_COLUMNS = {"article_key", "source", "link", "title", "pub_date", "province"}


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item))


def fingerprint(value) -> str:
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def prepare_article(row: dict, reference: str = "") -> dict:
    reasons = []
    key = row.get("article_key")
    if not isinstance(key, str) or not key.strip():
        key = None
        reasons.append("article_key_missing_or_invalid")
    province, published_at = None, None
    try:
        province = normalize_province(row.get("province"))
    except ValueError as error:
        reasons.append(f"province_{error}")
    try:
        published_at = utc_datetime(row.get("pub_date"))
    except ValueError as error:
        reasons.append(f"published_at_{error}")
    title = row.get("title") or ""
    description = row.get("description") or ""
    if not isinstance(title, str) or not isinstance(description, str):
        raise ValueError(f"{reference}: title/description must be text or null")
    if not title.strip():
        reasons.append("missing_title")
    url = row.get("normalized_url") or row.get("link")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        reasons.append("missing_or_invalid_url")
        url = None
    flags = row.get("review_reasons") or []
    if not isinstance(flags, list) or any(not isinstance(v, str) for v in flags):
        raise ValueError(f"{reference}: review_reasons must be a list of strings")
    for flag in ("multiple_events_in_article", "negation_or_hypothetical_context", "missing_incident_details"):
        if flag in flags:
            reasons.append(flag)
    vehicles = row.get("vehicles") or []
    if not isinstance(vehicles, list) or any(not isinstance(v, str) for v in vehicles):
        raise ValueError(f"{reference}: vehicles must be a list of strings")
    for field in ("fatalities", "injuries"):
        value = row.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError(f"{reference}: {field} must be a non-negative integer or null")
    for field in ("district", "ward"):
        if row.get(field) is not None and not isinstance(row[field], str):
            raise ValueError(f"{reference}: {field} must be text or null")
    return {
        "article_key": key, "source": row["source"], "url": url,
        "title": title, "description": description,
        "text": f"{title}. {description}".strip(),
        "published_at": published_at, "province": province,
        "district": row.get("district"), "ward": row.get("ward"),
        "vehicles": sorted(set(vehicles)), "fatalities": row.get("fatalities"),
        "injuries": row.get("injuries"), "flags": flags,
        "payload": json_text(row), "input_fingerprint": fingerprint(row),
        "reference": reference, "reasons": reasons,
    }
