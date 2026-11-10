"""Hierarchical event identity decisions with auditable evidence and vetoes."""

from config import MATCH_WEIGHTS, MatchConfig
from .profile import compare_profiles, token


def _pair_score(article, member, text_model, config, event_id):
    evidence = compare_profiles(article, member)
    lexical = text_model.similarity(article["text"], member["text"])
    semantic = text_model.semantic_similarity(article["text"], member["text"])
    # Dense similarity is topical evidence, not proof of incident identity.
    text = (0.65 * semantic + 0.35 * lexical if semantic is not None and lexical is not None else lexical)
    location = any(token(article.get(field)) and token(article.get(field)) == token(member.get(field))
                   for field in ("district", "ward")) or bool(evidence["shared_places"])
    left, right = set(article["vehicles"]), set(member["vehicles"])
    vehicles = len(left & right) / len(left | right) if left and right else None
    values = {"text": text, "location": 1.0 if location else None, "identity": evidence["identity"],
              "vehicles": vehicles, "time": 1.0 if evidence["same_incident_date"] else
              max(0.0, 1 - evidence["delta_hours"] / config.radius_hours)}
    coverage = sum(MATCH_WEIGHTS[k] for k, value in values.items() if value is not None)
    score = sum(MATCH_WEIGHTS[k] * value for k, value in values.items() if value is not None) / coverage
    duplicate = lexical is not None and lexical >= 0.85 and (location or bool(vehicles))
    supported = duplicate or evidence["identity"] is not None
    sufficient = text is not None and coverage >= config.min_coverage and supported
    return {"event_id": event_id, "score": score, "coverage": coverage,
            "components": values, "lexical_score": lexical, "semantic_score": semantic,
            "evidence": evidence, "conflicts": evidence["conflicts"],
            "sufficient": sufficient, "near_duplicate": duplicate,
            "matched_member_key": member.get("article_key")}


def calculate_match_score(article, candidate, text_model, config: MatchConfig) -> dict:
    members = candidate["members"]
    anchor = next((m for m in members if m.get("article_key") == candidate.get("anchor_article_key")), None)
    anchor = anchor or next((m for m in members if m["text"] == candidate["text"]), members[0])
    anchor_score = _pair_score(article, anchor, text_model, config, candidate["event_id"])
    pairs = [_pair_score(article, member, text_model, config, candidate["event_id"]) for member in members]
    # Do not assemble text, vehicle and location evidence from unrelated members.
    best = dict(max(pairs, key=lambda pair: (pair["sufficient"], pair["score"])))
    best["conflicts"] = sorted({conflict for pair in pairs for conflict in pair["conflicts"]})
    anchor_related = (anchor_score["near_duplicate"] or anchor_score["evidence"]["identity"] is not None)
    best["anchor_compatible"] = anchor_related
    best["sufficient"] = best["sufficient"] and anchor_related
    best["member_scores"] = [{"article_key": pair["matched_member_key"], "score": pair["score"],
                              "conflicts": pair["conflicts"]} for pair in pairs]
    return best


def decide_match(article, candidates, text_model, config: MatchConfig) -> dict:
    if article["reasons"]:
        return {"decision": "needs_review", "reasons": article["reasons"], "scores": []}
    if not candidates:
        return {"decision": "new_event", "reasons": ["no_candidates"], "scores": []}
    scores = sorted((calculate_match_score(article, e, text_model, config) for e in candidates),
                    key=lambda s: (-s["score"], s["event_id"]))
    viable = [s for s in scores if not s["conflicts"]]
    if not viable:
        return {"decision": "new_event", "reasons": ["conflicting_incident_evidence"], "scores": scores}
    eligible = [s for s in viable if s["sufficient"]]
    best = eligible[0] if eligible else viable[0]
    rivals = [s["score"] for s in viable if s is not best]
    gap = best["score"] - max(rivals) if rivals else 1.0
    text = best["components"]["text"]
    text_floor = config.min_text_score if best["near_duplicate"] else config.min_evidence_text_score
    if (best["sufficient"] and text >= text_floor
            and best["score"] >= config.threshold and gap >= config.min_margin):
        return {"decision": "matched", "event_id": best["event_id"], "score": best["score"],
                "margin": gap, "reasons": ["corroborated_incident_match"], "scores": scores}
    uncertain = any(not s["sufficient"] or s["score"] >= config.review_threshold for s in viable)
    return {"decision": "needs_review" if uncertain else "new_event",
            "reasons": ["ambiguous_or_insufficient_match" if uncertain else "low_similarity"],
            "margin": gap, "scores": scores}
