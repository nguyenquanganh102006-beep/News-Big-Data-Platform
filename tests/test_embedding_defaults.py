"""Embedding defaults and explicit offline mode, without network downloads."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import polars as pl

from config import DEFAULT_SEMANTIC_MODEL, MatchConfig
from events.cli import add_matching_arguments, matching_config
from events.run import run_events
from events.similarity import TextModel


class EmbeddingDefaultsTests(unittest.TestCase):
    def options(self, *values):
        parser = argparse.ArgumentParser()
        add_matching_arguments(parser)
        return matching_config(parser.parse_args(values))

    def test_api_and_cli_enable_embeddings_by_default(self):
        self.assertEqual(MatchConfig().semantic_model, DEFAULT_SEMANTIC_MODEL)
        self.assertEqual(self.options().semantic_model, DEFAULT_SEMANTIC_MODEL)

    def test_cache_option_does_not_disable_default_model(self):
        config = self.options('--model-cache', '/tmp/test-model-cache')
        self.assertEqual(config.semantic_model, DEFAULT_SEMANTIC_MODEL)
        self.assertEqual(config.semantic_cache_dir, '/tmp/test-model-cache')

    def test_offline_mode_is_explicit(self):
        self.assertIsNone(self.options('--no-embedding').semantic_model)
        self.assertIsNone(MatchConfig(semantic_model=None).semantic_model)

    def test_model_override_and_offline_flag_are_mutually_exclusive(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            self.options('--no-embedding', '--semantic-model', 'another-model')

    def test_text_model_builds_embeddings_without_an_explicit_model_argument(self):
        calls = []

        class Encoder:
            def __init__(self, **kwargs):
                calls.append(kwargs)

            def token_count(self, text):
                return len(text.split()) + 2

            def embed(self, texts, batch_size):
                return iter(np.array([1.0, 0.5], dtype=np.float32) for _ in texts)

        with patch.dict(sys.modules, {'fastembed': SimpleNamespace(TextEmbedding=Encoder)}), \
             patch('events.similarity._ENCODERS', {}), patch('events.similarity.version', return_value='test'):
            model = TextModel(['Một vụ tai nạn.'])
        self.assertEqual(calls[0]['model_name'], DEFAULT_SEMANTIC_MODEL)
        self.assertAlmostEqual(model.semantic_similarity('Một vụ tai nạn.', 'Một vụ tai nạn.'), 1.0, places=6)

    def test_missing_backend_does_not_silently_fall_back(self):
        with patch.dict(sys.modules, {'fastembed': None}):
            with self.assertRaisesRegex(RuntimeError, 'dependency missing'):
                TextModel(['Một vụ tai nạn.'])
            lexical = TextModel(['Một vụ tai nạn.'], semantic_model=None)
            self.assertIsNone(lexical.semantic_similarity('Một vụ tai nạn.', 'Một vụ tai nạn.'))

    def test_runner_passes_default_model_to_encoder(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'test.parquet'
            pl.DataFrame({
                'article_key': ['a'], 'source': ['test'], 'link': ['https://example.org/a'],
                'title': ['Xe tải va chạm xe máy tại Hà Nội'],
                'pub_date': ['2026-11-04T08:00:00+07:00'], 'province': ['Hà Nội'],
            }).write_parquet(path)
            with patch('events.run.TextModel') as factory, redirect_stdout(StringIO()):
                factory.return_value.fingerprint = 'test-model-fingerprint'
                result = run_events({'test': path}, root / 'events.duckdb', root / 'exports')
            self.assertEqual(factory.call_args.kwargs['semantic_model'], DEFAULT_SEMANTIC_MODEL)
            self.assertEqual(result['new_event'], 1)
