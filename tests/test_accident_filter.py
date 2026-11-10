import unittest

from filters.accident import classify_accident
from filters.evaluate import evaluate


class AccidentFilterTests(unittest.TestCase):
    def test_additional_real_event_wordings(self):
        cases = [
            ("Lâm Đồng: Tai nạn giữa xe bán tải và xe đầu kéo làm một người tử vong", None),
            ("Xe taxi đối đầu ô tô đi ngược chiều", None),
            ("Xe hoa lao xuống ruộng, cô dâu thoát nạn", None),
            ("Cầu gãy, máy cày chở máy xúc rơi xuống kênh", "Máy cày đang qua cầu thì cầu gãy."),
            ("Người giao cơm bị tai nạn tử vong", "Người đàn ông chạy xe máy gặp tai nạn trên đường quay về."),
            ("Ô tô mất lái lật ngửa, tài xế suýt chết", None),
            ("Xe đạp va quẹt ô tô, không ai bị thương", None),
            ("Xe tải húc xe máy trên đường", None),
            ("Ô tô đụng xe đạp khiến người đi xe bị thương", None),
            ("Tàu hỏa tông xe máy tại đường ngang", None),
            ("Xe tải bốc cháy trên cao tốc", None),
            ("Cây đổ đè ô tô đang di chuyển trên đường", None),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                self.assertEqual(classify_accident(title, lead).label, "accident")

    def test_non_events_and_lexical_collisions(self):
        cases = [
            ("Cầu sắp thông xe", "Mặt đường bê tông mới hoàn thành cho phương tiện lưu thông."),
            ("Đường bê tông mới giúp xe qua cầu", None),
            ("Ngã ba chữ T: Đường thẳng có mặc nhiên là đường chính?", "Nhánh đường đâm vào đường chính, các xe phải nhường."),
            ("Cầu mới lắp biển báo", '<p>Biển báo giúp xe qua cầu an toàn.</p><ul><li>Ô tô tông xe máy chết người</li></ul>'),
            ("Ô tô có nguy cơ mất lái khi trời mưa", None),
            ("Diễn tập tình huống xe khách lật trên đường", None),
            ("Xe tải chạy ngược chiều", "Xe tải suýt gây ra tai nạn với xe con."),
            ("Xe tải chạy ẩu", "Xe tải suýt tông người đi bộ."),
            ("Công nhân tử vong do điện giật khi sửa xe", None),
            ("Thống kê tai nạn: 100 vụ xe máy va chạm trong tháng", None),
            ("Nhiều ôtô bị thiêu rụi trong vụ cháy gara", None),
            ("Điều tra tai nạn trên quốc lộ", "Xe máy va chạm xe tải, một người bị thương."),
            ("Hải Phòng rà soát sau vụ tai nạn xe máy làm bốn người chết", None),
            ("Khởi tố tài xế gây tai nạn xe máy", None),
            ("Cứu hộ xe khách sau vụ lật xe trên cao tốc", None),
            ("Tàu hàng mắc cạn gần bờ biển", None),
            ("Sà lan va chạm làm lệch cầu", None),
            ("Xe múc lật khi thi công nhà", None),
        ]
        for title, lead in cases:
            with self.subTest(title=title):
                self.assertEqual(classify_accident(title, lead).label, "not_accident")

    def test_missing_road_context_is_retained_for_review(self):
        for title in ("Mưa lớn: Cây đổ đè ôtô", "Xe tải bốc cháy"):
            with self.subTest(title=title):
                self.assertEqual(classify_accident(title).label, "uncertain")

    def test_evaluation_uses_rss_description_and_handles_empty_review_set(self):
        metrics, _ = evaluate([{'sample_id': 'lead', 'title': 'Sự cố sáng nay',
                                'description': 'Xe hoa lao xuống ruộng.', 'label': 'accident'}])
        self.assertEqual(metrics['recall_accident'], 1)
        metrics, _ = evaluate([])
        self.assertIsNone(metrics['known_label_exact_accuracy'])

    def test_impact_without_casualties_is_accident(self):
        decision = classify_accident("Ô tô đâm vào cột điện, người trên xe thoát nạn")
        self.assertEqual(decision.label, "accident")

    def test_near_miss_is_not_actual_crash(self):
        self.assertEqual(classify_accident("Xe tải chạy ẩu", "Xe tải suýt đâm vào xe con.").label, "not_accident")

    def test_hypothetical_crash_is_advice(self):
        self.assertEqual(classify_accident("Ô tô va chạm: có được đưa xe vào lề?").label, "not_accident")

    def test_unresolved_scope_abstains(self):
        self.assertEqual(classify_accident("Xe khách bốc cháy trên đường").label, "accident")
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
