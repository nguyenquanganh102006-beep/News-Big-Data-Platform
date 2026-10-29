from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import polars as pl

from preprocessors.utils import dedup_new_articles_only, dedup_update_silver_history
from preprocessors.utils import dedup_add_article_identity


def batch(ids):
    return dedup_add_article_identity(pl.DataFrame({
        "link": [f"https://example.com/?id={i}" for i in ids],
        "title": ["same title"] * len(ids),
    }), "vnexpress")


class SilverHistoryTests(unittest.TestCase):
    def test_summary_counts_both_duplicate_stages_and_persists_new(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "silver.parquet")
            dedup_update_silver_history(batch([1]), str(path), "vnexpress")
            output = StringIO()
            with redirect_stdout(output), patch("preprocessors.utils.DEBUG", True):
                new = dedup_update_silver_history(batch([1, 2, 2, 3]), str(path), "vnexpress")
            self.assertEqual(new.height, 2)
            self.assertEqual(pl.read_parquet(path).height, 3)
            self.assertIn("input=4, batch_duplicates=1, history_duplicates=1, new=2, silver_total=3, status=saved", output.getvalue())

    def test_debug_false_suppresses_summary(self):
        with TemporaryDirectory() as tmp, patch("preprocessors.utils.DEBUG", False):
            output = StringIO()
            with redirect_stdout(output):
                dedup_update_silver_history(batch([1]), str(Path(tmp, "silver.parquet")), "vnexpress")
            self.assertEqual(output.getvalue(), "")

    def test_append_then_repeat_and_dry_run(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "nested", "silver.parquet")
            self.assertEqual(dedup_update_silver_history(batch([1, 2]), str(path), "vnexpress").height, 2)
            original = path.read_bytes()
            new = dedup_update_silver_history(batch([2, 3]), str(path), "vnexpress", save_file=False)
            self.assertEqual(new["link"].to_list(), batch([3])["link"].to_list())
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(dedup_update_silver_history(batch([2, 3]), str(path), "vnexpress").height, 1)
            self.assertEqual(pl.read_parquet(path).height, 3)
            self.assertEqual(dedup_update_silver_history(batch([2, 3]), str(path), "vnexpress").height, 0)
            self.assertEqual(pl.read_parquet(path).height, 3)

    def test_null_keys_do_not_match_history(self):
        history = pl.DataFrame({"article_key": ["a", None]})
        incoming = pl.DataFrame({"article_key": [None, "a", "b", None]})
        self.assertEqual(dedup_new_articles_only(incoming, history)["article_key"].to_list(), [None, "b", None])

    def test_legacy_silver_gets_keys(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "silver.parquet")
            batch([1]).select("link", "title").write_parquet(path)
            self.assertEqual(dedup_update_silver_history(batch([1, 2]), str(path), "vnexpress").height, 1)
            self.assertEqual(pl.read_parquet(path)["article_key"].null_count(), 0)
            self.assertEqual(pl.read_parquet(path).height, 2)


if __name__ == "__main__":
    unittest.main()
