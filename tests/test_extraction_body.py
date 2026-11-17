import json
import unittest

import polars as pl

from extractors import extract_accident, extract_frame


class BodyExtractionTests(unittest.TestCase):
    def test_body_fills_scene_without_related_article(self):
        result = extract_accident(
            "Xe tải tông lan can, 1 người chết, 2 người bị thương",
            content="Khi đến đoạn thuộc phường Thới Sơn, tỉnh Đồng Tháp xe tải tông lan can.\n"
                    "Vụ tai nạn khiến 1 người chết và 2 người bị thương.\n"
                    "TTO - Tại Tiền Giang xe máy va chạm khiến 2 người chết.")
        self.assertEqual((result.province, result.ward), ("Đồng Tháp", "Thới Sơn"))
        self.assertEqual((result.fatalities, result.injuries), (1, 2))
        self.assertNotIn("xe máy", result.vehicles)
        self.assertIn("province_body_context", result.evidence)

    def test_repeated_paragraph_counts_not_summed(self):
        r = extract_accident("Xe khách va chạm", content=
                             "Vụ va chạm khiến 2 người bị thương.\nHai người bị thương được cấp cứu.")
        self.assertEqual(r.injuries, 2)

    def test_conflicting_counts_not_maximum(self):
        r = extract_accident("Va chạm khiến 2 người chết", content="Vụ tai nạn khiến 3 người chết.")
        self.assertIsNone(r.fatalities)
        self.assertIn("conflicting_fatalities", r.review_reasons)

    def test_roundup_never_scalar_casualties(self):
        for title in ["Bản tin TNGT 26/11", "Tin tức tai nạn giao thông mới nhất hôm nay 5/2"]:
            r = extract_accident(title, "1 người chết, 3 người bị thương.",
                                 "Tại Hà Nội xảy ra va chạm, 1 người chết.")
            self.assertIsNone(r.fatalities)
            self.assertIsNone(r.injuries)
            self.assertIn("multiple_events_in_article", r.review_reasons)

    def test_rescue_and_hospital_do_not_supply_scene_or_vehicles(self):
        r = extract_accident("Xe máy va chạm tại Hà Nội", content=
                             "Bệnh viện tỉnh Bắc Ninh tiếp nhận 1 người bị thương.\n"
                             "Xe cứu thương và xe tải cứu hộ đến điều tiết giao thông tại hiện trường.")
        self.assertEqual(r.province, "Hà Nội")
        self.assertEqual(r.vehicles, ["xe máy"])

    def test_driver_residence_does_not_override_crash_province(self):
        r = extract_accident(
            "Đồng Tháp: Xe khách lao vào lề đường",
            content="Tại tỉnh Đồng Tháp, xe khách va chạm với ba người bên đường. "
                    "Tài xế ngụ tỉnh An Giang đang điều khiển xe.")
        self.assertEqual(r.province, "Đồng Tháp")

    def test_route_destination_does_not_override_crash_province(self):
        r = extract_accident(
            "Lâm Đồng: Xe bán tải va chạm xe đầu kéo",
            content="Vụ tai nạn xảy ra đoạn qua xã Quảng Tín, tỉnh Lâm Đồng. "
                    "Xe bán tải chạy theo hướng từ Lâm Đồng đi TP Đồng Nai.")
        self.assertEqual(r.province, "Lâm Đồng")

    def test_residence_word_does_not_match_inside_other_words(self):
        r = extract_accident("Xe máy bốc cháy ngùn ngụt trên cầu ở TPHCM")
        self.assertEqual(r.province, "TP Hồ Chí Minh")

    def test_vehicle_crossing_local_area_sets_scene_province(self):
        r = extract_accident(
            "Xe khách bốc cháy trơ khung",
            content="Xe khách lưu thông qua địa bàn xã Hòa Xuân (tỉnh Đắk Lắk) thì bốc cháy.\n"
                    "Tài xế ngụ tại tỉnh Thanh Hóa đã đưa hành khách thoát ra ngoài.")
        self.assertEqual(r.province, "Đắk Lắk")

    def test_body_subgroup_zero_not_article_zero(self):
        r = extract_accident("Xe khách va chạm", content="Tài xế không bị thương.")
        self.assertIsNone(r.injuries)

    def test_apostrophe_admin_and_singular(self):
        r = extract_accident("Tai nạn tại xã M'Đrắk (Đắk Lắk), một phụ nữ tử vong")
        self.assertEqual(r.ward, "M'Đrắk")
        self.assertEqual(r.fatalities, 1)

    def test_frame_uses_body_preserves_scope_and_source(self):
        f = pl.DataFrame({"title": ["Va chạm xe máy"], "content": ["Tại Hà Nội xảy ra va chạm, 2 người bị thương."],
                          "accident_label": ["uncertain"]})
        r = extract_frame(f).row(0, named=True)
        self.assertEqual(r["injuries"], 2)
        self.assertEqual(r["content"], f["content"][0])
        self.assertEqual(r["accident_label"], "uncertain")
        self.assertIn("upstream_scope_uncertain", r["review_reasons"])
        self.assertIn("injuries_body_context", json.loads(r["evidence_json"]))

    def test_qualified_numeric_victims_and_no_approximation(self):
        self.assertEqual(extract_accident("Hà Nội: 2 người đi xe máy tử vong sau va chạm xe tải").fatalities, 2)
        self.assertEqual(extract_accident("Bốn thanh thiếu niên tử vong sau va chạm").fatalities, 4)
        self.assertIsNone(extract_accident("Ít nhất 4 người tử vong sau va chạm").fatalities)
        self.assertIsNone(extract_accident("3 người đi xe máy suýt chết").fatalities)

    def test_missing_body_is_visible(self):
        r = extract_frame(pl.DataFrame({"title": ["Xe máy va chạm"], "content": [None]})).row(0, named=True)
        self.assertIn("missing_body", r["review_reasons"])


if __name__ == "__main__":
    unittest.main()
