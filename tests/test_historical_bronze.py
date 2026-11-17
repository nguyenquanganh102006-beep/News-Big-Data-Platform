from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import duckdb
import polars as pl

from preprocessors.historical import preprocess_historical_files
from preprocessors.run import bronze_snapshots
from streaming.repository import ProvisionalRepository
from dashboard.publish import snapshot_streaming
from config import MatchConfig
from streaming.message import normalize_article
from streaming.pipeline import ArticleProcessor
import json


class HistoricalBronzeTests(unittest.TestCase):
    def test_html_history_preserves_body_dates_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "history_1_2.parquet"
            output = root / "silver.parquet"
            pl.DataFrame([{
                "source": "dantri", "title": "<b>Tin &amp; tin</b>",
                "description": "<p>Nội dung mô tả</p>", "content": "Nội dung toàn bài",
                "link": "https://dantri.com.vn/test.htm", "pub_date": "2026-01-02T03:00:00+07:00",
            }]).write_parquet(raw)
            before = raw.read_bytes()
            with patch("preprocessors.historical.RSS_SOURCES", {"dantri": {"silver_save_path": output}}):
                preprocess_historical_files("dantri", [raw])
                preprocess_historical_files("dantri", [raw])
            result = pl.read_parquet(output)
            self.assertEqual(result.height, 1)
            self.assertEqual(result["title"][0], "Tin & tin")
            self.assertEqual(result["content"][0], "Nội dung toàn bài")
            self.assertEqual(result["pub_date"][0].hour, 20)
            self.assertEqual(raw.read_bytes(), before)

    def test_discovery_includes_history_and_keeps_date_filter_for_rss(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "bronze" / "dantri"
            folder.mkdir(parents=True)
            for name in ("history_00000001_00000100.parquet", "20261116_080000.parquet", "other.parquet"):
                pl.DataFrame({"title": ["fixture"]}).write_parquet(folder / name)
            with patch("preprocessors.run.DATA_DIR", root), patch("preprocessors.run.DATA_ARTIFACTS_DIR", root / "artifacts"), patch("preprocessors.run.RSS_SOURCES", {"dantri": {}}):
                self.assertEqual(len(bronze_snapshots()["dantri"]), 2)
                self.assertEqual([p.name for p in bronze_snapshots("2026-11-16")["dantri"]], ["20261116_080000.parquet"])

    def test_streaming_snapshot_includes_receipts_and_is_independent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "gold" / "streaming" / "provisional.duckdb"
            repo = ProvisionalRepository(source)
            repo.initialize()
            repo.connection.execute("INSERT INTO stream_receipts(article_key,status,raw_payload) VALUES ('test','not_accident','{}')")
            repo.close()
            generation = root / "snapshot"
            counts = snapshot_streaming(root, generation)
            self.assertEqual(counts["receipts"], 1)
            self.assertEqual(counts["articles"], 0)
            with duckdb.connect(str(generation / "gold" / "streaming" / "provisional.duckdb"), read_only=True) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM stream_receipts").fetchone()[0], 1)
            self.assertTrue(source.is_file())

    def test_streaming_keeps_full_body_in_matching_input(self):
        with TemporaryDirectory() as directory:
            repo = ProvisionalRepository(Path(directory) / "stream.duckdb")
            try:
                repo.initialize()
                payload = normalize_article({
                    "source": "vietnamplus", "link": "https://www.vietnamplus.vn/test-body.vnp",
                    "pub_date": "2026-01-02T08:00:00+07:00",
                    "title": "Xe tải va chạm xe máy tại Hà Nội",
                    "description": "Xe tải va chạm xe máy tại quận Cầu Giấy, Hà Nội khiến 2 người tử vong.",
                    "content": "Chi tiết toàn bài được giữ cho mô hình ghép sự kiện.",
                })
                processor = ArticleProcessor(repo, MatchConfig(radius_hours=24, semantic_model=None))
                self.assertEqual(processor.process(payload)["status"], "new_event")
                saved = repo.connection.execute("SELECT extraction_payload FROM provisional_articles").fetchone()[0]
                self.assertEqual(json.loads(saved)["content"], payload["content"])
                self.assertEqual(processor.process(payload)["status"], "already_processed")
            finally:
                repo.close()


if __name__ == "__main__":
    unittest.main()
