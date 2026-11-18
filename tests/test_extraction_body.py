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

    def test_scene_after_plate_and_route_is_not_lost(self):
        r = extract_accident(
            "Ô tô bốc cháy trên cao tốc",
            content="Xe mang biển số 61A chạy trên cao tốc TP. Hồ Chí Minh - Trung Lương, "
                    "khi đến đoạn qua xã Tân Hương, tỉnh Đồng Tháp thì bốc cháy.")
        self.assertEqual(r.province, "Đồng Tháp")

    def test_city_abbreviation_is_scene_not_road_name(self):
        r = extract_accident(
            "Tai nạn liên hoàn trên đường Hồ Chí Minh",
            "Vụ tai nạn xảy ra tại xã A Lưới 4, TP. Huế khiến hai người tử vong.")
        self.assertEqual(r.province, "Huế")

    def test_parenthetical_province_after_scene_ward(self):
        r = extract_accident(
            "Xe con lật trên cao tốc",
            content="Vụ tai nạn xảy ra tại Km217 cao tốc Pháp Vân, "
                    "đoạn thuộc địa phận P.Đồng Văn (Ninh Bình). Xe con lật ngửa.")
        self.assertEqual(r.province, "Ninh Bình")

    def test_dateline_with_incident_in_first_paragraph(self):
        r = extract_accident("Xe ben tông xe tải trên cầu",
                             content="Hà Nội Xe ben tông xe tải trên cầu Nhật Tân, đêm 1/11.")
        self.assertEqual(r.province, "Hà Nội")
        r = extract_accident("Xe ben gây tai nạn liên hoàn trên cầu",
                             content="Hà Nội Xe ben từ phía sau lao tới gây tai nạn liên hoàn trên cầu Nhật Tân.")
        self.assertEqual(r.province, "Hà Nội")

    def test_train_route_and_police_office_are_not_scene(self):
        r = extract_accident(
            "Xe máy bị tàu hỏa tông",
            content="Công an TP.HCM cho biết tàu chạy hướng Hà Nội - TP.HCM. "
                    "Vụ tai nạn xảy ra tại phường Đồng Văn, tỉnh Ninh Bình.")
        self.assertEqual(r.province, "Ninh Bình")

    def test_roundup_and_route_endpoints_do_not_get_forced_province(self):
        roundup = extract_accident("Toàn cảnh | Hai vụ tai nạn tại Hà Nội và Huế",
                                   "Hai xe máy va chạm, ba người bị thương.")
        self.assertIsNone(roundup.province)
        self.assertIn("multiple_events_in_article", roundup.review_reasons)
        route = extract_accident("Xe tải bốc cháy trên cao tốc Hà Nội - Hải Phòng")
        self.assertIsNone(route.province)

    def test_incident_details_cover_real_road_impacts(self):
        examples = (
            ("Xe máy va quẹt taxi trên đường", "va_quet"),
            ("Ô tô sụt xuống hố giữa đường", "sut_ho"),
            ("Cây đổ trúng xe máy trên đường", "vat_de_xe"),
            ("Xe máy bị nước lũ cuốn trôi trên đường", "nuoc_cuon_xe"),
            ("Sét đánh trúng người đang chạy xe máy trên đường", "set_danh_nguoi_di_xe"),
            ("Xe máy bị vùi lấp do sạt lở trên quốc lộ", "xe_bi_vui_lap"),
            ("Nhiều xe đâm dồn toa trên cao tốc", "va_cham"),
        )
        for title, expected in examples:
            with self.subTest(title=title):
                r = extract_accident(title)
                self.assertIn(expected, r.incident_types)
                self.assertNotIn("missing_incident_details", r.review_reasons)

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

    def test_audited_parenthetical_road_and_bridge_provinces(self):
        examples = [
            ("Đầu kéo lao vào hiện trường vụ lật xe",
             "Sau vụ lật xe đầu kéo trên quốc lộ 8A (Hà Tĩnh), một ô tô khác đâm vào xe gặp nạn.", "Hà Tĩnh"),
            ("Cầu sắt gãy đôi, máy cày rơi xuống kênh",
             "Máy cày chở xe cuốc qua cầu Tân Thành (Tây Ninh). Nhịp cầu bất ngờ gãy, xe rơi xuống kênh.", "Tây Ninh"),
        ]
        for title, lead, expected in examples:
            with self.subTest(expected=expected):
                r = extract_accident(title, lead)
                self.assertEqual(r.province, expected)
                self.assertNotIn("missing_province", r.review_reasons)

    def test_audited_dateline_and_fire_body(self):
        dateline = extract_accident("Ôtô lao xuống hồ Trị An", content=
            "Đồng Nai Ôtô 5 chỗ mất kiểm soát lao xuống hồ, hai vợ chồng tự thoát ra ngoài.\n"
            "Chiếc xe mang biển số Khánh Hòa được trục vớt.")
        self.assertEqual(dateline.province, "Đồng Nai")
        fire = extract_accident("Cháy container trên quốc lộ 51", content=
            "Xe chạy theo hướng về TPHCM. Khi vừa qua nút giao Phước Thái "
            "(xã Phước Thái, Đồng Nai), phần đầu xe bất ngờ bốc cháy.")
        self.assertEqual(fire.province, "Đồng Nai")

    def test_parenthetical_residence_and_fire_route_are_not_scene(self):
        residence = extract_accident("Xe tải bốc cháy trên đường", content=
            "Tài xế quê gần cầu Tân Thành (Tây Ninh) đã thoát khỏi xe đang bốc cháy.")
        self.assertIsNone(residence.province)
        route = extract_accident("Xe tải bốc cháy trên cao tốc Hà Nội - Hải Phòng", content=
            "Tài xế trú tại Hà Nội, chiếc xe mang biển số Hải Phòng.")
        self.assertIsNone(route.province)

    def test_scene_reference_without_collision_verb_is_preserved(self):
        r = extract_accident("Xe máy bị tàu tông", content=
            "Sự việc xảy ra tại đường ngang.\nKhu vực trên thuộc địa bàn phường Đồng Văn, tỉnh Ninh Bình.")
        self.assertEqual(r.province, "Ninh Bình")

    def test_late_scene_after_background_is_not_truncated(self):
        body = "\n".join([f"Thông tin xử lý số {i}." for i in range(10)])
        r = extract_accident("Tàu tông xe tải", content=body +
            "\nVụ tai nạn xảy ra tại xã Vệ Giang, tỉnh Quảng Ngãi.")
        self.assertEqual(r.province, "Quảng Ngãi")


if __name__ == "__main__":
    unittest.main()
