"""Summarize one accident without adding casualty figures across reports."""


def aggregate_members(members: list[dict]) -> dict:
    result, evidence, reasons = {}, {}, []
    for field in ("district", "ward", "fatalities", "injuries"):
        mentions = [{"article_key": a["article_key"], "value": a.get(field)}
                    for a in members if a.get(field) is not None]
        # Normalize spelling for location comparison, retaining a source value.
        values = {str(m["value"]).strip().casefold() for m in mentions}
        upstream_conflict = any(f"conflicting_{field}" in a.get("flags", []) for a in members)
        if field == "injuries":
            upstream_conflict |= any("injury_status_updated" in a.get("flags", []) for a in members)
        result[field] = mentions[0]["value"] if len(values) == 1 and not upstream_conflict else None
        evidence[field] = mentions
        if len(values) > 1 or upstream_conflict:
            reasons.append(f"conflicting_{field}")
    result["vehicles"] = sorted({v for member in members for v in member["vehicles"]})
    result["location_full"] = ", ".join(str(result[field]) for field in ("ward", "district") if result[field])
    province = members[0]["province"]
    result["location_full"] = ", ".join(filter(None, (result["location_full"], province)))
    result["first_published_at"] = min(a["published_at"] for a in members)
    result["last_published_at"] = max(a["published_at"] for a in members)
    result["evidence"] = evidence
    result["reasons"] = reasons
    return result
