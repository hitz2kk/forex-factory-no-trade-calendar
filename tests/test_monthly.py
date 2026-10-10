import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import browser_calendar as browser
import generate_no_trade_calendar as generator


class MonthlyCalendarTests(unittest.TestCase):
    def raw(self, month="2026-10", rows=None):
        return {"covered_days": list(browser.month_days(month)),
                "rendered_days": list(browser.month_days(month)),
                "display_timezone": "Europe/London", "rendered_event_count": 20,
                "incomplete_event_ids": [], "rows": rows or []}

    def row(self, day="Thu Oct 29", title="GDP", time="12:30pm", id="1"):
        return {"day": day, "id": id, "title": title, "country": "USD",
                "impact": "High Impact Expected", "time": time}

    def test_all_month_lengths_including_leap_year(self):
        for month, count in (("2026-10", 31), ("2026-11", 30), ("2026-02", 28), ("2028-02", 29)):
            self.assertEqual(len(browser.make_snapshot(self.raw(month), month)["covered_days"]), count)

    def test_partial_or_unrendered_month_and_wrong_timezone_are_rejected(self):
        for field, value in (("covered_days", []), ("rendered_days", []),
                             ("display_timezone", "America/New_York"),
                             ("incomplete_event_ids", ["1"]), ("rendered_event_count", 0)):
            raw = self.raw()
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                browser.make_snapshot(raw, "2026-10")

    def test_dst_and_separate_simultaneous_releases(self):
        rows = [self.row("Wed Oct 14", time="1:30pm"),
                self.row(title="GDP"), self.row(title="Core PCE", id="2")]
        snapshot = browser.make_snapshot(self.raw(rows=rows), "2026-10")
        self.assertEqual(snapshot["events"][0]["date"], "2026-10-14T13:30:00+01:00")
        self.assertEqual(snapshot["events"][1]["date"], "2026-10-29T12:30:00+00:00")
        events = generator.parse_events(json.dumps(snapshot["events"]), ZoneInfo("Europe/London"))
        self.assertEqual(len(generator.dedupe_events(events + events)), 3)

    def test_tentative_event_is_retained_but_not_given_invented_time(self):
        snapshot = browser.make_snapshot(self.raw(rows=[self.row(time="Tentative")]), "2026-10")
        self.assertEqual(snapshot["events"], [])
        self.assertEqual(snapshot["untimed_events"][0]["title"], "GDP")

    def test_changed_or_removed_events_replace_snapshot_without_timestamp_churn(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            original = browser.make_snapshot(self.raw(rows=[self.row()]), "2026-10")
            self.assertTrue(browser.write_snapshot(path, original))
            updated = copy.deepcopy(original)
            updated["updated_at"] = "2026-10-10T17:00:00+00:00"
            self.assertFalse(browser.write_snapshot(path, updated))
            updated["events"] = []
            self.assertTrue(browser.write_snapshot(path, updated))
            self.assertEqual(generator.load_month_snapshot(path, date(2026, 10, 1), ZoneInfo("Europe/London")), [])

    def test_november_rollover_excludes_october(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "snapshot.json"
            output = Path(directory) / "calendar.ics"
            browser.write_snapshot(snapshot_path, browser.make_snapshot(self.raw(rows=[self.row()]), "2026-10"))
            args = ["generator", "--snapshot", str(snapshot_path), "--output", str(output), "--month", "2026-11"]
            with patch.object(sys, "argv", args):
                generator.main()
            november = self.raw("2026-11", [self.row("Mon Nov 2", time="1:30pm")])
            self.assertNotIn("BEGIN:VEVENT", output.read_text())
            browser.write_snapshot(snapshot_path, browser.make_snapshot(november, "2026-11"))
            with patch.object(sys, "argv", args):
                generator.main()
            self.assertIn("DTSTART:20261102T131500Z", output.read_text())
            self.assertNotIn("20261029", output.read_text())

    def test_invalid_snapshot_does_not_replace_live_calendar(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "snapshot.json"
            snapshot_path.write_text('{"month":"2026-10"}')
            output = Path(directory) / "calendar.ics"
            output.write_text("last valid calendar")
            with patch.object(sys, "argv", ["generator", "--snapshot", str(snapshot_path), "--output", str(output)]):
                with self.assertRaises(ValueError):
                    generator.main()
            self.assertEqual(output.read_text(), "last valid calendar")
