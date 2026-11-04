"""Prefer the newest known field without adding casualty counts across reports."""

from datetime import datetime, timezone


SUMMARY_FIELDS = ("province", "district", "ward", "fatalities", "injuries", "vehicles")


def has_field_conflict(article, field):
    flags = article.get("flags", [])
    reasons = {f"conflicting_{field}", f"ambiguous_{field}"}
    if field == "province":
        reasons.add("conflicting_article_province")
    if field == "injuries":
        reasons.add("injury_status_updated")
    return bool(reasons.intersection(flags))


def _field_time(article, field):
    return ((article.get("field_timestamps") or {}).get(field)
            or article.get("published_at") or article.get("ingested_at")
            or datetime.min.replace(tzinfo=timezone.utc))


def _select_field(members, field):
    mentions = []
    for article in members:
        conflict = has_field_conflict(article, field)
        if article.get(field) is None and not conflict:
            continue
        stamp = _field_time(article, field)
        mentions.append({"article_key": article["article_key"], "value": article.get(field),
                         "field_updated_at": stamp, "source_conflict": conflict,
                         "published_at": article.get("published_at") or stamp})
    if not mentions:
        return None, [], False
    rank = lambda item: (item["field_updated_at"], item["published_at"])
    newest_rank = max(map(rank, mentions))
    newest = [item for item in mentions if rank(item) == newest_rank]
    values = {str(item["value"]).strip().casefold() for item in newest}
    ambiguous = len(values) != 1 or any(item["source_conflict"] for item in newest)
    value = None if ambiguous else newest[0]["value"]
    for item in mentions:
        item["selected"] = not ambiguous and rank(item) == newest_rank
    return value, mentions, ambiguous


def aggregate_members(members: list[dict], fallback_province=None) -> dict:
    result, evidence, reasons = {}, {}, []
    province, evidence["province"], conflict = _select_field(members, "province")
    result["province"] = province or fallback_province
    if conflict:
        reasons.append("conflicting_province")
    for field in ("district", "ward", "fatalities", "injuries"):
        eligible = members
        if field in ("district", "ward"):
            eligible = [a for a in members if a.get("province") == result["province"]]
        value, evidence[field], conflict = _select_field(eligible, field)
        result[field] = value
        if conflict:
            reasons.append(f"conflicting_{field}")
    result["vehicles"] = sorted({v for member in members for v in member["vehicles"]})
    result["location_full"] = ", ".join(str(result[field]) for field in ("ward", "district", "province")
                                        if result[field])
    dates = [a["published_at"] for a in members if a.get("published_at") is not None]
    result["first_published_at"] = min(dates) if dates else None
    result["last_published_at"] = max(dates) if dates else None
    result["evidence"] = evidence
    result["reasons"] = reasons
    return result
