#!/usr/bin/env python3
"""Generate a no-trade iCalendar file from Forex Factory red-folder news."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zoneinfo import ZoneInfo


DEFAULT_FEEDS = (
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
)
DEFAULT_CURRENCIES = ("USD", "GBP", "EUR")
DEFAULT_OUTPUT = "no-trade.ics"
SOURCE_TIMEZONE = timezone.utc
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    country: str
    impact: str
    release_utc: datetime
    release_local: datetime
    url: str


def fetch_feed(url: str) -> str | None:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/xml,text/xml,*/*;q=0.8",
        },
    )
    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=30) as response:
                content_type = response.headers.get_content_charset() or "windows-1252"
                return response.read().decode(content_type, errors="replace")
        except HTTPError as error:
            if error.code == 404:
                print(f"Skipping unavailable feed: {url}", file=sys.stderr)
                return None
            if error.code == 429:
                curl_text = fetch_feed_with_curl(url)
                if curl_text is not None:
                    return curl_text
            if error.code == 429 and attempt < 3:
                sleep(10 * attempt)
                continue
            raise
        except URLError as error:
            if attempt < 3:
                sleep(5 * attempt)
                continue
            raise RuntimeError(f"Could not fetch {url}: {error}") from error
    return None


def fetch_feed_with_curl(url: str) -> str | None:
    curl = shutil.which("curl")
    if not curl:
        return None

    result = subprocess.run(
        [
            curl,
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "30",
            "-A",
            USER_AGENT,
            url,
        ],
        capture_output=True,
        check=False,
        text=True,
        encoding="windows-1252",
        errors="replace",
    )
    if result.returncode == 0:
        return result.stdout
    if "404" in result.stderr:
        print(f"Skipping unavailable feed: {url}", file=sys.stderr)
        return None
    return None


def node_text(node: ElementTree.Element, name: str) -> str:
    value = node.findtext(name, default="")
    return html.unescape(value.strip())


def parse_release_time(raw_date: str, raw_time: str) -> datetime | None:
    if not raw_time or raw_time.lower() in {"all day", "tentative"}:
        return None

    match = re.fullmatch(r"(\d{1,2}):(\d{2})(am|pm)", raw_time.strip().lower())
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = match.group(3)

    if hour == 12:
        hour = 0
    if meridiem == "pm":
        hour += 12

    release_date = datetime.strptime(raw_date, "%m-%d-%Y").date()
    return datetime.combine(release_date, dtime(hour, minute), tzinfo=SOURCE_TIMEZONE)


def parse_json_events(feed_text: str, local_tz: ZoneInfo) -> list[CalendarEvent]:
    data = json.loads(feed_text)
    events: list[CalendarEvent] = []

    for item in data:
        release = datetime.fromisoformat(str(item.get("date", "")))
        if release.tzinfo is None:
            release = release.replace(tzinfo=SOURCE_TIMEZONE)
        release_utc = release.astimezone(timezone.utc)
        country = str(item.get("country", "")).strip().upper()
        impact = str(item.get("impact", "")).strip()
        events.append(
            CalendarEvent(
                title=str(item.get("title", "")).strip(),
                country=country,
                impact=impact,
                release_utc=release_utc,
                release_local=release_utc.astimezone(local_tz),
                url=str(item.get("url", "")).strip(),
            )
        )

    return events


def parse_xml_events(xml_text: str, local_tz: ZoneInfo) -> list[CalendarEvent]:
    root = ElementTree.fromstring(xml_text)
    events: list[CalendarEvent] = []

    for item in root.findall("event"):
        release_utc = parse_release_time(node_text(item, "date"), node_text(item, "time"))
        if release_utc is None:
            continue

        country = node_text(item, "country").upper()
        impact = node_text(item, "impact")
        events.append(
            CalendarEvent(
                title=node_text(item, "title"),
                country=country,
                impact=impact,
                release_utc=release_utc,
                release_local=release_utc.astimezone(local_tz),
                url=node_text(item, "url"),
            )
        )

    return events


def parse_events(feed_text: str, local_tz: ZoneInfo) -> list[CalendarEvent]:
    stripped = feed_text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return parse_json_events(feed_text, local_tz)
    return parse_xml_events(feed_text, local_tz)


def filter_events(
    events: Iterable[CalendarEvent],
    currencies: set[str],
    start_time: dtime,
    end_time: dtime,
) -> list[CalendarEvent]:
    filtered = []
    for event in events:
        release_time = event.release_local.time()
        if event.country in currencies and event.impact.lower() == "high":
            if start_time <= release_time <= end_time:
                filtered.append(event)

    return sorted(filtered, key=lambda event: (event.release_utc, event.country, event.title))


def dedupe_events(events: Iterable[CalendarEvent]) -> list[CalendarEvent]:
    seen: set[tuple[str, datetime, str]] = set()
    deduped: list[CalendarEvent] = []
    for event in events:
        key = (event.url or event.title, event.release_utc, event.country)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\r\n", r"\n")
        .replace("\n", r"\n")
    )


def fold_line(line: str) -> list[str]:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]

    parts: list[str] = []
    current = ""
    current_bytes = 0
    limit = 75
    for char in line:
        char_bytes = len(char.encode("utf-8"))
        if current and current_bytes + char_bytes > limit:
            parts.append(current)
            current = " " + char
            current_bytes = 1 + char_bytes
            limit = 75
        else:
            current += char
            current_bytes += char_bytes
    if current:
        parts.append(current)
    return parts


def event_uid(event: CalendarEvent) -> str:
    raw = f"{event.url}|{event.release_utc.isoformat()}|{event.country}|{event.title}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{digest}@forex-factory-no-trade-calendar"


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(
    events: list[CalendarEvent],
    *,
    minutes_before: int,
    minutes_after: int,
    generated_at: datetime,
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//hitz2kk//Forex Factory No Trade Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Forex Factory NO TRADE",
        "X-WR-TIMEZONE:Europe/London",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    for event in events:
        start = event.release_utc - timedelta(minutes=minutes_before)
        end = event.release_utc + timedelta(minutes=minutes_after)
        local_release = event.release_local.strftime("%a %d %b %Y %H:%M %Z")
        summary = f"NO TRADE: {event.country} {event.title}"
        description = (
            f"Forex Factory red-folder event. Release time: {local_release}. "
            f"Currency: {event.country}. Impact: {event.impact}."
        )
        if event.url:
            description += f" Source: {event.url}"

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event_uid(event)}",
                f"DTSTAMP:{format_utc(generated_at)}",
                f"DTSTART:{format_utc(start)}",
                f"DTEND:{format_utc(end)}",
                f"SUMMARY:{escape_ics(summary)}",
                f"DESCRIPTION:{escape_ics(description)}",
                "TRANSP:OPAQUE",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")

    folded: list[str] = []
    for line in lines:
        folded.extend(fold_line(line))
    return "\r\n".join(folded) + "\r\n"


def parse_hhmm(value: str) -> dtime:
    return datetime.strptime(value, "%H:%M").time()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--timezone", default="Europe/London")
    parser.add_argument("--start-time", default="08:00")
    parser.add_argument("--end-time", default="17:00")
    parser.add_argument("--minutes-before", type=int, default=15)
    parser.add_argument("--minutes-after", type=int, default=15)
    parser.add_argument("--currency", action="append", dest="currencies")
    parser.add_argument("--feed", action="append", dest="feeds")
    args = parser.parse_args()

    local_tz = ZoneInfo(args.timezone)
    currencies = {currency.upper() for currency in (args.currencies or DEFAULT_CURRENCIES)}
    start_time = parse_hhmm(args.start_time)
    end_time = parse_hhmm(args.end_time)
    feeds = args.feeds or list(DEFAULT_FEEDS)

    all_events: list[CalendarEvent] = []
    for feed_url in feeds:
        xml_text = fetch_feed(feed_url)
        if xml_text:
            all_events.extend(parse_events(xml_text, local_tz))

    selected = dedupe_events(filter_events(all_events, currencies, start_time, end_time))
    output = Path(args.output)
    output.write_text(
        build_ics(
            selected,
            minutes_before=args.minutes_before,
            minutes_after=args.minutes_after,
            generated_at=datetime.now(timezone.utc),
        ),
        encoding="utf-8",
    )

    print(f"Wrote {len(selected)} events to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
