from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import polars as pl
from config import MatchConfig

from events.evaluate import evaluate


class EventEvaluationTests(unittest.TestCase):
    def test_positive_abstention_counts_as_miss_and_existing_output_is_refused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / 'inputs'
            inputs.mkdir()
            pl.DataFrame({
                'article_key': ['a', 'b'], 'source': ['test', 'test'],
                'link': ['https://example.org/a', 'https://example.org/b'],
                'title': ['Xe tải va chạm xe máy', 'Xe tải va chạm xe máy'],
                'pub_date': ['2026-11-04T08:00:00+07:00'] * 2,
                'province': ['Hà Nội', None],
            }).write_parquet(inputs / 'test.parquet')
            labels = root / 'labels.json'
            labels.write_text(json.dumps({'provenance': 'Unit test of metric accounting only',
                                         'pairs': [{'left': 'a', 'right': 'b', 'same_event': True}]}))
            with redirect_stdout(StringIO()):
                result = evaluate(inputs, root / 'output', labels, config=MatchConfig(semantic_model=None))
            self.assertEqual(result['metrics']['fn'], 1)
            self.assertEqual(result['metrics']['abstained_pairs'], 1)
            self.assertEqual(result['metrics']['recall_including_abstentions'], 0)
            with self.assertRaises(FileExistsError):
                evaluate(inputs, root / 'output', labels)

    def test_empty_input_is_rejected_before_output_creation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                evaluate(root, root / 'output')
            self.assertFalse((root / 'output').exists())
