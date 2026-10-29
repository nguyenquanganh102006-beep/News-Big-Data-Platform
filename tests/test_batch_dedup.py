import unittest

import polars as pl
from polars.testing import assert_frame_equal

from preprocessors.utils import dedup_batch
from preprocessors.utils import dedup_add_article_identity


class BatchDedupTests(unittest.TestCase):
    def test_keeps_last_row_and_all_null_keys_in_order(self):
        df = pl.DataFrame({
            "article_key": ["a", None, "b", "a", None],
            "title": ["old", "unknown one", "different", "updated", "unknown two"],
        })
        result = dedup_batch(df)
        self.assertEqual(result["title"].to_list(),
                         ["unknown one", "different", "updated", "unknown two"])
        assert_frame_equal(dedup_batch(result), result)

    def test_tracking_duplicates_removed_but_same_title_different_ids_kept(self):
        df = dedup_add_article_identity(pl.DataFrame({
            "link": ["https://example.com/?id=1&utm_source=x",
                     "https://example.com/?id=2", "https://example.com/?id=1#comments"],
            "title": ["same title"] * 3,
        }), "vnexpress")
        result = dedup_batch(df)
        self.assertEqual(result.height, 2)
        self.assertEqual(result["link"].to_list(), df["link"].to_list()[1:])

    def test_empty_and_unique_batches_unchanged(self):
        for keys in ([], [None, None], ["a", "b"]):
            df = pl.DataFrame({"article_key": pl.Series(keys, dtype=pl.String)})
            assert_frame_equal(dedup_batch(df), df)


if __name__ == "__main__":
    unittest.main()
