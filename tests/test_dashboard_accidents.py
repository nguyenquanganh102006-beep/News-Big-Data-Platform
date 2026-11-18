from datetime import date
import unittest

import pandas as pd

from dashboard.accidents import event_metrics, filter_events


class AccidentDashboardTests(unittest.TestCase):
    def setUp(self):
        self.events = pd.DataFrame({
            "event_id": ["a", "b", "c"], "province": ["Hà Nội", "Hà Nội", "Huế"],
            "article_count": [7, 3, 2], "total_fatalities": [2, None, 0],
            "total_injuries": [None, None, None],
            "first_published_at": ["2026-11-16T18:00:00Z", "2026-11-16T10:00:00Z", None]})

    def test_counts_events_not_articles_and_preserves_unknown(self):
        metrics = event_metrics(self.events)
        self.assertEqual(metrics["events"], 3)
        self.assertEqual(metrics["total_fatalities"], 2)
        self.assertEqual(metrics["total_fatalities_known"], 2)
        self.assertTrue(pd.isna(metrics["total_injuries"]))

    def test_filter_local_first_publication_and_province(self):
        result = filter_events(self.events, ["Hà Nội"], dates=(date(2026, 11, 17), date(2026, 11, 17)))
        self.assertEqual(result["event_id"].tolist(), ["a"])
        self.assertEqual(len(self.events), 3)

    def test_literal_query_and_empty_selection(self):
        self.assertTrue(filter_events(self.events, query="[").empty)
        self.assertEqual(event_metrics(self.events.iloc[:0])["events"], 0)


if __name__ == "__main__":
    unittest.main()
