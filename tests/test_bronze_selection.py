from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from config import latest_bronze_path


class BronzeSelectionTests(unittest.TestCase):
    def test_latest_date_and_exact_time_with_collisions(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            names = ["20261024_090000.parquet", "20261024_153000.parquet",
                     "20261024_153000_000001.parquet", "20261025_080000.parquet",
                     "unrelated.parquet", "20261024_1530009.parquet"]
            for name in names:
                directory.joinpath(name).touch()
            with patch.dict("config.preprocessors.RSS_SOURCES", {"test": {"bronze_dir": tmp}}):
                self.assertEqual(latest_bronze_path("test").name, names[3])
                self.assertEqual(latest_bronze_path("test", "2026-10-24").name, names[2])
                self.assertEqual(latest_bronze_path("test", "2026-10-24 15:30:00").name, names[2])
                self.assertEqual(latest_bronze_path("test", "2026-10-24 09:00:00").name, names[0])
                for value in ("2026-10-23", "2026-10-24 15:30:01"):
                    with self.subTest(value=value), self.assertRaises(FileNotFoundError):
                        latest_bronze_path("test", value)
                for value in ("2026-02-30", "2026-1-24", "2026/10/24", "2026-10-24 9:00:00", ""):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        latest_bronze_path("test", value)

    def test_missing_directory_has_no_latest_file(self):
        with TemporaryDirectory() as tmp:
            with patch.dict("config.preprocessors.RSS_SOURCES", {"test": {"bronze_dir": str(Path(tmp, "missing"))}}):
                with self.assertRaises(FileNotFoundError):
                    latest_bronze_path("test")
