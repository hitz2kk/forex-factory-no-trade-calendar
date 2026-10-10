"""Read next week's public Forex Factory calendar using a normal browser."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


CALENDAR_URL = "https://www.forexfactory.com/calendar?week=next"
LONDON = ZoneInfo("Europe/London")
IMPACTS = {
    "High Impact Expected": "High",
    "Med Impact Expected": "Medium",
    "Low Impact Expected": "Low",
    "Non-Economic": "Holiday",
}

READ_ROWS = """rows => {
    let day = "";
    let time = "";
    return rows.map(row => {
        const date = row.querySelector(".calendar__date");
        if (date) { day = date.textContent.trim(); time = ""; }
        const clock = row.querySelector(".calendar__time");
        if (clock && clock.textContent.trim()) time = clock.textContent.trim();
        return {
            id: row.getAttribute("data-event-id"), day, time,
            title: row.querySelector(".calendar__event-title")?.textContent.trim(),
            country: row.querySelector(".calendar__currency")?.textContent.trim(),
            impact: row.querySelector(".calendar__impact span[title]")?.getAttribute("title"),
            empty: row.classList.contains("calendar__row--no-event")
        };
    });
}"""


def next_week_start(today: date) -> date:
    return today + timedelta(days=7 - ((today.weekday() + 1) % 7))


def parse_rows(rows: list[dict], week_start: date) -> list[dict]:
    dates = {
        f"{day.strftime('%a %b')} {day.day}": day
        for day in (week_start + timedelta(days=offset) for offset in range(7))
    }
    seen_days = {row["day"] for row in rows}
    if not set(dates).issubset(seen_days):
        raise ValueError("Upcoming calendar did not contain all seven expected dates")

    events = []
    for row in rows:
        if row["day"] not in dates:
            raise ValueError("Upcoming calendar contains unexpected dates")
        if row.get("empty"):
            continue
        if not row.get("id") or not row.get("title") or row.get("impact") not in IMPACTS:
            raise ValueError("Upcoming calendar contains an incomplete event row")
        try:
            clock = datetime.strptime(row["time"].lower(), "%I:%M%p").time()
        except ValueError:
            # All-day and tentative releases have no reliable trading time.
            continue
        day = dates[row["day"]]
        release = datetime.combine(day, clock, tzinfo=LONDON)
        events.append({
            "title": row["title"],
            "country": row["country"],
            "impact": IMPACTS[row["impact"]],
            "date": release.isoformat(),
            "url": f"https://www.forexfactory.com/calendar?day={day.strftime('%b').lower()}{day.day}.{day.year}",
        })
    if not events:
        raise ValueError("Upcoming calendar contains no timed events")
    return events


def fetch_next_week() -> list[dict]:
    from playwright.sync_api import sync_playwright

    week_start = next_week_start(datetime.now(LONDON).date())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(timezone_id="Europe/London", locale="en-GB")
        page = context.new_page()
        page.set_default_timeout(30000)
        try:
            response = page.goto(CALENDAR_URL, wait_until="domcontentloaded")
            if response is None or response.status != 200:
                raise RuntimeError(f"Upcoming calendar access failed: {response.status if response else 'no response'}")
            page.locator(".calendar__date").first.wait_for()
            # Forex Factory renders each day's rows as it enters the viewport.
            for offset in range(7):
                day = week_start + timedelta(days=offset)
                label = f"{day.strftime('%a %b')} {day.day}"
                page.get_by_role("cell", name=label, exact=True).scroll_into_view_if_needed()
                page.wait_for_timeout(250)

            clock_text = page.locator('a[href="/timezone"]').first.inner_text().strip()
            shown = datetime.strptime(clock_text.lower(), "%I:%M%p")
            now = datetime.now(LONDON)
            difference = abs((shown.hour * 60 + shown.minute) - (now.hour * 60 + now.minute))
            if min(difference, 1440 - difference) > 3:
                raise ValueError("Forex Factory display timezone does not match UK time")

            rows = page.locator(".calendar__row").evaluate_all(READ_ROWS)
            events = parse_rows(rows, week_start)
            print(f"Read {len(events)} timed events for {week_start} through {week_start + timedelta(days=6)}")
            return events
        finally:
            context.close()
            browser.close()
