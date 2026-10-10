# Forex Factory NO TRADE Calendar

Automatically updated Apple Calendar subscription for high-impact Forex Factory news during the UK trading day.

## Subscription URL

Use this URL in Apple Calendar:

```text
https://raw.githubusercontent.com/hitz2kk/forex-factory-no-trade-calendar/main/no-trade.ics
```

## Rules

- Source: Forex Factory weekly JSON feed, with XML parsing retained as a fallback for compatible feed URLs.
- Currencies: USD, GBP, and EUR.
- Impact: high/red-folder only.
- Time filter: release time between 08:00 and 17:00 UK time after converting from the feed timestamp.
- Calendar block: 15 minutes before to 15 minutes after each release.

## Automation

GitHub Actions checks Forex Factory every five minutes (at minutes 2, 7, 12, and so on through 57 of each hour, UTC). It publishes `no-trade.ics` only when qualifying events or calendar settings change. Changed release times, impact levels, additions, and removals are reflected in the next successful update. Failed or invalid downloads leave the last valid calendar in place and fail the workflow. The workflow also runs after generator changes and can be run manually from the Actions tab.

This is periodic checking, not an instant push subscription. Updates must first appear in Forex Factory's public JSON export, then be picked up by GitHub Actions and Apple Calendar. GitHub can delay scheduled runs, so the five-minute schedule is not a guaranteed delivery deadline. The calendar requests a five-minute refresh from clients, but Apple controls the actual refresh timing.

The public export supplies the current week. A separate next-week export was unavailable when tested. Next week's website listings cannot currently be included in advance; they become available here when the public export rolls forward. An empty future calendar does not establish that there are no high-impact events.

In Apple Calendar on Mac, Control-click this calendar, choose **Get Info**, and set **Auto-refresh** to **Every 5 minutes** (or the shortest available interval). Choose **View > Refresh Calendars** to refresh now. iPhone/iCloud refresh timing is controlled by Apple. Keep your existing subscription URL; leave username and password blank.

References: [Apple Calendar refresh settings](https://support.apple.com/en-gb/guide/calendar/icl1024/mac), [GitHub scheduled workflow limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The generator has no third-party Python dependencies:

```bash
python scripts/generate_no_trade_calendar.py --output no-trade.ics
```
