from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import duckdb
import polars as pl

from events.run import run_events
from events.repository import EventRepository
from events.inspect import show_database


SCHEMA = {
    "article_key": pl.String, "source": pl.String, "link": pl.String,
    "title": pl.String, "description": pl.String, "pub_date": pl.String,
    "province": pl.String, "district": pl.String, "ward": pl.String,
    "vehicles": pl.List(pl.String), "fatalities": pl.Int64, "injuries": pl.Int64,
    "review_reasons": pl.List(pl.String),
}


def row(key, source="test", **changes):
    result = {"article_key": key, "source": source, "link": f"https://example.com/{key}",
              "title": "Xe tải va chạm xe máy tại Hà Nội", "description": "Tai nạn ở quận Cầu Giấy.",
              "pub_date": "2026-11-04T12:00:00+07:00", "province": "Hà Nội",
              "district": "Cầu Giấy", "ward": None, "vehicles": ["xe tải", "xe máy"],
              "fatalities": 2, "injuries": None, "review_reasons": []}
    result.update(changes)
    return result


class EventDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "events.duckdb"
        self.exports = self.root / "exports"

    def inputs(self, rows_by_source):
        paths = {}
        for source, rows in rows_by_source.items():
            paths[source] = self.root / f"{source}.parquet"
            pl.DataFrame(rows, schema=SCHEMA).write_parquet(paths[source])
        return paths

    def run_import(self, paths):
        with redirect_stdout(StringIO()):
            return run_events(paths, self.db, self.exports)

    def query(self, sql):
        with duckdb.connect(str(self.db), read_only=True) as connection:
            return connection.execute(sql).fetchall()

    def test_same_event_cross_source_has_two_articles_not_double_casualties(self):
        paths = self.inputs({"one": [row("a", "one")], "two": [row("b", "two")]})
        before = {p: p.read_bytes() for p in paths.values()}
        stats = self.run_import(paths)
        self.assertEqual((stats["new_event"], stats["matched"]), (1, 1))
        self.assertEqual(self.query("SELECT article_count,total_fatalities,total_injuries,time_occurred FROM accident_events"),
                         [(2, 2, None, None)])
        urls = self.query("SELECT list_article_urls FROM accident_event_summary")[0][0]
        self.assertEqual(len(urls), 2)
        self.assertEqual({p: p.read_bytes() for p in paths.values()}, before)
        exported = pl.read_parquet(self.exports / "articles.parquet")
        self.assertEqual(exported["event_id"].n_unique(), 1)
        self.assertEqual(exported.height, 2)

    def test_repeat_preserves_ids_counts_and_pending_reviews(self):
        paths = self.inputs({"test": [row("a"), row("b", province=None), row(None, province=None)]})
        first = self.run_import(paths)
        ids = self.query("SELECT event_id FROM accident_events")
        second = self.run_import(paths)
        self.assertEqual(first["database"], second["database"])
        self.assertEqual(second["already_processed"], 1)
        self.assertEqual(ids, self.query("SELECT event_id FROM accident_events"))
        self.assertEqual(self.query("SELECT count(*) FROM match_reviews"), [(2,)])
        self.assertEqual(self.query("SELECT count(*) FROM articles"), [(2,)])

    def test_casualty_conflict_keeps_null_and_both_sources(self):
        self.run_import(self.inputs({"test": [row("a"), row("b", fatalities=3)]}))
        count, reasons, evidence = self.query(
            "SELECT total_fatalities,review_reasons,aggregation_evidence FROM accident_events")[0]
        self.assertIsNone(count)
        self.assertIn("conflicting_fatalities", json.loads(reasons))
        self.assertEqual(len(json.loads(evidence)["fatalities"]), 2)

    def test_missing_count_is_not_zero_but_explicit_zero_is_retained(self):
        self.run_import(self.inputs({"test": [row("a", fatalities=0), row("b", fatalities=None)]}))
        self.assertEqual(self.query("SELECT total_fatalities,total_injuries FROM accident_events"), [(0, None)])

    def test_upstream_casualty_conflict_is_not_hidden_by_other_report(self):
        self.run_import(self.inputs({"test": [row("a"), row("b", fatalities=None,
                        review_reasons=["conflicting_fatalities"])]}))
        self.assertIsNone(self.query("SELECT total_fatalities FROM accident_events")[0][0])

    def test_human_readable_summary_does_not_modify_database(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        before = self.db.read_bytes()
        output = StringIO()
        with redirect_stdout(output):
            show_database(self.db)
        self.assertIn("sự kiện: 1", output.getvalue())
        self.assertIn("bị thương: chưa rõ", output.getvalue())
        self.assertEqual(self.db.read_bytes(), before)

    def test_empty_and_later_new_input_find_events_from_previous_runs(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        stats = self.run_import(self.inputs({"test": []}))
        self.assertEqual(stats["database"]["accident_events"], 1)
        stats = self.run_import(self.inputs({"test": [row("b")]}))
        self.assertEqual(stats["matched"], 1)
        self.assertEqual(stats["database"]["accident_events"], 1)

    def test_fixed_anchor_prevents_a_chain_of_reports_extending_window(self):
        self.run_import(self.inputs({"test": [
            row("a", pub_date="2026-11-04T00:00:00Z"),
            row("b", pub_date="2026-11-04T23:00:00Z"),
            row("c", pub_date="2026-11-05T22:00:00Z"),
        ]}))
        self.assertEqual(self.query("SELECT article_count FROM accident_events ORDER BY article_count"), [(1,), (2,)])

    def test_export_failure_keeps_committed_database_and_retry_is_safe(self):
        paths = self.inputs({"test": [row("a")]})
        with patch.object(EventRepository, "export", side_effect=OSError("export failed")):
            with self.assertRaisesRegex(OSError, "export failed"):
                self.run_import(paths)
        self.assertEqual(self.query("SELECT count(*) FROM accident_events"), [(1,)])
        stats = self.run_import(paths)
        self.assertEqual(stats["already_processed"], 1)
        self.assertEqual(pl.read_parquet(self.exports / "accident_events.parquet").height, 1)

    def test_different_locations_and_ambiguous_article(self):
        paths = self.inputs({"test": [row("a", ward="A"), row("b", ward="B"), row("c")]})
        stats = self.run_import(paths)
        self.assertEqual(stats["new_event"], 2)
        self.assertEqual(stats["needs_review"], 1)
        self.assertEqual(self.query("SELECT article_key FROM articles WHERE article_key NOT IN (SELECT article_key FROM event_articles)"), [("c",)])

    def test_changed_input_keeps_previous_link_and_payload(self):
        paths = self.inputs({"test": [row("a")]})
        self.run_import(paths)
        before = self.query("SELECT event_id,total_fatalities FROM accident_events")
        paths = self.inputs({"test": [row("a", fatalities=9)]})
        self.assertEqual(self.run_import(paths)["changed_input"], 1)
        self.assertEqual(self.query("SELECT event_id,total_fatalities FROM accident_events"), before)
        self.assertEqual(self.query("SELECT fatalities FROM articles"), [(2,)])
        self.assertEqual(self.query("SELECT count(*) FROM match_reviews"), [(1,)])

    def test_empty_gold_creates_queryable_empty_database_and_exports(self):
        stats = self.run_import(self.inputs({"test": []}))
        self.assertEqual(stats["input"], 0)
        self.assertEqual(stats["database"]["accident_events"], 0)
        frame = pl.read_parquet(self.exports / "accident_events.parquet")
        self.assertEqual(frame.height, 0)
        self.assertIn("list_article_urls", frame.columns)

    def test_missing_input_or_bad_schema_stops_before_creating_database(self):
        good = self.inputs({"test": [row("a")]})
        with self.assertRaises(FileNotFoundError):
            self.run_import({**good, "missing": self.root / "missing.parquet"})
        self.assertFalse(self.db.exists())
        pl.DataFrame({"title": ["test"]}).write_parquet(good["test"])
        with self.assertRaises(ValueError):
            self.run_import(good)
        self.assertFalse(self.db.exists())

    def test_conflicting_input_keys_are_not_silently_deduplicated(self):
        paths = self.inputs({"test": [row("a"), row("a", fatalities=9)]})
        with self.assertRaisesRegex(ValueError, "Conflicting Gold"):
            self.run_import(paths)
        self.assertFalse(self.db.exists())

    def test_failure_rolls_back_articles_links_and_event_updates(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        before = self.query("SELECT event_id,article_count,total_fatalities FROM accident_events")
        paths = self.inputs({"test": [row("a"), row("b"), row("c", district="Ba Đình")]})
        refresh = EventRepository.refresh_event
        calls = []

        def fail_on_second(repository, *args):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("simulated disk error")
            return refresh(repository, *args)

        with patch.object(EventRepository, "refresh_event", new=fail_on_second):
            with self.assertRaisesRegex(RuntimeError, "simulated disk error"):
                self.run_import(paths)
        self.assertEqual(self.query("SELECT event_id,article_count,total_fatalities FROM accident_events"), before)
        self.assertEqual(self.query("SELECT count(*) FROM articles"), [(1,)])
        self.assertEqual(self.query("SELECT count(*) FROM event_articles"), [(1,)])

    def test_foreign_keys_reject_orphan_links(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        with duckdb.connect(str(self.db)) as connection:
            with self.assertRaises(duckdb.ConstraintException):
                connection.execute("UPDATE event_articles SET event_id='missing'")
