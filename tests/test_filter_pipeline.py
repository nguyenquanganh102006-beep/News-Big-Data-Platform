from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

from filters.run import filter_frame, filter_silver_file
from main import run_pipeline


class FilterPipelineTests(unittest.TestCase):
    def test_outputs_partition_history_without_modifying_silver(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "silver.parquet")
            original = pl.DataFrame({"article_key": ["a", "b", "c"], "title": [
                "Ô tô tông xe máy", "Khai trương bến xe", "Xe tải bốc cháy"],
                "description": [None, None, None]})
            original.write_parquet(path)
            contents = path.read_bytes()
            output = Path(tmp, "filtered")
            expected = {"input": 3, "accident": 1, "not_accident": 1, "uncertain": 1}
            self.assertEqual(filter_silver_file(path, output), expected)
            self.assertEqual(filter_silver_file(path, output), expected)
            self.assertEqual(path.read_bytes(), contents)
            self.assertEqual(pl.read_parquet(output / "accident.parquet")["article_key"].to_list(), ["a"])
            self.assertEqual(pl.read_parquet(output / "classified.parquet").height, 3)
            assert_frame_equal(pl.read_parquet(path), original)

    def test_empty_input_and_missing_description(self):
        self.assertEqual(filter_frame(pl.DataFrame({"title": pl.Series([], dtype=pl.String)})).height, 0)
        self.assertEqual(filter_frame(pl.DataFrame({"title": [None]}))["accident_label"][0], "uncertain")
        with self.assertRaises(ValueError):
            filter_frame(pl.DataFrame({"link": ["example"]}))

    def test_steps_run_only_requested_stage_and_reject_invalid_step(self):
        with patch("main.os.makedirs") as mkdir, patch("main.run_crawlers") as crawl, patch("main.run_preprocessors") as preprocess, patch("main.run_filters") as filtering:
            for step, expected in ((0, (1, 1, 1)), (1, (1, 0, 0)), (2, (0, 1, 0)), (3, (0, 0, 1))):
                with self.subTest(step=step):
                    crawl.reset_mock()
                    preprocess.reset_mock()
                    filtering.reset_mock()
                    run_pipeline(step=step)
                    self.assertEqual((crawl.call_count, preprocess.call_count, filtering.call_count), expected)
            self.assertEqual(mkdir.call_count, 16)
            with self.assertRaises(ValueError):
                run_pipeline(step=4)

    def test_pipeline_order_and_failure(self):
        order = []
        with patch("main.run_crawlers", side_effect=lambda: order.append("crawl")), patch("main.run_preprocessors", side_effect=lambda: order.append("preprocess")), patch("main.run_filters", side_effect=lambda: order.append("filter")):
            run_pipeline()
            self.assertEqual(order, ["crawl", "preprocess", "filter"])
            order.clear()
            run_pipeline(step=2)
            self.assertEqual(order, ["preprocess"])
        with patch("main.run_crawlers", side_effect=RuntimeError("failed")), patch("main.run_filters") as filtering:
            with self.assertRaises(RuntimeError):
                run_pipeline()
            filtering.assert_not_called()
