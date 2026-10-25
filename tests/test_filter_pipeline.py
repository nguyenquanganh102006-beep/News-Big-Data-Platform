from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import polars as pl
from polars.testing import assert_frame_equal

from filters.run import filter_frame, filter_silver_file
from pipeline import run_pipeline


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

    def test_pipeline_order_and_failure(self):
        order = []
        with patch("pipeline.run_crawlers", side_effect=lambda: order.append("crawl")), patch("pipeline.run_preprocessors", side_effect=lambda: order.append("preprocess")), patch("pipeline.run_filters", side_effect=lambda: order.append("filter")):
            run_pipeline()
            self.assertEqual(order, ["crawl", "preprocess", "filter"])
            order.clear()
            run_pipeline(skip_crawl=True)
            self.assertEqual(order, ["preprocess", "filter"])
        with patch("pipeline.run_crawlers", side_effect=RuntimeError("failed")), patch("pipeline.run_filters") as filtering:
            with self.assertRaises(RuntimeError):
                run_pipeline()
            filtering.assert_not_called()
