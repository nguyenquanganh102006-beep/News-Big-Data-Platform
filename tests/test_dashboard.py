from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
import polars as pl
from streamlit.testing.v1 import AppTest

from dashboard.data import filter_articles, read_database, discover_datasets
from batch.run import run_batch
from test_event_database import SCHEMA, row


class DashboardTests(unittest.TestCase):
    def test_only_current_dataset_and_preserves_historical_dates(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root/'dashboard_snapshots/current'
            current.mkdir(parents=True)
            (root/'diagnostics/old/data/silver/filtered').mkdir(parents=True)
            import json
            (root/'dashboard_current.json').write_text(json.dumps({'path':'dashboard_snapshots/current'}))
            datasets = discover_datasets(root)
            self.assertEqual(list(datasets.values()), [current.resolve()])
            pl.DataFrame({'title':['Old article','New article'], 'source':['test']*2,
                          'accident_label':['accident']*2,
                          'pub_date':['2026-09-01T00:00:00Z','2026-11-10T00:00:00Z']}).write_parquet(current/'articles.parquet')
            with patch('config.DATA_DIR', str(root)):
                app = AppTest.from_file(str(Path('src/dashboard/app.py').resolve()),default_timeout=30).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.metric[0].value,'2')
                self.assertFalse(any(s.label=='Bộ dữ liệu' for s in app.selectbox))
                self.assertFalse(app.checkbox[0].value)
    def test_search_is_literal_and_dates_use_vietnam_timezone(self):
        frame = pd.DataFrame({'title': ['Xe [1]', 'Tin khác'], 'source': ['one', 'two'],
                              'accident_label': ['accident', 'not_accident'],
                              'pub_date': ['2026-11-09T18:00:00Z', '2026-11-09T12:00:00Z']})
        result = filter_articles(frame, ['one'], ['accident'], '[1]', (date(2026, 11, 10), date(2026, 11, 10)))
        self.assertEqual(result['title'].tolist(), ['Xe [1]'])

    def test_reader_preserves_database_and_missing_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root/'test.parquet'
            pl.DataFrame([row('a'), row('b', province=None)], schema=SCHEMA).write_parquet(path)
            db = root/'canonical.duckdb'
            run_batch({'test': path}, db)
            before = db.read_bytes()
            snapshot = read_database(db)
            self.assertEqual((len(snapshot['events']), len(snapshot['reviews'])), (1, 1))
            self.assertEqual(snapshot['reviews']['title'].iloc[0], row('b')['title'])
            self.assertEqual(before, db.read_bytes())
            missing = root/'absent.duckdb'
            with self.assertRaises(FileNotFoundError):
                read_database(missing)
            self.assertFalse(missing.exists())

    def test_ui_filters_and_review_switch_without_data_changes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root/'silver/filtered/test'
            folder.mkdir(parents=True)
            file = folder/'classified.parquet'
            pl.DataFrame({'title': ['Xe va chạm', 'Chưa rõ'], 'source': ['test', 'test'],
                          'accident_label': ['accident', 'uncertain'],
                          'pub_date': ['2026-11-10T00:00:00Z']*2,
                          'description': ['Mô tả', 'Mô tả']}).write_parquet(file)
            before = file.read_bytes()
            with patch('config.DATA_DIR', str(root)):
                app = AppTest.from_file(str(Path('src/dashboard/app.py').resolve()), default_timeout=30).run()
                self.assertFalse(app.exception)
                app.multiselect[1].set_value(['accident']).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.metric[0].value, '1')
                app.radio[0].set_value('Matching / trích xuất').run()
                self.assertFalse(app.exception)
            self.assertEqual(before, file.read_bytes())

    def test_ui_empty_dataset_has_no_exception(self):
        with TemporaryDirectory() as tmp, patch('config.DATA_DIR', tmp):
            app = AppTest.from_file(str(Path('src/dashboard/app.py').resolve()), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, '0')
