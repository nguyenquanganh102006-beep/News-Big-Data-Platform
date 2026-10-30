from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unicodedata
import unittest

import polars as pl
from polars.testing import assert_frame_equal

from events import retrieve_candidates


def article(**overrides):
    return {
        "article_key": "A01",
        "province": "Hà Nội",
        "published_at": "2026-10-30T12:00:00+07:00",
        **overrides,
    }


def catalog(rows=()):
    return pl.DataFrame(rows, schema={
        "event_id": pl.String,
        "province": pl.String,
        "anchor_published_at": pl.String,
    }, orient="row")


class CandidateRetrievalTests(unittest.TestCase):
    def test_same_province_and_inclusive_window_on_both_sides(self):
        events = catalog([
            ("near", "Hà Nội", "2026-10-30T08:00:00+07:00"),
            ("lower", "Hà Nội", "2026-10-29T12:00:00+07:00"),
            ("upper", "Hà Nội", "2026-10-31T12:00:00+07:00"),
            ("too_early", "Hà Nội", "2026-10-29T11:59:59.999999+07:00"),
            ("too_late", "Hà Nội", "2026-10-31T12:00:00.000001+07:00"),
            ("other_province", "Hải Phòng", "2026-10-30T08:00:00+07:00"),
        ])
        result = retrieve_candidates(article(), events)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.candidates["event_id"].to_list(), ["lower", "near", "upper"])

    def test_configurable_radius_is_a_radius_not_total_window_width(self):
        events = catalog([("e", "Hà Nội", "2026-10-29T00:00:00+07:00")])
        self.assertEqual(retrieve_candidates(article(), events).candidates.height, 0)
        self.assertEqual(retrieve_candidates(article(), events, radius_hours=48).candidates.height, 1)

    def test_alias_unicode_case_and_whitespace_without_boundary_remapping(self):
        events = catalog([
            ("alias", "TP.HCM", "2026-10-30T05:00:00Z"),
            ("different", "Bình Dương", "2026-10-30T05:00:00Z"),
        ])
        value = unicodedata.normalize("NFD", "  tp   Hồ Chí Minh \n")
        result = retrieve_candidates(article(province=value), events)
        self.assertEqual(result.candidates["event_id"].to_list(), ["alias"])

    def test_utc_comparison_and_stable_id_tiebreaker(self):
        events = catalog([
            ("B", "Hà Nội", "2026-10-30T01:00:00-04:00"),
            ("A", "Hà Nội", "2026-10-30T05:00:00Z"),
        ])
        result = retrieve_candidates(article(), events, radius_hours=0.5)
        self.assertEqual(result.candidates["event_id"].to_list(), ["A", "B"])
        assert_frame_equal(result.candidates, retrieve_candidates(article(), events.reverse(), 0.5).candidates)

    def test_aware_datetime_input_and_preserved_schema_payload_and_inputs(self):
        stamp = datetime(2026, 10, 30, 12, tzinfo=timezone(timedelta(hours=7)))
        incoming = article(published_at=stamp)
        original_article = deepcopy(incoming)
        events = pl.DataFrame({
            "event_id": ["e"], "province": ["Hà Nội"],
            "anchor_published_at": [stamp], "vehicles": [["xe tải", "xe máy"]],
        })
        original_events = events.clone()
        result = retrieve_candidates(incoming, events)
        assert_frame_equal(result.candidates, original_events)
        assert_frame_equal(events, original_events)
        self.assertEqual(incoming, original_article)

    def test_empty_catalog_and_valid_no_match_are_ok_with_full_schema(self):
        for events in (catalog(), catalog([("e", "Hải Phòng", "2026-10-30T05:00:00Z")])):
            with self.subTest(events=events):
                result = retrieve_candidates(article(), events)
                self.assertEqual(result.status, "ok")
                self.assertEqual(result.candidates.height, 0)
                self.assertEqual(result.candidates.schema, events.schema)

    def test_incomplete_or_invalid_article_needs_review_even_with_empty_catalog(self):
        cases = [
            ({"article_key": None}, "article_key_missing_or_invalid"),
            ({"province": None}, "province_missing"),
            ({"province": "  "}, "province_missing"),
            ({"province": ["Hà Nội", "Hải Phòng"]}, "province_invalid"),
            ({"province": "unknown"}, "province_unknown"),
            ({"published_at": None}, "published_at_missing"),
            ({"published_at": "bad date"}, "published_at_invalid"),
            ({"published_at": "2026-10-30T12:00:00"}, "published_at_timezone_required"),
            ({"published_at": datetime(2026, 10, 30)}, "published_at_timezone_required"),
        ]
        for overrides, reason in cases:
            with self.subTest(overrides=overrides):
                result = retrieve_candidates(article(**overrides), catalog())
                self.assertEqual(result.status, "needs_review")
                self.assertIn(reason, result.reasons)
                self.assertEqual(result.candidates.height, 0)
        self.assertEqual(len(retrieve_candidates({}, catalog()).reasons), 3)

    def test_invalid_radius_rejected(self):
        for radius in (0, -1, float("nan"), float("inf"), True, "24", 1e30, 1e-30):
            with self.subTest(radius=radius), self.assertRaises(ValueError):
                retrieve_candidates(article(), catalog(), radius_hours=radius)

    def test_invalid_catalog_not_silently_treated_as_no_candidates(self):
        cases = [
            pl.DataFrame(),
            catalog([(None, "Hà Nội", "2026-10-30T05:00:00Z")]),
            catalog([("e", None, "2026-10-30T05:00:00Z")]),
            catalog([("e", "unknown", "2026-10-30T05:00:00Z")]),
            catalog([("e", "Hà Nội", None)]),
            catalog([("e", "Hà Nội", "2026-10-30T05:00:00")]),
            catalog([("e", "Hà Nội", "invalid")]),
            catalog([
                ("e", "Hà Nội", "2026-10-30T05:00:00Z"),
                ("e", "Hà Nội", "2026-10-30T06:00:00Z"),
            ]),
        ]
        for events in cases:
            with self.subTest(events=events), self.assertRaises(ValueError):
                retrieve_candidates(article(), events)


if __name__ == "__main__":
    unittest.main()
