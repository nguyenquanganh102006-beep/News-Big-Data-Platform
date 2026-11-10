from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import duckdb
import polars as pl

from batch.run import run_batch
from config import MatchConfig
from events.adapter import prepare_article
from events.matching import decide_match
from events.service import MatchingService
from events.similarity import TextModel
from streaming.consumer import writer_lock
from streaming.pipeline import ArticleProcessor
from test_event_database import SCHEMA, row


class CanonicalBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'test.parquet'
        self.db = self.root / 'canonical.duckdb'

    def write(self, rows):
        pl.DataFrame(rows, schema=SCHEMA).write_parquet(self.path)
        return {'test': self.path}

    def query(self, sql):
        with duckdb.connect(str(self.db), read_only=True) as c:
            return c.execute(sql).fetchall()

    def test_full_rebuild_repeat_and_correction(self):
        paths = self.write([row('a'), row('b'), row('c', province=None), row('a')])
        before = self.path.read_bytes()
        stats = run_batch(paths, self.db)
        self.assertEqual((stats['input'], stats['new_event'], stats['matched'], stats['needs_review']), (3, 1, 1, 1))
        snapshot = self.query('SELECT article_key,event_id FROM canonical_event_articles ORDER BY article_key')
        run_batch(paths, self.db)
        self.assertEqual(snapshot, self.query('SELECT article_key,event_id FROM canonical_event_articles ORDER BY article_key'))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(any('provisional' in t[0] for t in self.query('SHOW TABLES')))
        self.write([row('a'), row('b', district='Ba Đình'), row('c', province=None)])
        stats = run_batch(paths, self.db)
        self.assertEqual(stats['new_event'], 2)
        self.assertEqual(stats['matched'], 0)

    def test_failure_preserves_previous_database(self):
        paths = self.write([row('a')])
        run_batch(paths, self.db)
        before = self.db.read_bytes()
        with patch('batch.run.MatchingService.decide', side_effect=RuntimeError('injected failure')):
            with self.assertRaises(RuntimeError):
                run_batch(paths, self.db)
        self.assertEqual(self.db.read_bytes(), before)
        with patch.object(Path, 'replace', side_effect=PermissionError('reader holding file')):
            with self.assertRaises(PermissionError):
                run_batch(paths, self.db)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.query('SELECT count(*) FROM canonical_events'), [(1,)])
        self.assertFalse(list(self.root.glob('canonical-stage-*')))

    def test_missing_empty_conflicting_and_invalid_inputs_preserve_database(self):
        paths = self.write([row('a')])
        run_batch(paths, self.db)
        before = self.db.read_bytes()
        with self.assertRaises(FileNotFoundError):
            run_batch({'missing': self.root/'missing.parquet'}, self.db)
        for rows in ([], [row('a'), row('a', fatalities=9)]):
            self.write(rows)
            with self.assertRaises(ValueError):
                run_batch(paths, self.db)
        pl.DataFrame({'invalid': [1]}).write_parquet(self.path)
        with self.assertRaises(ValueError):
            run_batch(paths, self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_unkeyed_input_is_retained_in_review(self):
        stats = run_batch(self.write([row(None), row(None)]), self.db)
        self.assertEqual(stats['needs_review'], 1)
        self.assertEqual(self.query('SELECT article_key FROM canonical_match_reviews'), [(None,)])

    def test_refuses_to_overwrite_unrelated_database(self):
        paths = self.write([row('a')])
        with duckdb.connect(str(self.db)) as c:
            c.execute('CREATE TABLE provisional_events (event_id VARCHAR)')
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            run_batch(paths, self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_writer_lock_prevents_second_batch(self):
        paths = self.write([row('a')])
        with writer_lock(self.db):
            with self.assertRaises(OSError):
                run_batch(paths, self.db)
        self.assertFalse(self.db.exists())


class MatchingContractTests(unittest.TestCase):
    def test_shared_service_preserves_phase_three_decision(self):
        article = prepare_article(row('a'))
        model = TextModel([article['text']])
        class Repository:
            def find_candidates(self, *args):
                return []
        service = MatchingService()
        actual = service.decide(article, Repository(), {}, model)
        expected = decide_match(article, [], model, MatchConfig())
        self.assertEqual({k: actual[k] for k in expected}, expected)
        self.assertEqual(actual['model_fingerprint'], model.fingerprint)

    def test_streaming_inclusive_24h_and_no_future_candidates(self):
        article = prepare_article(row('a'))
        model = TextModel([article['text']])
        seen = []
        class Repository:
            def find_candidates(self, article, config, articles):
                seen.append(config.radius_hours)
                return [dict(event_id=str(hours), anchor_published_at=article['published_at']+timedelta(hours=hours))
                        for hours in (-24, -23.999, 0, 1)]
        service = ArticleProcessor(None).matching
        with patch('events.service.decide_match', return_value={'decision': 'new_event'}) as decide:
            service.decide(article, Repository(), {}, model)
            candidates = decide.call_args.args[1]
            self.assertEqual([c['event_id'] for c in candidates], ['-24', '-23.999', '0'])
        self.assertEqual(seen, [24])

    def test_real_retrieval_boundary_and_batch_radius(self):
        from events.repository import EventRepository
        with TemporaryDirectory() as tmp:
            repo = EventRepository(Path(tmp)/'events.duckdb')
            try:
                repo.initialize()
                anchor = prepare_article(row('a'))
                repo.insert_article(anchor)
                decision = {'decision': 'new_event'}
                repo.save_assignment(anchor, decision, 'config', 'model')
                stored = {'a': anchor}
                for delta, count in ((24, 1), (24.001, 0)):
                    article = {**anchor, 'published_at': anchor['published_at']+timedelta(hours=delta)}
                    self.assertEqual(len(repo.find_candidates(article, MatchConfig(radius_hours=24), stored)), count)
                    self.assertEqual(len(repo.find_candidates(article, MatchConfig(), stored)), 1)
            finally:
                repo.close()
