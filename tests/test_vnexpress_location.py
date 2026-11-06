import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import polars as pl
from polars.testing import assert_frame_equal
import requests

from config import ArticleLocation, VNEXPRESS_EXTRACT_VERSION
from extractors import extract_frame, extract_filtered_files
from extractors.vnexpress import (
    fetch_vnexpress_location, fetch_vnexpress_locations, parse_vnexpress_location,
)


URL = "https://vnexpress.net/example-5140249.html"


def page(label):
    return f'<p class="description"><span class="location-stamp">{label}</span>Xe tải va chạm xe máy.</p>'


def response(html="", status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.iter_content.return_value = [html.encode("utf-8")]
    return result


class VnexpressLocationTests(unittest.TestCase):
    def test_datelines_observed_on_three_real_articles(self):
        for label, expected in (("TP Huế", "Huế"), ("Nghệ An", "Nghệ An"), ("Hà Nội", "Hà Nội")):
            with self.subTest(label=label):
                result = parse_vnexpress_location(page(label), URL)
                self.assertEqual((result.status, result.province, result.text), ("ok", expected, label))

    def test_alias_prefix_and_unicode(self):
        for label, expected in (("TP. Hồ Chí Minh", "TP Hồ Chí Minh"), ("Tỉnh Thanh Hoá", "Thanh Hóa"),
                                ("  TP.  Huế  ", "Huế")):
            with self.subTest(label=label):
                self.assertEqual(parse_vnexpress_location(page(label)).province, expected)

    def test_does_not_take_navigation_body_residence_or_image_location(self):
        html = ('<nav><span class="location-stamp">Hà Nội</span></nav>'
                '<p class="description">Xe tải va chạm xe máy.</p>'
                '<article><p>Nạn nhân quê ở Nghệ An.</p></article>')
        self.assertEqual(parse_vnexpress_location(html).status, "missing")

    def test_unknown_and_multiple_provinces_are_not_guessed(self):
        self.assertEqual(parse_vnexpress_location(page("Quốc lộ 1A")).status, "unknown")
        self.assertEqual(parse_vnexpress_location(page("Hà Nội") + page("Hải Phòng")).status, "ambiguous")

    def test_fill_missing_province_preserve_source_text_and_other_extractions(self):
        frame = pl.DataFrame({"title": ["Hai xe máy va chạm, 2 người chết"],
                              "description": ["Va chạm trên đường ven biển."], "link": [URL]})
        original = frame.clone()
        baseline = extract_frame(frame)
        enriched = extract_frame(frame, [ArticleLocation("ok", "Nghệ An", "Nghệ An", URL)])
        self.assertEqual(enriched["province"][0], "Nghệ An")
        self.assertNotIn("missing_province", enriched["review_reasons"][0].to_list())
        self.assertEqual(enriched["fatalities"][0], baseline["fatalities"][0])
        self.assertEqual(enriched["title"][0], frame["title"][0])
        self.assertEqual(enriched["description"][0], frame["description"][0])
        self.assertEqual(enriched["extraction_version"][0], VNEXPRESS_EXTRACT_VERSION)
        evidence = json.loads(enriched["evidence_json"][0])
        self.assertEqual(evidence["province_dateline"], ["Nghệ An"])
        self.assertEqual(evidence["province_dateline_url"], [URL])
        assert_frame_equal(frame, original)

    def test_conflict_does_not_silently_replace_rss_province(self):
        for title in ("Xe máy va chạm tại Hà Nội", "Xe máy va chạm tại Hà Nội và tại Hải Phòng"):
            with self.subTest(title=title):
                result = extract_frame(pl.DataFrame({"title": [title]}),
                                       [ArticleLocation("ok", "Nghệ An", "Nghệ An", URL)])
                self.assertIsNone(result["province"][0])
                self.assertIn("conflicting_article_province", result["review_reasons"][0].to_list())

    def test_request_failure_keeps_rss_result_and_records_status(self):
        frame = pl.DataFrame({"title": ["Xe máy va chạm tại Hà Nội", "Xe máy va chạm"]})
        result = extract_frame(frame, [ArticleLocation("fetch_error", url=URL)] * 2)
        self.assertEqual(result["province"].to_list(), ["Hà Nội", None])
        self.assertIn("article_location_fetch_error", result["review_reasons"][1].to_list())
        self.assertEqual(result["article_location_status"].to_list(), ["fetch_error"] * 2)

    def test_http_timeout_and_bad_urls_do_not_abort_extraction(self):
        session = Mock()
        session.get.side_effect = requests.Timeout("timeout")
        self.assertEqual(fetch_vnexpress_location(URL, session).status, "fetch_error")
        session.reset_mock()
        for url in (None, "https://example.com/a", "https://vnexpress.net.attacker.invalid/a", "http://vnexpress.net/a"):
            with self.subTest(url=url):
                self.assertEqual(fetch_vnexpress_location(url, session).status, "invalid_url")
        session.get.assert_not_called()

    def test_http_success_and_same_host_redirect(self):
        session = Mock()
        first = response(status=302, headers={"Location": "/new-5140249.html"})
        second = response(page("Hà Nội"))
        session.get.side_effect = [first, second]
        result = fetch_vnexpress_location(URL, session)
        self.assertEqual(result.province, "Hà Nội")
        self.assertEqual(result.url, "https://vnexpress.net/new-5140249.html")
        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_redirect_to_other_host_and_large_response_are_rejected(self):
        session = Mock()
        session.get.return_value = response(status=302, headers={"Location": "https://example.com/a"})
        self.assertEqual(fetch_vnexpress_location(URL, session).status, "invalid_redirect")
        session.get.assert_called_once()
        session.get.return_value = response("x" * 21)
        with patch("extractors.vnexpress.VNEXPRESS_MAX_HTML_BYTES", 20):
            self.assertEqual(fetch_vnexpress_location(URL, session).status, "too_large")

    def test_duplicate_links_fetched_once_per_batch(self):
        frame = pl.DataFrame({"link": [URL, URL]})
        with patch("extractors.vnexpress.requests.Session") as factory:
            session = factory.return_value.__enter__.return_value
            session.get.return_value = response(page("Hà Nội"))
            result = fetch_vnexpress_locations(frame)
        self.assertEqual([x.province for x in result], ["Hà Nội", "Hà Nội"])
        session.get.assert_called_once()

    def test_empty_input_and_hint_count_validation(self):
        empty = pl.DataFrame({"title": pl.Series([], dtype=pl.String), "link": pl.Series([], dtype=pl.String)})
        result = extract_frame(empty, [])
        self.assertEqual(result.height, 0)
        self.assertIn("article_location_status", result.columns)
        with self.assertRaises(ValueError):
            extract_frame(pl.DataFrame({"title": ["test"]}), [])

    def test_pipeline_enriches_vnexpress_only_and_preserves_input(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = pl.DataFrame({"title": ["Xe máy va chạm"], "link": [URL], "article_key": ["a"]})
            for source in ("vnexpress", "other"):
                directory = root / "filtered" / source
                directory.mkdir(parents=True)
                original.write_parquet(directory / "accident.parquet")
            input_path = root / "filtered/vnexpress/accident.parquet"
            before = input_path.read_bytes()
            with patch("extractors.accident.FILTERED_DATA_DIR", str(root / "filtered")), \
                 patch("extractors.accident.EXTRACT_OUTPUT_DIR", str(root / "silver/accidents")), \
                 patch("extractors.accident.EXTRACT_SOURCES", ("vnexpress", "other")), \
                 patch("extractors.accident.fetch_vnexpress_locations", return_value=[ArticleLocation("ok", "Hà Nội", "Hà Nội", URL)]) as fetch:
                extract_filtered_files()
                extract_filtered_files()
            self.assertEqual(fetch.call_count, 2)
            enriched = pl.read_parquet(root / "silver/accidents/vnexpress.parquet")
            self.assertEqual(enriched["province"].to_list(), ["Hà Nội"])
            self.assertEqual(enriched.height, 1)
            self.assertNotIn("article_location_status", pl.read_parquet(root / "silver/accidents/other.parquet").columns)
            self.assertEqual(input_path.read_bytes(), before)
