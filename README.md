# Forex Factory NO TRADE Calendar

Daily Apple Calendar subscription for high-impact Forex Factory news during the UK trading day.

## Subscription URL

Use this URL in Apple Calendar:

```text
https://hitz2kk.github.io/forex-factory-no-trade-calendar/no-trade.ics
```

## Rules

- Source: Forex Factory weekly JSON feed, with XML parsing retained as a fallback for compatible feed URLs.
- Currencies: USD, GBP, and EUR.
- Impact: high/red-folder only.
- Time filter: release time between 08:00 and 17:00 UK time after converting from the feed timestamp.
- Calendar block: 15 minutes before to 15 minutes after each release.

## Automation

GitHub Actions refreshes `no-trade.ics` every day at 05:10 UTC and commits the updated file when the feed changes. The workflow can also be run manually from the Actions tab.

The generator has no third-party Python dependencies:

```bash
python scripts/generate_no_trade_calendar.py --output no-trade.ics
```
