from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import polars as pl

from filters.body_fetch import fetch_article_body, is_video_page, parse_article_body, valid_article_url
from filters.run import filter_silver_file


BODY = ("Lúc 7h sáng, xe máy va chạm với xe tải trên đường Nguyễn Trãi, "
        "khiến một người bị thương. Công an đến hiện trường xử lý vụ tai nạn.")


class BodyFetchTests(unittest.TestCase):
    def test_extracts_only_article_text(self):
        html = ("<nav>Điều hướng</nav><article class='fck_detail'>"
                f"<p>{BODY}</p><p>Hai xe bị hư hỏng tại hiện trường.</p>"
                "<aside><p>Bài liên quan không thuộc vụ này.</p></aside></article>")
        body = parse_article_body(html, "vnexpress")
        self.assertIn("xe máy va chạm", body)
        self.assertNotIn("Bài liên quan", body)
        self.assertIsNone(parse_article_body("<article><p>Tin quá ngắn</p></article>", "vnexpress"))

    def test_json_ld_body(self):
        html = ('<script type="application/ld+json">{"@type":"NewsArticle",'
                '"articleBody":"' + BODY + '"}</script>')
        self.assertIn("Nguyễn Trãi", parse_article_body(html, "vietnamplus"))
        related = ('<script type="application/ld+json">{"@type":"NewsArticle",'
                   '"mainEntityOfPage":"https://vietnamplus.vn/other",'
                   '"articleBody":"' + BODY + '"}</script>')
        self.assertIsNone(parse_article_body(
            related, "vietnamplus", "https://vietnamplus.vn/current"))

    def test_does_not_take_related_story_when_video_has_no_body(self):
        html = ("<div class='detail-content'></div>"
                f"<article><p>{BODY}</p></article>")
        self.assertIsNone(parse_article_body(html, "baoxaydung"))

    def test_video_metadata_is_recognized_without_body(self):
        html = ('<script type="application/ld+json">'
                '{"@graph":[{"@type":"NewsArticle"},'
                '{"@type":"VideoObject","name":"Ô tô tông xe máy"}]}'
                '</script><h1>Ô tô tông xe máy</h1><div class="detail-content"></div>')
        self.assertTrue(is_video_page(html))
        self.assertIsNone(parse_article_body(html, "baoxaydung"))
        response = Mock(status_code=200, headers={"Content-Type": "text/html"})
        response.iter_content.return_value = [html.encode()]
        session = Mock()
        session.get.return_value = response
        self.assertEqual(fetch_article_body("https://baoxaydung.vn/a.htm", "baoxaydung", session)[1],
                         "video_without_body")
        self.assertFalse(is_video_page('<p>Video liên quan</p>'))
        self.assertFalse(is_video_page(html.replace('Ô tô tông xe máy</h1>', 'Bài chữ khác</h1>')))

    def test_dantri_new_article_container(self):
        html = (f"<article id='articleContent'><div class='desktop-in-article'>"
                f"<p>{BODY}</p><figure><figcaption><p>Chú thích ảnh</p></figcaption></figure>"
                "</div></article>")
        body = parse_article_body(html, "dantri")
        self.assertIn("Nguyễn Trãi", body)
        self.assertNotIn("Chú thích ảnh", body)

    def test_rejects_untrusted_urls_and_redirects(self):
        self.assertFalse(valid_article_url("http://vnexpress.net/a", "vnexpress"))
        self.assertFalse(valid_article_url("https://vnexpress.net.evil.test/a", "vnexpress"))
        self.assertFalse(valid_article_url("https://example.com/a", "vnexpress"))
        response = Mock(status_code=302, headers={"Location": "https://example.com/a"})
        session = Mock()
        session.get.return_value = response
        self.assertEqual(fetch_article_body("https://vnexpress.net/a", "vnexpress", session)[1],
                         "invalid_redirect")
        response.close.assert_called_once()

    def test_fetches_candidates_reclassifies_and_reuses_cache(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "vnexpress.parquet")
            output = Path(tmp, "filtered")
            pl.DataFrame({
                "article_key": ["a", "b", "c"],
                "source": ["vnexpress"] * 3,
                "title": ["Ô tô tông xe máy", "Tai nạn giao thông", "Khai trương bến xe"],
                "description": [None] * 3,
                "link": [f"https://vnexpress.net/{x}.html" for x in "abc"],
            }).write_parquet(path)
            with patch("filters.body_fetch.fetch_article_body", side_effect=lambda url, source, session:
                       (BODY, "ok", url)) as fetch:
                counts = filter_silver_file(path, output)
                self.assertEqual(fetch.call_count, 2)
            self.assertEqual(counts, {"input": 3, "accident": 2,
                                      "not_accident": 1, "uncertain": 0, "skipped_video": 0})
            classified = pl.read_parquet(output / "classified.parquet")
            self.assertEqual(classified["body_fetch_status"].to_list(), ["ok", "ok", "skipped"])
            self.assertEqual(classified["content"].to_list(), [BODY, BODY, None])
            with patch("filters.body_fetch.fetch_article_body") as fetch:
                filter_silver_file(path, output)
                fetch.assert_not_called()
            self.assertEqual(pl.read_parquet(output / "classified.parquet")
                             ["body_fetch_status"].to_list(), ["cached", "cached", "skipped"])

    def test_fetch_failure_keeps_candidate_and_status(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "vnexpress.parquet")
            output = Path(tmp, "filtered")
            pl.DataFrame({"source": ["vnexpress"], "title": ["Ô tô tông xe máy"],
                          "description": ["Hai xe va chạm."],
                          "link": ["https://vnexpress.net/a.html"]}).write_parquet(path)
            with patch("filters.body_fetch.fetch_article_body",
                       return_value=(None, "fetch_error", "https://vnexpress.net/a.html")):
                counts = filter_silver_file(path, output)
            self.assertEqual(counts["accident"], 1)
            row = pl.read_parquet(output / "classified.parquet").row(0, named=True)
            self.assertEqual(row["body_fetch_status"], "fetch_error")
            self.assertIsNone(row["content"])

    def test_missing_body_is_not_fetched_again_immediately(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "tienphong.parquet")
            output = Path(tmp, "filtered")
            pl.DataFrame({"source": ["tienphong"], "title": ["Ô tô tông xe máy"],
                          "description": ["Hai xe va chạm."],
                          "link": ["https://tienphong.vn/a.tpo"]}).write_parquet(path)
            with patch("filters.body_fetch.fetch_article_body",
                       return_value=(None, "body_missing", "https://tienphong.vn/a.tpo")) as fetch:
                filter_silver_file(path, output)
                filter_silver_file(path, output)
                self.assertEqual(fetch.call_count, 1)
            row = pl.read_parquet(output / "classified.parquet").row(0, named=True)
            self.assertEqual(row["body_fetch_status"], "cached_missing")

    def test_empty_video_is_skipped_and_cached(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "baoxaydung.parquet")
            output = Path(tmp, "filtered")
            pl.DataFrame({"source": ["baoxaydung"], "title": ["Ô tô tông xe máy"],
                          "description": ["Hai xe va chạm."],
                          "link": ["https://baoxaydung.vn/a.htm"]}).write_parquet(path)
            with patch("filters.body_fetch.fetch_article_body",
                       return_value=(None, "video_without_body", "https://baoxaydung.vn/a.htm")) as fetch:
                first = filter_silver_file(path, output)
                second = filter_silver_file(path, output)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(first["skipped_video"], 1)
            self.assertEqual(second["accident"], 0)
            row = pl.read_parquet(output / "classified.parquet").row(0, named=True)
            self.assertEqual(row["body_fetch_status"], "cached_video_without_body")
            self.assertEqual(row["filter_reason"], "video_without_body")


if __name__ == "__main__":
    unittest.main()
