# Forex Factory NO TRADE Calendar

Apple Calendar subscription for the entire current UK calendar month, updated from Forex Factory.

## Subscribe

Use this public URL with **File > New Calendar Subscription** in Apple Calendar:

```text
https://raw.githubusercontent.com/hitz2kk/forex-factory-no-trade-calendar/main/no-trade.ics
```

Leave username and password blank. Keep the existing subscription if already added. On Mac, Control-click the calendar, choose **Get Info**, and set **Auto-refresh** to **Every 5 minutes** or the shortest available interval. Use **View > Refresh Calendars** to refresh now. Apple controls iPhone/iCloud refresh timing.

## Rules

- Include the whole current month, including elapsed dates, but no previous or next month.
- Switch to the new month on the first successful check after midnight on the 1st, UK time.
- USD, GBP and EUR high-impact/red-folder events only.
- Release time between 08:00 and 17:00 UK time, inclusive: the user's London/New York trading window, not a separate exchange-hours calculation.
- Automatically handle British Summer Time and GMT, including a clock change within the month.
- Block 15 minutes before and after each qualifying release. Separate simultaneous releases remain separate entries.
- Exclude tentative/all-day releases until a reliable time is published. Store them in the snapshot for later rechecking; never invent their time.

## Updates

The Codex heartbeat on the user's Mac checks the **full current month** every 15 minutes using the public Forex Factory browser page. The Mac must be awake, online and running Codex. It validates every displayed day, imports additions/removals/changed times or impact classifications, regenerates `no-trade.ics`, and pushes changes to this repository. Unchanged checks make no commit. See [BROWSER_UPDATES.md](BROWSER_UPDATES.md) for the repeatable process.

GitHub Actions runs after snapshot/code changes and on a five-minute schedule, validates the generator, and republishes the current-month calendar from the saved browser snapshot. GitHub cannot read the month page directly (403 when tested); the public JSON export contains only one week. Consequently GitHub alone cannot collect the month or detect source changes. If the Mac is unavailable or Forex Factory blocks the browser, the saved data does not receive new source updates. At a month rollover, an old-month snapshot produces an empty calendar until a valid new-month snapshot arrives, rather than retaining the wrong month.

These are periodic checks, not instant push updates. Codex, GitHub scheduling, public URL caching and Apple refresh timing can delay delivery. Failed or incomplete browser reads preserve the last valid snapshot. A parse failure does not overwrite the published file.

## Local Checks

Python standard library only; no browser package is needed in GitHub Actions.

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/browser_calendar.py /tmp/forex-month-rows.json
python3 -B scripts/generate_no_trade_calendar.py --output no-trade.ics
```

The importer expects the read-only `READ_MONTH` extraction from `scripts/browser_calendar.py`, plus `display_timezone: "Europe/London"` after verifying the website timezone. The generator uses `data/browser-calendar.json` by default. `--month YYYY-MM` supports reproducible tests. Explicit `--feed URL` remains available for compatible JSON/XML feeds, still filtered to the requested month.
