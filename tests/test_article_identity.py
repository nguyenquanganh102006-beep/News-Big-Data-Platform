import unittest

import polars as pl

from preprocessors.utils import dedup_add_article_identity, dedup_normalize_article_url


class ArticleIdentityTests(unittest.TestCase):
    def test_tracking_variants_share_key(self):
        df = dedup_add_article_identity(pl.DataFrame({"link": [
            " https://EXAMPLE.com/news?id=42&utm_source=facebook#comments ",
            "https://example.com/news?id=42&fbclid=abc",
        ]}), "vnexpress")
        self.assertEqual(df["normalized_url"].to_list(), ["https://example.com/news?id=42"] * 2)
        self.assertEqual(df["article_key"].n_unique(), 1)

    def test_business_query_is_preserved(self):
        url = "https://example.com/news?id=42&tag=a%20b&tag=c&ref=home&UTM_MEDIUM=x"
        self.assertEqual(dedup_normalize_article_url(url), "https://example.com/news?id=42&tag=a%20b&tag=c&ref=home")
        df = dedup_add_article_identity(pl.DataFrame({"link": [
            "https://example.com/news?id=42", "https://example.com/news?id=43",
        ]}), "vnexpress")
        self.assertEqual(df["article_key"].n_unique(), 2)

    def test_source_is_part_of_key(self):
        df = pl.DataFrame({"link": ["https://example.com/news"]})
        self.assertNotEqual(dedup_add_article_identity(df, "vnexpress")["article_key"][0],
                            dedup_add_article_identity(df, "tuoitre")["article_key"][0])

    def test_invalid_urls_have_no_key_and_rows_are_kept(self):
        urls = [None, "", "   ", "/news", "javascript:alert(1)",
                "https://example.com/a b", "https://example.com:bad/news"]
        df = dedup_add_article_identity(pl.DataFrame({"link": urls}), "vnexpress")
        self.assertEqual(df.height, len(urls))
        self.assertEqual(df["article_key"].null_count(), len(urls))


if __name__ == "__main__":
    unittest.main()
