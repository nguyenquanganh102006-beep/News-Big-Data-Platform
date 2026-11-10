import unittest

from config import MatchConfig
from events.adapter import prepare_article
from events.matching import decide_match
from events.similarity import TextModel


def lexical_model(texts):
    # Keep lexical scoring unit tests deterministic and independent of model downloads.
    return TextModel(texts, semantic_model=None)


def sample(key="a", **changes):
    row = {"article_key": key, "source": "test", "link": f"https://example.com/{key}",
           "title": "Xe tải va chạm xe máy tại Hà Nội", "description": "Tai nạn ở quận Cầu Giấy.",
           "pub_date": "2026-11-04T12:00:00+07:00", "province": "Hà Nội",
           "district": "Cầu Giấy", "ward": None, "vehicles": ["xe tải", "xe máy"],
           "fatalities": 2, "injuries": None, "review_reasons": []}
    row.update(changes)
    return prepare_article(row)


def candidate(event_id, member):
    return {"event_id": event_id, "text": member["text"], "members": [member],
            "anchor_published_at": member["published_at"], "vehicles": member["vehicles"]}


class EventMatchingTests(unittest.TestCase):
    def test_same_event_matches_despite_changed_casualty_count(self):
        existing, incoming = sample(), sample("b", fatalities=3)
        model = lexical_model([existing["text"], incoming["text"]])
        decision = decide_match(incoming, [candidate("E1", existing)], model, MatchConfig())
        self.assertEqual(decision["decision"], "matched")
        self.assertEqual(decision["event_id"], "E1")
        self.assertIn("components", decision["scores"][0])

    def test_conflicting_locations_prevent_text_only_merge(self):
        existing, incoming = sample(), sample("b", district="Ba Đình")
        decision = decide_match(incoming, [candidate("E1", existing)], lexical_model([incoming["text"]]), MatchConfig())
        self.assertEqual(decision["decision"], "new_event")
        self.assertIn("conflicting_district", decision["scores"][0]["conflicts"])

    def test_close_candidates_go_to_review(self):
        incoming = sample("new")
        events = [candidate("E1", sample("a")), candidate("E2", sample("b"))]
        result = decide_match(incoming, events, lexical_model([incoming["text"]]), MatchConfig())
        self.assertEqual(result["decision"], "needs_review")
        self.assertEqual(len(result["scores"]), 2)

    def test_missing_attributes_do_not_inflate_score_into_a_match(self):
        existing = sample(vehicles=[], district=None)
        incoming = sample("b", vehicles=[], district=None)
        result = decide_match(incoming, [candidate("E1", existing)], lexical_model([incoming["text"]]), MatchConfig())
        self.assertEqual(result["decision"], "needs_review")
        self.assertFalse(result["scores"][0]["sufficient"])

    def test_conflicts_checked_across_whole_event_not_only_anchor(self):
        existing, incoming = sample(), sample("b", ward="A")
        event = candidate("E1", existing)
        event["members"].append(sample("c", ward="B"))
        result = decide_match(incoming, [event], lexical_model([incoming["text"]]), MatchConfig())
        self.assertEqual(result["decision"], "new_event")

    def test_no_candidates_and_multiple_events_article(self):
        valid = sample()
        self.assertEqual(decide_match(valid, [], lexical_model([valid["text"]]), MatchConfig())["decision"], "new_event")
        multiple = sample(review_reasons=["multiple_events_in_article"])
        self.assertEqual(decide_match(multiple, [], lexical_model([multiple["text"]]), MatchConfig())["decision"], "needs_review")

    def test_empty_vector_and_configuration_validation(self):
        self.assertIsNone(lexical_model([]).similarity("", ""))
        for values in ({"threshold": 2}, {"radius_hours": 0}, {"threshold": 0.4, "review_threshold": 0.5}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                MatchConfig(**values)
