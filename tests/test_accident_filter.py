import unittest

from filters.accident import classify_accident
from filters.evaluate import evaluate


class AccidentFilterTests(unittest.TestCase):
    def test_impact_without_casualties_is_accident(self):
        decision = classify_accident("Ô tô đâm vào cột điện, người trên xe thoát nạn")
        self.assertEqual(decision.label, "accident")

    def test_near_miss_is_not_actual_crash(self):
        self.assertEqual(classify_accident("Xe tải chạy ẩu", "Xe tải suýt đâm vào xe con.").label, "not_accident")

    def test_hypothetical_crash_is_advice(self):
        self.assertEqual(classify_accident("Ô tô va chạm: có được đưa xe vào lề?").label, "not_accident")

    def test_unresolved_scope_abstains(self):
        self.assertEqual(classify_accident("Xe khách bốc cháy trên đường").label, "uncertain")
        self.assertEqual(classify_accident(None, None).label, "uncertain")

    def test_related_crash_does_not_override_main_topic(self):
        self.assertEqual(classify_accident("Cầu mới lắp biển báo", "Đơn vị lắp biển báo. Xe tải va chạm xe máy khiến một người tử vong.").label, "not_accident")

    def test_metrics_penalize_abstention_on_known_positive(self):
        metrics, _ = evaluate([
            {"sample_id": "a", "title": "Ô tô tông xe máy", "label": "accident"},
            {"sample_id": "b", "title": "Tai nạn chưa rõ", "label": "accident"},
            {"sample_id": "c", "title": "Khai trương bến xe", "label": "not_accident"},
        ])
        self.assertEqual(metrics["precision_accident"], 1.0)
        self.assertEqual(metrics["recall_accident"], 0.5)
        self.assertEqual(metrics["known_label_exact_accuracy"], 2 / 3)
