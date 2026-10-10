import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_upcoming_calendar import next_week_start, parse_rows


class UpcomingCalendarTests(unittest.TestCase):
    def rows(self, start):
        from datetime import timedelta

        return [{"day": f"{day.strftime('%a %b')} {day.day}", "empty": True}
                for day in (start + timedelta(days=n) for n in range(7))]

    def test_sunday_rollover(self):
        self.assertEqual(next_week_start(date(2026, 10, 10)), date(2026, 10, 11))
        self.assertEqual(next_week_start(date(2026, 10, 11)), date(2026, 10, 18))

    def test_display_dates_across_new_year_and_uk_dst(self):
        for start, expected in ((date(2026, 12, 27), "2027-01-01T13:30:00+00:00"),
                                (date(2026, 10, 11), "2026-10-16T13:30:00+01:00")):
            rows = self.rows(start)
            rows[5].update(empty=False, id="148337", title="CPI m/m", country="USD",
                           impact="High Impact Expected", time="1:30pm")
            self.assertEqual(parse_rows(rows, start)[0]["date"], expected)

    def test_partial_week_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_rows(self.rows(date(2026, 10, 11))[:3], date(2026, 10, 11))

    def test_unrendered_event_is_rejected(self):
        rows = self.rows(date(2026, 10, 11))
        rows[3]["empty"] = False
        with self.assertRaises(ValueError):
            parse_rows(rows, date(2026, 10, 11))
