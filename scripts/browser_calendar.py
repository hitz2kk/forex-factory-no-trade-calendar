"""Validate month data read from the visible Forex Factory browser calendar."""

import argparse
import calendar
import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
IMPACTS = {"High Impact Expected": "High", "Med Impact Expected": "Medium",
           "Low Impact Expected": "Low", "Non-Economic": "Holiday"}

# Run this read-only extractor in the Codex browser after rendering every day.
READ_MONTH = """rows => {
    let day = "", time = "";
    const days = new Set(), renderedDays = new Set(), events = [], incomplete = [];
    let rendered = 0;
    for (const row of rows) {
        const label = row.querySelector('.calendar__date')?.textContent.trim();
        if (label && /^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) /.test(label)) {
            day = label; time = ""; days.add(day);
        }
        if (row.classList.contains('calendar__row--no-event')) { renderedDays.add(day); continue; }
        if (row.classList.contains('calendar__row--day-breaker')) continue;
        const id = row.getAttribute('data-event-id');
        if (!id) continue;
        rendered++;
        const clock = row.querySelector('.calendar__time')?.textContent.trim();
        if (clock) time = clock;
        const title = row.querySelector('.calendar__event-title')?.textContent.trim();
        const country = row.querySelector('.calendar__currency')?.textContent.trim();
        const impact = row.querySelector('.calendar__impact span[title]')?.getAttribute('title');
        if (!day || !title || !country || !impact) incomplete.push(id);
        else renderedDays.add(day);
        if (impact === 'High Impact Expected' && ['USD','GBP','EUR'].includes(country))
            events.push({id, day, time, title, country, impact});
    }
    return {covered_days: [...days], rendered_days: [...renderedDays], rendered_event_count: rendered,
            incomplete_event_ids: incomplete, rows: events};
}"""


def month_days(month: str) -> dict[str, date]:
    first = date.fromisoformat(month + "-01")
    return {f"{day.strftime('%a %b')} {day.day}": day
            for day in (first.replace(day=n) for n in range(1, calendar.monthrange(first.year, first.month)[1] + 1))}


def validate_snapshot(snapshot: dict) -> None:
    dates = month_days(snapshot["month"])
    if snapshot.get("timezone") != "Europe/London":
        raise ValueError("Browser calendar must display Europe/London")
    if set(snapshot.get("covered_days", [])) != set(dates):
        raise ValueError("Browser calendar did not contain the entire month")
    if not isinstance(snapshot.get("events"), list):
        raise ValueError("Missing browser events list")
    if datetime.fromisoformat(snapshot["updated_at"]).tzinfo is None:
        raise ValueError("Snapshot timestamp must include a timezone")
    for event in snapshot["events"]:
        release = datetime.fromisoformat(event["date"])
        if release.tzinfo is None or release.astimezone(LONDON).strftime("%Y-%m") != snapshot["month"]:
            raise ValueError("Browser event is outside its month or lacks a timezone")
        if (not event.get("title") or not event.get("id") or
                event.get("country") not in {"USD", "GBP", "EUR"} or event.get("impact") != "High"):
            raise ValueError("Incomplete or unexpected browser event")


def make_snapshot(raw: dict, month: str) -> dict:
    dates = month_days(month)
    if set(raw["covered_days"]) != set(dates) or set(raw.get("rendered_days", [])) != set(dates):
        raise ValueError("Partial month; keeping the last valid calendar")
    if raw.get("display_timezone") != "Europe/London":
        raise ValueError("Verify the browser display timezone before importing")
    if raw.get("incomplete_event_ids") or raw.get("rendered_event_count", 0) < 1:
        raise ValueError("Unrendered or incomplete month; keeping the last valid calendar")
    events, untimed = [], []
    for row in raw["rows"]:
        if (row.get("day") not in dates or not row.get("id") or not row.get("title") or
                row.get("country") not in {"USD", "GBP", "EUR"} or row.get("impact") != "High Impact Expected"):
            raise ValueError("Incomplete or unexpected high-impact browser row")
        if row["time"].lower() in {"tentative", "all day", ""}:
            untimed.append({"id": row["id"], "day": row["day"], "title": row["title"], "country": row["country"]})
            continue
        clock = datetime.strptime(row["time"].lower(), "%I:%M%p").time()
        day = dates[row["day"]]
        events.append({"id": row["id"], "title": row["title"], "country": row["country"],
                       "impact": "High", "date": datetime.combine(day, clock, tzinfo=LONDON).isoformat(),
                       "url": f"https://www.forexfactory.com/calendar?day={day.strftime('%b').lower()}{day.day}.{day.year}"})
    snapshot = {"month": month, "timezone": "Europe/London",
                "source": f"https://www.forexfactory.com/calendar?month={next(iter(dates.values())).strftime('%b').lower()}.{next(iter(dates.values())).year}",
                "covered_days": list(dates), "updated_at": datetime.now(timezone.utc).isoformat(),
                "events": sorted(events, key=lambda e: (e["date"], e["country"], e["title"], e["id"])),
                "untimed_events": sorted(untimed, key=lambda e: e["id"])}
    validate_snapshot(snapshot)
    return snapshot


def write_snapshot(path: Path, snapshot: dict) -> bool:
    validate_snapshot(snapshot)
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if {k: v for k, v in previous.items() if k != "updated_at"} == {k: v for k, v in snapshot.items() if k != "updated_at"}:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--month", default=datetime.now(LONDON).strftime("%Y-%m"))
    parser.add_argument("--output", type=Path, default=Path("data/browser-calendar.json"))
    args = parser.parse_args()
    snapshot = make_snapshot(json.loads(args.input.read_text(encoding="utf-8")), args.month)
    changed = write_snapshot(args.output, snapshot)
    print(f"{'Updated' if changed else 'Unchanged'}: {args.month}, {len(snapshot['events'])} timed high-impact events")


if __name__ == "__main__":
    main()
