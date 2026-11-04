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
from events.adapter import prepare_article
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

    def test_changed_assigned_article_updates_event_without_creating_review_or_new_link(self):
        paths = self.inputs({"test": [row("a")]})
        self.run_import(paths)
        event_id = self.query("SELECT event_id FROM accident_events")[0][0]
        paths = self.inputs({"test": [row("a", fatalities=9)]})
        stats = self.run_import(paths)
        self.assertEqual(stats["updated_assigned"], 1)
        self.assertEqual(stats["changed_input"], 0)
        self.assertEqual(self.query("SELECT event_id,total_fatalities FROM accident_events"), [(event_id,9)])
        self.assertEqual(self.query("SELECT fatalities FROM articles"), [(9,)])
        self.assertEqual(self.query("SELECT count(*) FROM match_reviews"), [(0,)])
        history = json.loads(self.query("SELECT previous_payload FROM article_revisions")[0][0])
        self.assertEqual(history["fatalities"], 2)
        self.assertEqual(self.query("SELECT count(*) FROM event_articles"), [(1,)])

    def test_updated_field_beats_old_reports_even_when_publication_time_is_unchanged(self):
        paths = self.inputs({"test": [row("a"), row("b")]})
        self.run_import(paths)
        event_id = self.query("SELECT event_id FROM accident_events")[0][0]
        paths = self.inputs({"test": [row("a", fatalities=3), row("b")]})
        self.run_import(paths)
        self.assertEqual(self.query("SELECT event_id,total_fatalities,article_count FROM accident_events"), [(event_id,3,2)])
        self.assertEqual(self.query("SELECT fatalities FROM articles ORDER BY article_key"), [(3,),(2,)])
        replay = self.run_import(paths)
        self.assertEqual(replay["updated_assigned"], 0)
        self.assertEqual(replay["already_processed"], 2)
        self.assertEqual(self.query("SELECT count(*) FROM article_revisions"), [(1,)])

    def test_newer_article_supersedes_older_casualty_figure_without_summing(self):
        self.run_import(self.inputs({"test": [row("a"), row("b", fatalities=3,
                        pub_date="2026-11-04T13:00:00+07:00")]}))
        self.assertEqual(self.query("SELECT total_fatalities,article_count FROM accident_events"), [(3,2)])

    def test_description_only_change_does_not_make_older_casualty_number_newer(self):
        self.run_import(self.inputs({"test": [row("a"), row("b", fatalities=3,
                        pub_date="2026-11-04T13:00:00+07:00")]}))
        stats = self.run_import(self.inputs({"test": [row("a", description="Tin bổ sung về xử lý giao thông.")]}))
        self.assertEqual(stats["updated_assigned"], 1)
        self.assertEqual(self.query("SELECT total_fatalities FROM accident_events"), [(3,)])

    def test_missing_fields_do_not_erase_known_values_but_explicit_zero_replaces_them(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        self.run_import(self.inputs({"test": [row("a", fatalities=None, province=None, pub_date=None)]}))
        self.assertEqual(self.query("SELECT total_fatalities,province FROM accident_events"), [(2,"Hà Nội")])
        self.run_import(self.inputs({"test": [row("a", fatalities=0)]}))
        self.assertEqual(self.query("SELECT total_fatalities FROM accident_events"), [(0,)])
        self.assertEqual(self.query("SELECT count(*) FROM article_revisions"), [(2,)])

    def test_event_location_correction_is_visible_to_new_articles_in_same_batch(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        event_id = self.query("SELECT event_id FROM accident_events")[0][0]
        paths = self.inputs({"test": [row("b", province="Nghệ An", district="Vinh",
                        pub_date="2026-11-04T11:30:00+07:00"), row("a", province="Nghệ An", district="Vinh")]})
        stats = self.run_import(paths)
        self.assertEqual((stats["updated_assigned"], stats["matched"]), (1,1))
        self.assertEqual(self.query("SELECT event_id,province,article_count FROM accident_events"), [(event_id,"Nghệ An",2)])
        self.assertIn("Nghệ An", self.query("SELECT location_full FROM accident_events")[0][0])

    def test_existing_database_with_legacy_index_supports_automatic_updates(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        with duckdb.connect(str(self.db)) as connection:
            connection.execute("CREATE INDEX event_province_time ON accident_events(province,anchor_published_at)")
        stats = self.run_import(self.inputs({"test": [row("a", province="Nghệ An", district="Vinh")]}))
        self.assertEqual(stats["updated_assigned"],1)
        self.assertEqual(self.query("SELECT province FROM accident_events"),[("Nghệ An",)])

    def test_assigned_update_and_revision_history_roll_back_if_event_refresh_fails(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        paths = self.inputs({"test": [row("a", fatalities=9)]})
        with patch.object(EventRepository, "refresh_event", side_effect=RuntimeError("refresh failed")):
            with self.assertRaisesRegex(RuntimeError,"refresh failed"):
                self.run_import(paths)
        self.assertEqual(self.query("SELECT fatalities FROM articles"), [(2,)])
        self.assertEqual(self.query("SELECT total_fatalities FROM accident_events"), [(2,)])
        self.assertEqual(self.query("SELECT count(*) FROM article_revisions"), [(0,)])

    def test_legacy_changed_input_review_is_closed_when_assigned_update_is_applied(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        updated = row("a", fatalities=4)
        repository = EventRepository(self.db)
        try:
            repository.save_review(prepare_article(updated), {
                "decision":"needs_review","reasons":["changed_input"],"scores":[]})
        finally:
            repository.close()
        stats = self.run_import(self.inputs({"test": [updated]}))
        self.assertEqual(stats["database"]["pending_reviews"],0)
        self.assertEqual(self.query("SELECT status FROM match_reviews"), [("resolved",)])

    def test_legacy_review_is_closed_if_current_gold_is_already_applied(self):
        paths = self.inputs({"test": [row("a")]})
        self.run_import(paths)
        repository = EventRepository(self.db)
        try:
            repository.save_review(prepare_article(row("a")), {
                "decision":"needs_review","reasons":["changed_input"],"scores":[]})
        finally:
            repository.close()
        stats = self.run_import(paths)
        self.assertEqual(stats["already_processed"],1)
        self.assertEqual(stats["updated_assigned"],0)
        self.assertEqual(stats["database"]["pending_reviews"],0)

    def test_enriched_unassigned_article_matches_existing_event_and_resolves_old_reviews(self):
        self.run_import(self.inputs({"test": [row("a"), row("b", province=None)]}))
        event_id = self.query("SELECT event_id FROM accident_events")[0][0]
        updated = row("b")
        # Reproduce the legacy changed_input review created before this fix.
        repository = EventRepository(self.db)
        try:
            repository.save_review(prepare_article(updated), {
                "decision": "needs_review", "reasons": ["changed_input"], "scores": [],
            })
        finally:
            repository.close()
        paths = self.inputs({"test": [row("a"), updated]})
        stats = self.run_import(paths)
        self.assertEqual((stats["already_processed"], stats["updated_unassigned"], stats["matched"]), (1, 1, 1))
        self.assertEqual(stats["changed_input"], 0)
        self.assertEqual(self.query("SELECT article_count FROM accident_events"), [(2,)])
        self.assertEqual(self.query("SELECT event_id FROM event_articles WHERE article_key='b'"), [(event_id,)])
        self.assertEqual(self.query("SELECT province FROM articles WHERE article_key='b'"), [("Hà Nội",)])
        self.assertEqual(self.query("SELECT status FROM match_reviews ORDER BY review_id"), [("resolved",), ("resolved",)])
        count = self.query("SELECT count(*) FROM match_reviews")
        replay = self.run_import(paths)
        self.assertEqual(replay["already_processed"], 2)
        self.assertEqual(replay["updated_unassigned"], 0)
        self.assertEqual(self.query("SELECT count(*) FROM match_reviews"), count)

    def test_enriched_unassigned_article_can_create_new_event_without_changing_old_one(self):
        missing = row("b", province=None, title="Xe tải va chạm xe máy tại Nghệ An")
        self.run_import(self.inputs({"test": [row("a"), missing]}))
        before = self.query("SELECT event_id,anchor_article_key,article_count,total_fatalities FROM accident_events")
        stats = self.run_import(self.inputs({"test": [row("a"), {**missing, "province": "Nghệ An"}]}))
        self.assertEqual((stats["updated_unassigned"], stats["new_event"]), (1, 1))
        self.assertEqual(stats["database"]["accident_events"], 2)
        self.assertEqual(stats["database"]["pending_reviews"], 0)
        self.assertEqual(self.query("SELECT event_id,anchor_article_key,article_count,total_fatalities "
                                    "FROM accident_events WHERE anchor_article_key='a'"), before)

    def test_enriched_but_still_incomplete_article_keeps_only_current_reason_pending(self):
        self.run_import(self.inputs({"test": [row("b", province=None)]}))
        paths = self.inputs({"test": [row("b", review_reasons=["missing_incident_details"])]})
        stats = self.run_import(paths)
        self.assertEqual((stats["updated_unassigned"], stats["needs_review"]), (1, 1))
        self.assertEqual(stats["database"]["pending_reviews"], 1)
        self.assertEqual(self.query("SELECT province FROM articles"), [("Hà Nội",)])
        self.assertEqual(self.query("SELECT reasons FROM match_reviews WHERE status='pending'"),
                         [(json.dumps(["missing_incident_details"]),)])
        self.assertEqual(self.run_import(paths)["database"], stats["database"])
        self.assertEqual(self.query("SELECT count(*) FROM match_reviews WHERE status='resolved'"), [(1,)])

    def test_failure_after_enrichment_rolls_back_article_update_and_review_resolution(self):
        self.run_import(self.inputs({"test": [row("a"), row("b", province=None)]}))
        before = self.query("SELECT article_key,province,input_fingerprint FROM articles ORDER BY article_key")
        paths = self.inputs({"test": [row("a"), row("b")]})
        with patch.object(EventRepository, "save_assignment", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                self.run_import(paths)
        self.assertEqual(self.query("SELECT article_key,province,input_fingerprint FROM articles ORDER BY article_key"), before)
        self.assertEqual(self.query("SELECT status FROM match_reviews"), [("pending",)])
        self.assertEqual(self.query("SELECT count(*) FROM event_articles"), [(1,)])

    def test_repository_refuses_updating_already_assigned_article(self):
        self.run_import(self.inputs({"test": [row("a")]}))
        repository = EventRepository(self.db)
        try:
            with self.assertRaisesRegex(ValueError, "already assigned"):
                repository.update_unassigned_article(prepare_article(row("a", fatalities=9)))
        finally:
            repository.close()
        self.assertEqual(self.query("SELECT fatalities FROM articles"), [(2,)])

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
