"""Validate RSS Bronze fields without trusting externally supplied identity."""
from datetime import datetime
import json

from config.schemas import RssBronzeBaseModel
from config import RSS_SOURCES
from preprocessors.utils import dedup_make_article_key, dedup_normalize_article_url

SOURCES = frozenset(RSS_SOURCES)


def normalize_article(value):
    if not isinstance(value, dict):
        raise ValueError("article must be a JSON object")
    source = value.get("source")
    if source not in SOURCES:
        raise ValueError(f"source must be one of: {', '.join(sorted(SOURCES))}")
    row = dict(value)
    for name in ("title", "description", "pub_date", "link"):
        item = row.get(name)
        if name == "pub_date" and isinstance(item, datetime):
            item = item.isoformat()
        if not isinstance(item, str) or (name != "description" and not item.strip()):
            raise ValueError(f"{name} must be text and required fields must be nonempty")
        row[name] = item
    url = dedup_normalize_article_url(row["link"])
    if url is None:
        raise ValueError("link must be a valid HTTP(S) URL")
    # Reuse the Phase 1 base schema; feed metadata is optional at this interface.
    for name in ("meta_title", "meta_description", "meta_link"):
        row.setdefault(name, None)
    bronze = RssBronzeBaseModel.model_validate(row)
    row.update(bronze.model_dump(mode="json"))
    row.update(source=source, normalized_url=url, article_key=dedup_make_article_key(source, url))
    # Reject non-JSON metadata as well as NaN before enqueue.
    json.dumps(row, ensure_ascii=False, allow_nan=False)
    return row


def parse_message(raw):
    try:
        return normalize_article(json.loads(raw))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid article message: {error}") from error
