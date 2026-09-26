# AGENTS.md

This is a single-file Python tool, `luma_scan.py`, that uses only the standard library. It scans Luma calendars for events matching the user's criteria and remembers which events were already reviewed.

## Entry point

`main()` in `luma_scan.py`. It has two paths: the maintenance commands `--note`, `--exclude` and `--restore`, which only touch the ledger, and the normal run that lists calendars, scans events, and writes reports.

## Architecture

| Function | What it does |
|----------|-------------|
| `list_calendar()` | Resolves a calendar slug to an id (`/url`), then pages through `calendar/get-items` for upcoming events |
| `fetch()` | The only network call. Read-only GET, sleeps 0.5 s between calls. Tests replace it with a fake |
| `extract()` | Turns an event detail JSON into plain-text fields: title, hosts, host_names, guests, categories, calendar, description |
| `evaluate()` | Scores one event against `criteria.json`: 2 strong, 1 weak, 0 none per criterion |
| `rank_key()` / `first_tier()` | Sort key by criterion importance, then strong before weak, then start time. `first_tier()` says which criterion an event is filed under |
| `build_candidates()` | Events that match at least one criterion and are not excluded |
| `is_excluded()` | Excluded by hand, or `shown_date` earlier than today |
| `write_candidates()` / `write_excluded()` / `write_scanned_report()` | Regenerate the Markdown reports from the ledger and cache |
| `load_state()` / `save_state()` | Ledger I/O. A corrupt ledger stops the run and is left untouched. Saves are atomic |

