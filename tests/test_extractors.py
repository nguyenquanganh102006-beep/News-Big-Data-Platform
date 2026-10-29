from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import polars as pl

from extractors import extract_accident, extract_frame, extract_filtered_files


class ExtractionTests(unittest.TestCase):
    def test_locations_vehicles_and_individual_casualties(self):
        result = extract_accident(
            "Lâm Đồng: Xe đầu kéo va chạm xe tập lái khiến 2 người thương vong",
            "Xe ôtô tải tập lái va chạm xe đầu kéo, khiến học viên tử vong và thầy dạy lái bị thương nặng.",
        )
        self.assertEqual(result.province, "Lâm Đồng")
        self.assertEqual(result.vehicles, ["xe đầu kéo", "xe tải"])
        self.assertEqual((result.fatalities, result.injuries), (1, 1))
        self.assertEqual(result.incident_types, ["va_cham"])
        self.assertIn("học viên tử vong", result.evidence["fatalities"])

    def test_road_name_is_not_accident_province(self):
        result = extract_accident("Xe tải tông đuôi container trên cao tốc TP HCM - Long Thành - Dầu Giây, một người chết")
        self.assertIsNone(result.province)
        self.assertEqual(result.fatalities, 1)
        self.assertIsNone(result.injuries)
        self.assertEqual(result.incident_types, ["tong_duoi"])

    def test_administrative_levels_are_separate(self):
        result = extract_accident("Va chạm xe máy ở Hải Phòng", "Trên đường Võ Văn Kiệt, phường Thạch Khôi.")
        self.assertEqual(result.province, "Hải Phòng")
        self.assertEqual(result.ward, "Thạch Khôi")
        self.assertIsNone(result.district)
        result = extract_accident("Tai nạn tại huyện Bình Sơn, tỉnh Quảng Ngãi")
        self.assertEqual(result.district, "Bình Sơn")
        self.assertEqual(result.province, "Quảng Ngãi")

    def test_missing_total_conflict_and_negation(self):
        result = extract_accident("Hai xe máy va chạm khiến 2 người thương vong")
        self.assertIsNone(result.fatalities)
        self.assertIsNone(result.injuries)
        result = extract_accident("Va chạm, 4 người chết", "1 người tử vong tại hiện trường, 3 người tử vong tại bệnh viện.")
        self.assertEqual(result.fatalities, 4)
        result = extract_accident("Xe tải suýt tông xe máy khiến một người chết")
        self.assertIsNone(result.fatalities)
        self.assertEqual(result.incident_types, [])

    def test_zero_and_approximation(self):
        result = extract_accident("Hai xe máy va chạm", "Không ai bị thương.")
        self.assertEqual(result.injuries, 0)
        self.assertIn("va_cham", result.incident_types)
        self.assertIsNone(extract_accident("Va chạm, ít nhất 2 người chết").fatalities)
        self.assertEqual(extract_accident("Va chạm, hai mươi hai người chết").fatalities, 22)
        self.assertIsNone(extract_accident("Va chạm, 2-3 người chết").fatalities)
        result = extract_accident("Va chạm, bốn người tử vong", "4 người tử vong.")
        self.assertEqual(result.fatalities, 4)

    def test_obstacle_and_ambiguous_provinces(self):
        result = extract_accident("Ô tô lao vào tường tại Hà Nội", "Thông tin khác tại Hải Phòng.")
        self.assertIn("dam_vat_can", result.incident_types)
        self.assertIsNone(result.province)
        self.assertIn("ambiguous_province", result.review_reasons)

    def test_unrelated_negation_does_not_erase_confirmed_casualties(self):
        result = extract_accident("Hai xe máy va chạm, 2 người tử vong", "Nguyên nhân chưa được làm rõ.")
        self.assertEqual(result.fatalities, 2)
        self.assertIn("va_cham", result.incident_types)
        result = extract_accident("Xe không mất lái nhưng tông xe máy, 1 người chết")
        self.assertEqual(result.fatalities, 1)
        self.assertIn("va_cham", result.incident_types)
        self.assertNotIn("mat_lai", result.incident_types)

    def test_vehicle_specificity_does_not_drop_another_car(self):
        for title, expected in (
            ("Ô tô con va chạm xe tải", {"ô tô", "xe tải"}),
            ("Ô tô tải tông xe máy", {"xe tải", "xe máy"}),
            ("Xe máy điện va chạm xe đạp điện", {"xe máy điện", "xe đạp điện"}),
            ("Ô tô cứu thương va chạm taxi", {"xe cứu thương", "taxi"}),
        ):
            with self.subTest(title=title):
                self.assertEqual(set(extract_accident(title).vehicles), expected)

    def test_two_roles_and_explicit_role_counts(self):
        self.assertEqual(extract_accident("Hai tài xế tử vong sau va chạm").fatalities, 2)
        self.assertEqual(extract_accident("Tài xế tử vong, phụ xe tử vong sau va chạm").fatalities, 2)
        # Repeated role mentions could identify the same person, so abstain.
        result = extract_accident("Tài xế tử vong, tài xế tử vong trong vụ khác")
        self.assertIsNone(result.fatalities)
        result = extract_accident("Tài xế tử vong, người đàn ông tử vong sau va chạm")
        self.assertIsNone(result.fatalities)

    def test_survival_is_not_a_near_miss(self):
        result = extract_accident("Suýt chết sau va chạm xe máy")
        self.assertIn("va_cham", result.incident_types)
        self.assertIsNone(result.fatalities)
        result = extract_accident("Hai xe máy va chạm, không có thương vong")
        self.assertEqual((result.fatalities, result.injuries), (0, 0))
        result = extract_accident("Va chạm, chưa ghi nhận thương vong")
        self.assertEqual((result.fatalities, result.injuries), (None, None))

    def test_count_phrasings_and_vietnamese_numbers(self):
        for text, deaths, injuries in (
            ("Va chạm, hai người chết, ba người bị thương", 2, 3),
            ("Tai nạn làm chết 2 người, bị thương 3 người", 2, 3),
            ("Va chạm khiến 2 người chết và 3 bị thương", 2, 3),
            ("Va chạm, mười một người chết", 11, None),
            ("Va chạm, hai mươi lăm người bị thương", None, 25),
            ("Va chạm, một trăm linh năm người bị thương", None, 105),
            ("Va chạm, 1.000 người bị thương", None, 1000),
        ):
            with self.subTest(text=text):
                result = extract_accident(text)
                self.assertEqual((result.fatalities, result.injuries), (deaths, injuries))

    def test_approximate_and_range_counts_are_not_exact(self):
        for text in ("ít nhất hai người chết", "khoảng 3 người chết", "2 đến 3 người chết", "2–3 người chết", "1,5 người chết"):
            with self.subTest(text=text):
                self.assertIsNone(extract_accident("Va chạm, " + text).fatalities)

    def test_update_requires_explicit_final_total(self):
        result = extract_accident("Một người chết trong vụ va chạm", "Thêm một người tử vong sau đó.")
        self.assertIsNone(result.fatalities)
        result = extract_accident("Một người chết trong vụ va chạm", "Thêm một người tử vong, nâng tổng số người chết lên 2.")
        self.assertEqual(result.fatalities, 2)
        result = extract_accident("Va chạm, 2 người bị thương", "Ban đầu 2 người bị thương, sau đó một người tử vong.")
        self.assertIsNone(result.injuries)

    def test_no_unsafe_addition_of_equal_numeric_groups(self):
        result = extract_accident("Va chạm", "1 người tử vong, 1 người tử vong.")
        self.assertIsNone(result.fatalities)
        self.assertIn("conflicting_fatalities", result.review_reasons)
        result = extract_accident("Va chạm, 2 người chết", "Tổng cộng 2 người tử vong, 1 người tử vong tại hiện trường.")
        self.assertEqual(result.fatalities, 2)

    def test_explicit_disjoint_groups_and_age(self):
        result = extract_accident("4 người tử vong", "1 người tử vong tại hiện trường, 3 người tử vong tại bệnh viện.")
        self.assertEqual(result.fatalities, 4)
        result = extract_accident("Va chạm", "1 người tử vong, 3 người khác tử vong.")
        self.assertEqual(result.fatalities, 4)
        result = extract_accident("Va chạm", "Bốn người từ 16 - 21 tuổi tử vong.")
        self.assertEqual(result.fatalities, 4)
        result = extract_accident("Va chạm, 6 người chết", "1 người tử vong tại hiện trường, 3 người tử vong tại bệnh viện.")
        self.assertIsNone(result.fatalities)

    def test_location_after_road_and_residence_or_hospital(self):
        result = extract_accident("Xe máy va chạm trên đường Nguyễn Trãi tại Hà Nội")
        self.assertEqual(result.province, "Hà Nội")
        result = extract_accident("Va chạm tại Hà Nội", "Nạn nhân trú tại Hải Phòng. Được cấp cứu tại bệnh viện ở Bắc Ninh.")
        self.assertEqual(result.province, "Hà Nội")
        result = extract_accident("Va chạm", "Nạn nhân quê tại huyện Bình Sơn, tỉnh Quảng Ngãi.")
        self.assertIsNone(result.district)
        self.assertIsNone(result.province)

    def test_admin_names_and_no_thi_xa_overlap(self):
        result = extract_accident("Va chạm tại thị xã Bình Minh")
        self.assertEqual(result.district, "Bình Minh")
        self.assertIsNone(result.ward)
        result = extract_accident("Va chạm tại phường Thạch Khôi bất ngờ gây ùn tắc")
        self.assertEqual(result.ward, "Thạch Khôi")
        result = extract_accident("Va chạm tại quận 12, TP.HCM")
        self.assertEqual(result.district, "12")
        self.assertEqual(result.province, "TP Hồ Chí Minh")

    def test_province_vocabulary_and_historical_names_no_remap(self):
        for name in ("Bắc Ninh", "Nghệ An", "Phú Thọ", "Hải Dương", "Bình Dương"):
            with self.subTest(name=name):
                self.assertEqual(extract_accident(f"Va chạm tại tỉnh {name}").province, name)

    def test_multiple_events_and_unknown_fields(self):
        result = extract_accident("Hai vụ tai nạn làm 3 người chết")
        self.assertIsNone(result.fatalities)
        self.assertIn("multiple_events_in_article", result.review_reasons)
        result = extract_accident(None, None)
        self.assertIsNone(result.fatalities)
        self.assertEqual(result.vehicles, [])
        with self.assertRaises(ValueError):
            extract_accident(123)

    def test_empty_html_unicode_and_missing_title(self):
        self.assertEqual(extract_frame(pl.DataFrame({"title": pl.Series([], dtype=pl.String)})).height, 0)
        with self.assertRaises(ValueError):
            extract_frame(pl.DataFrame({"link": ["url"]}))
        result = extract_accident(None, "<p>Va chạm&nbsp;xe máy tại tỉnh Gia Lai, 2 người tử vong.</p>")
        self.assertEqual(result.province, "Gia Lai")
        self.assertEqual(result.fatalities, 2)

    def test_pipeline_preserves_input_and_replaces_output(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp, "filtered", "test")
            source.mkdir(parents=True)
            input_path = source / "accident.parquet"
            pl.DataFrame({"title": ["Hai xe máy va chạm, bốn người tử vong"], "article_key": ["a"]}).write_parquet(input_path)
            original = input_path.read_bytes()
            output = Path(tmp, "gold")
            with patch("extractors.accident.FILTERED_DATA_DIR", str(source.parent)), patch("extractors.accident.EXTRACT_OUTPUT_DIR", str(output)), patch("extractors.accident.EXTRACT_SOURCES", ("test",)):
                extract_filtered_files()
                extract_filtered_files()
                result = pl.read_parquet(output / "test.parquet")
                self.assertEqual(result.height, 1)
                self.assertEqual(result["article_key"][0], "a")
                self.assertEqual(result["fatalities"][0], 4)
                self.assertEqual(input_path.read_bytes(), original)
                with patch("extractors.accident.EXTRACT_SOURCES", ("missing",)):
                    with self.assertRaises(FileNotFoundError):
                        extract_filtered_files()
