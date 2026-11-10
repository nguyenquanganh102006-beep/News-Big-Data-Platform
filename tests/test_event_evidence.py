"""Regression cases for event identity, not a substitute for real-news evaluation."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import polars as pl

from config import MatchConfig
from events.adapter import prepare_article
from events.matching import decide_match
from events.profile import incident_profile
from events.repository import EventRepository
from events.run import run_events
from events.similarity import TextModel, split_for_encoder


def report(key, **changes):
    row = {"article_key": key, "source": "test", "link": f"https://example.org/{key}",
           "title": "Xe ben va chạm xe máy trong hầm chui Phan Thúc Duyện",
           "description": "Sáng 31/10, vụ tai nạn tại TP.HCM khiến hai người tử vong.",
           "pub_date": "2026-10-31T08:00:00+07:00", "province": "TP Hồ Chí Minh",
           "vehicles": ["xe ben", "xe máy"], "review_reasons": []}
    row.update(changes)
    return row


def classify(left, right, model_class=TextModel):
    a, b = prepare_article(left), prepare_article(right)
    model = model_class([a["text"], b["text"]])
    event = {"event_id": "event", "text": a["text"], "members": [a],
             "vehicles": a["vehicles"], "anchor_published_at": a["published_at"]}
    return decide_match(b, [event], model, MatchConfig())


class EventEvidenceTests(unittest.TestCase):
    def test_long_body_chunking_preserves_words_despite_capped_token_count(self):
        text = " ".join(f"word{i}" for i in range(500))
        count = lambda value: min(len(value.split()) + 2, 128)
        chunks = split_for_encoder(text, count)
        self.assertEqual(" ".join(chunks), text)
        self.assertTrue(all(count(chunk) <= 120 for chunk in chunks))

    def test_different_named_roads_veto_almost_identical_text(self):
        a = report("a", title="Xe ben va chạm xe máy trên đường Xuân Thủy")
        b = report("b", title="Xe ben va chạm xe máy trên đường Trần Duy Hưng")
        result = classify(a, b)
        self.assertEqual(result["decision"], "new_event")
        self.assertIn("conflicting_road", result["scores"][0]["conflicts"])

    def test_different_incident_dates_veto_same_place_and_vehicles(self):
        result = classify(report("a"), report("b", description="Sáng 30/10, vụ tai nạn tại TP.HCM khiến hai người tử vong."))
        self.assertEqual(result["decision"], "new_event")
        self.assertIn("conflicting_incident_date", result["scores"][0]["conflicts"])

    def test_high_semantic_similarity_without_identity_does_not_merge(self):
        class SameTopicModel(TextModel):
            def semantic_similarity(self, left, right):
                return 0.99
        result = classify(
            report("a", title="Xe tải va chạm xe máy tại TP.HCM", description="Tai nạn lúc sáng sớm."),
            report("b", title="Tài xế container tông người đi xe hai bánh", description="Cảnh sát điều tra một vụ tai nạn ở TP.HCM."),
            SameTopicModel)
        self.assertNotEqual(result["decision"], "matched")

    def test_admin_name_is_not_a_bridge_name(self):
        a = prepare_article(report("a", title="Xe máy va chạm ở quận Cầu Giấy",
                                   description="Tai nạn tại Hà Nội."))
        self.assertEqual(incident_profile(a)["places"]["bridge"], [])

    def test_numbered_commune_keeps_its_identifier(self):
        a = prepare_article(report("a", title="Xe tải va chạm xe máy ở xã A Lưới 4"))
        self.assertEqual(incident_profile(a)["places"]["ward"], ["a lưới 4"])

    def test_residence_is_not_a_scene(self):
        a = prepare_article(report("a", title="Xe tải va chạm xe máy",
                                   description="Nạn nhân trú ở đường Xuân Thủy, đang điều trị tại bệnh viện."))
        self.assertEqual(incident_profile(a)["places"]["road"], [])

    def test_yearless_incident_date_across_new_year(self):
        a = prepare_article(report("a", pub_date="2027-01-01T09:00:00+07:00",
                                   description="Tai nạn xảy ra đêm 31/12 tại TP.HCM."))
        self.assertEqual(incident_profile(a)["incident_dates"], ["2026-12-31"])

    def test_late_followup_uses_same_incident_date_and_named_scene(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "test.parquet"
            pl.DataFrame([report("a"), report("b", pub_date="2026-11-01T14:00:00+07:00")]).write_parquet(path)
            with redirect_stdout(StringIO()):
                result = run_events({"test": path}, root / "events.duckdb", root / "exports")
            self.assertEqual((result["new_event"], result["matched"]), (1, 1))

    def test_body_is_available_after_database_reload(self):
        with TemporaryDirectory() as tmp:
            repository = EventRepository(Path(tmp) / "events.duckdb")
            try:
                repository.initialize()
                a = prepare_article(report("a", content="Thông tin trong thân bài: biển số 29A-12345."))
                repository.insert_article(a)
                self.assertEqual(repository.read_articles()["a"]["text"], a["text"])
            finally:
                repository.close()

    def test_invalid_semantic_configuration_rejected(self):
        for values in ({"semantic_model": ""}, {"semantic_cache_dir": 123},
                       {"followup_radius_hours": -1}, {"min_evidence_text_score": 2}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                MatchConfig(**values)
