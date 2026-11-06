"""Explainable article-to-event decisions; this module does not write data."""

import unicodedata

from config import MATCH_WEIGHTS, MatchConfig


def _token(value):
    return " ".join(unicodedata.normalize("NFC", value or "").split()).casefold()


def calculate_match_score(article, candidate, text_model, config: MatchConfig) -> dict:
    text = text_model.similarity(article["text"], candidate["text"])
    location, conflicts = [], []
    # Compare to every linked article to avoid attaching a bridge article to a
    # cluster whose reliable locations disagree. The fixed anchor supplies text.
    for member in candidate["members"]:
        for field in ("district", "ward"):
            a, b = _token(article.get(field)), _token(member.get(field))
            if a and b:
                if a != b:
                    conflicts.append(f"conflicting_{field}")
                else:
                    location.append(1.0)
    location_score = 1.0 if location and not conflicts else (0.0 if conflicts else None)
    left, right = set(article["vehicles"]), set(candidate["vehicles"])
    vehicles = len(left & right) / len(left | right) if left and right else None
    delta = abs((article["published_at"] - candidate["anchor_published_at"]).total_seconds()) / 3600
    time = max(0.0, 1 - delta / config.radius_hours)
    values = {"text": text, "location": location_score, "vehicles": vehicles, "time": time}
    weights = MATCH_WEIGHTS
    coverage = sum(weights[k] for k, v in values.items() if v is not None)
    score = sum(weights[k] * v for k, v in values.items() if v is not None) / coverage
    supported = location_score == 1 or (vehicles is not None and vehicles > 0)
    sufficient = text is not None and coverage >= config.min_coverage and supported
    return {"event_id": candidate["event_id"], "score": score, "coverage": coverage,
            "components": values, "conflicts": sorted(set(conflicts)), "sufficient": sufficient}


def decide_match(article, candidates, text_model, config: MatchConfig) -> dict:
    if article["reasons"]:
        return {"decision": "needs_review", "reasons": article["reasons"], "scores": []}
    if not candidates:
        return {"decision": "new_event", "reasons": ["no_candidates"], "scores": []}
    scores = sorted((calculate_match_score(article, e, text_model, config) for e in candidates),
                    key=lambda s: (-s["score"], s["event_id"]))
    viable = [s for s in scores if not s["conflicts"]]
    if not viable:
        return {"decision": "new_event", "reasons": ["different_locations"], "scores": scores}
    best = viable[0]
    gap = best["score"] - viable[1]["score"] if len(viable) > 1 else 1.0
    text = best["components"]["text"]
    if (best["sufficient"] and text >= config.min_text_score
            and best["score"] >= config.threshold and gap >= config.min_margin):
        return {"decision": "matched", "event_id": best["event_id"], "score": best["score"],
                "reasons": ["multi_attribute_match"], "scores": scores}
    # A plausible but uncertain candidate is not automatically a new accident.
    uncertain = any(not s["sufficient"] or s["score"] >= config.review_threshold for s in viable)
    return {"decision": "needs_review" if uncertain else "new_event",
            "reasons": ["ambiguous_or_insufficient_match" if uncertain else "low_similarity"],
            "scores": scores}
