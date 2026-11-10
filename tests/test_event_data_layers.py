from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import duckdb
import polars as pl

from config import DATA_SILVER_DIR, EVENT_INPUT_DIR, EXTRACT_OUTPUT_DIR, MatchConfig
from extractors import extract_filtered_files
from events.run import run_events


class EventDataLayersTests(unittest.TestCase):
    def test_default_input_is_extracted_silver_and_agrees_with_stage_two_output(self):
        expected = Path(DATA_SILVER_DIR) / "accidents"
        self.assertEqual(Path(EXTRACT_OUTPUT_DIR), expected)
        self.assertEqual(EVENT_INPUT_DIR, expected)

    def test_stage_two_writes_silver_and_stage_three_reads_it_to_build_gold(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            filtered = root / "filtered" / "test"
            filtered.mkdir(parents=True)
            source = filtered / "accident.parquet"
            pl.DataFrame({
                "article_key": ["article-a"], "source": ["test"],
                "title": ["Xe tải va chạm xe máy tại tỉnh Nghệ An"],
                "description": ["Hai người tử vong sau vụ va chạm."],
                "link": ["https://example.com/accident-a"],
                "pub_date": ["2026-11-04T12:00:00+07:00"],
            }).write_parquet(source)
            original = source.read_bytes()
            silver = root / "silver" / "accidents"
            gold = root / "gold" / "events"
            database = gold / "accident_events.duckdb"
            with patch("extractors.accident.FILTERED_DATA_DIR", str(filtered.parent)), \
                 patch("extractors.accident.EXTRACT_OUTPUT_DIR", str(silver)), \
                 patch("extractors.accident.EXTRACT_SOURCES", ("test",)):
                extract_filtered_files()
            article_path = silver / "test.parquet"
            self.assertTrue(article_path.is_file())
            self.assertEqual(pl.read_parquet(article_path)["province"].to_list(), ["Nghệ An"])
            before_events = article_path.read_bytes()
            with patch("events.run.EVENT_INPUT_DIR", silver), \
                 patch("events.run.EXTRACT_SOURCES", ("test",)), \
                 patch("events.run.EVENT_DATABASE_PATH", database), \
                 patch("events.run.EVENT_EXPORT_DIR", gold / "exports"), \
                 redirect_stdout(StringIO()):
                first = run_events(config=MatchConfig(semantic_model=None))
                second = run_events(config=MatchConfig(semantic_model=None))
            self.assertEqual(first["new_event"], 1)
            self.assertEqual(second["already_processed"], 1)
            self.assertEqual(first["database"], second["database"])
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(article_path.read_bytes(), before_events)
            self.assertFalse((root / "gold" / "accidents").exists())
            with duckdb.connect(str(database), read_only=True) as connection:
                self.assertEqual(connection.execute("SELECT province,article_count FROM accident_events").fetchall(),
                                 [("Nghệ An", 1)])
            self.assertTrue((gold / "exports" / "accident_events.parquet").is_file())

    def test_missing_silver_does_not_fall_back_to_legacy_gold_articles(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "gold" / "accidents" / "test.parquet"
            old.parent.mkdir(parents=True)
            pl.DataFrame({"title": ["legacy"]}).write_parquet(old)
            before = old.read_bytes()
            database = root / "gold" / "events" / "accident_events.duckdb"
            with patch("events.run.EVENT_INPUT_DIR", root / "silver" / "accidents"), \
                 patch("events.run.EXTRACT_SOURCES", ("test",)), \
                 patch("events.run.EVENT_DATABASE_PATH", database):
                with self.assertRaisesRegex(FileNotFoundError, "Silver.*step=4"):
                    run_events()
            self.assertFalse(database.exists())
            self.assertEqual(old.read_bytes(), before)
