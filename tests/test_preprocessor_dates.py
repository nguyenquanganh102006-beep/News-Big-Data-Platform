from datetime import datetime, timezone
import unittest

from preprocessors.utils import convert_string_to_datetime_utc


class PreprocessorDatesTests(unittest.TestCase):
    def test_rss_offset_is_preserved(self):
        self.assertEqual(
            convert_string_to_datetime_utc("Wed, 04 Nov 2026 12:00:00 +0700"),
            datetime(2026, 11, 4, 5, tzinfo=timezone.utc),
        )

    def test_different_rss_offsets_describe_same_instant(self):
        self.assertEqual(
            convert_string_to_datetime_utc("Wed, 04 Nov 2026 05:00:00 +0000"),
            convert_string_to_datetime_utc("Wed, 04 Nov 2026 12:00:00 +0700"),
        )

    def test_naive_source_date_still_uses_source_timezone(self):
        self.assertEqual(
            convert_string_to_datetime_utc("11/04/2026 12:00:00 PM", "%m/%d/%Y %I:%M:%S %p", 7),
            datetime(2026, 11, 4, 5, tzinfo=timezone.utc),
        )
