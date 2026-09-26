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

## Key design decisions

- **Data never lives in this repository.** The default data directory is `~/.luma-event-scanner/`. Don't add a data directory inside the repo, and don't add ignore rules for one.
- **Read-only and credential-free.** Only unauthenticated GETs to `api.lu.ma`. Never add login, cookies, tokens, or any write call.
- **Keyword scan uses only the event's own text**: title, hosts, guests and description. The raw JSON contains boilerplate such as the description Luma attaches to every event in a category. Matching it produced 241 false hits out of 284 events.
- **Details are cached in `cache/`** so editing criteria needs no network. An event without a cache file is scanned again on the next run.
- **Listed means seen.** Events written to `candidates.md` get a `shown_date`. From the next day on they count as excluded. Same-day reruns keep them. `--peek` skips the marking.
- **A failed detail download doesn't mark the event as scanned.** It's retried next run.
- **If no calendar can be read, the run stops** with a non-zero exit and leaves the ledger untouched.
- **Already scanned events are rescanned after 3 days** because hosts often add sponsors late.
- **Unofficial endpoints**: `/url`, `calendar/get-items`, `event/get` are undocumented and may change. When they break, the "no calendar could be read" stop is the expected symptom.

## Files written to the data directory

| File | Purpose |
|------|---------|
| `ledger.json` | State: config, calendars, events, notes, run history |
| `scanned.md`, `candidates.md`, `excluded.md` | Generated reports, never edit by hand |
| `criteria.json` | Written by the user, ordered from most to least important |
| `cache/evt_<id>.json` | Raw event details |

## Testing

```bash
python3 -m unittest discover tests -v
```

Offline. `luma_scan.fetch` is replaced by a fake calendar, every test uses a temporary directory. Run with `-W error::ResourceWarning` too. Add a test for every behavior change. Time zones in tests: pass `--timezone UTC` for stable output.

## Conventions

- Standard library only. Don't add dependencies.
- Python 3.9 compatible: no `match`, no `X | Y` type unions.
- Keep user-facing messages and comments in English.
