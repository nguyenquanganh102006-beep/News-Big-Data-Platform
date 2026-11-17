from datetime import date
import unittest
import pandas as pd
from dashboard.statistics import article_periods, event_periods


class DashboardStatisticsTests(unittest.TestCase):
    def test_vietnam_midnight_and_missing_days_and_week_boundary(self):
        frame = pd.DataFrame({'pub_date': ['2026-11-08T18:00:00Z', '2026-11-11T00:00:00Z', 'bad'],
                              'accident_label': ['accident', 'uncertain', 'accident']})
        result = article_periods(frame)
        self.assertEqual(result['Tổng bài'].tolist(), [1, 0, 1])
        self.assertEqual(str(result.index[0].date()), '2026-11-09')
        self.assertTrue(pd.isna(result.iloc[1]['Tỷ lệ tai nạn (%)']))
        weekly = article_periods(frame, 'W-MON')
        self.assertEqual(str(weekly.index[0].date()), '2026-11-09')
        self.assertEqual(int(weekly.iloc[0]['Tổng bài']), 2)
        bounded = article_periods(frame, 'D', (date(2026, 11, 7), date(2026, 11, 12)))
        self.assertEqual(len(bounded), 6)

    def test_casualties_remain_unknown_and_events_not_article_counts(self):
        frame = pd.DataFrame({'first_published_at': ['2026-11-09T18:00:00Z', '2026-11-12T00:00:00Z'],
                              'article_count': [10, 5], 'total_fatalities': [None, 2],
                              'total_injuries': [None, None]})
        result = event_periods(frame)
        self.assertEqual(result['Sự kiện'].tolist(), [1, 0, 1])
        self.assertEqual(int(result['Sự kiện'].sum()), 2)
        self.assertTrue(pd.isna(result.iloc[0]['Tử vong đã ghi nhận']))
        self.assertTrue(result['Bị thương đã ghi nhận'].isna().all())
