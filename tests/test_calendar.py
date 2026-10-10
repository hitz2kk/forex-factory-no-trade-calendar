import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, time, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from zoneinfo import ZoneInfo


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_no_trade_calendar.py"
SPEC = importlib.util.spec_from_file_location("generator", SCRIPT)
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


def event(title="CPI", date="2026-10-14T08:30:00-04:00", country="USD", impact="High"):
    return {"title": title, "date": date, "country": country, "impact": impact}


def calendar(items, generated_at=None):
    events = generator.parse_events(json.dumps(items), ZoneInfo("Europe/London"))
    selected = generator.filter_events(events, {"USD", "GBP", "EUR"}, time(8), time(17))
    return generator.build_ics(
        selected,
        minutes_before=15,
        minutes_after=15,
        generated_at=generated_at or datetime(2026, 10, 10, tzinfo=timezone.utc),
    )


class CalendarTests(unittest.TestCase):
    def test_uk_filter_boundaries_in_summer_and_winter(self):
        for day in ("2026-10-14", "2026-12-14"):
            with self.subTest(day=day):
                items = [
                    event("Before", f"{day}T07:59:00", impact="High"),
                    event("Start", f"{day}T08:00:00", country="GBP"),
                    event("End", f"{day}T17:00:00", country="EUR"),
                    event("After", f"{day}T17:01:00"),
                    event("Other currency", f"{day}T10:00:00", country="CAD"),
                    event("Medium", f"{day}T10:00:00", impact="Medium"),
                ]
                for item in items:
                    item["date"] = datetime.fromisoformat(item["date"]).replace(
                        tzinfo=ZoneInfo("Europe/London")
                    ).isoformat()
                result = calendar(items)
                self.assertEqual(result.count("BEGIN:VEVENT"), 2)
                self.assertIn("GBP Start", result)
                self.assertIn("EUR End", result)

    def test_unchanged_events_keep_file_and_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "calendar.ics"
            original = calendar([event()])
            self.assertTrue(generator.write_calendar(output, original))
            later = datetime(2026, 10, 10, 1, tzinfo=timezone.utc)
            self.assertFalse(generator.write_calendar(output, calendar([event()], later)))
            self.assertEqual(output.read_bytes(), original.encode("utf-8"))

    def test_changed_release_and_removal_replace_previous_events(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "calendar.ics"
            generator.write_calendar(output, calendar([event(), event("Retail Sales")]))
            updated = calendar([event(date="2026-10-14T09:00:00-04:00")])
            self.assertTrue(generator.write_calendar(output, updated))
            result = output.read_text()
            self.assertEqual(result.count("BEGIN:VEVENT"), 1)
            self.assertIn("DTSTART:20261014T124500Z", result)
            self.assertNotIn("DTSTART:20261014T121500Z", result)
            self.assertNotIn("Retail Sales", result)

    def test_valid_feed_with_no_matching_events_clears_blocks(self):
        self.assertNotIn("BEGIN:VEVENT", calendar([event(impact="Low")]))

    def test_invalid_feed_preserves_last_calendar(self):
        for invalid in ("[]", "{}", "not JSON", json.dumps([{"title": "CPI"}]),
                        json.dumps([event(date="2026-10-14T08:30:00")])):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "calendar.ics"
                output.write_text("last valid calendar")
                with patch.object(sys, "argv", [str(SCRIPT), "--feed", "https://example.com/feed", "--output", str(output)]), \
                     patch.object(generator, "fetch_feed", return_value=invalid):
                    with self.assertRaises((ValueError, generator.ElementTree.ParseError)):
                        generator.main()
                self.assertEqual(output.read_text(), "last valid calendar")

    def test_unavailable_feed_is_an_error(self):
        error = HTTPError("https://example.com/feed", 404, "Not found", {}, None)
        with patch.object(generator, "urlopen", side_effect=error):
            with self.assertRaises(HTTPError):
                generator.fetch_feed("https://example.com/feed")


if __name__ == "__main__":
    unittest.main()
