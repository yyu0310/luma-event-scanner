# luma-event-scanner

[繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

**Free Luma calendar scanner.** It reads the full description of every upcoming event in the calendars you name, matches them against your keywords, ranks them by your priorities, and remembers what you have already reviewed, so tomorrow's list only shows what is new.

## Install with an AI coding agent

Copy this into Claude Code, Codex CLI, or any coding agent:

> Clone https://github.com/yyu0310/luma-event-scanner and read AGENTS.md, then help me set it up. Ask me which Luma calendars to watch and what I care about. A calendar's slug is the last part of its luma.com URL. Write a criteria.json for me from examples/criteria.example.json, then run the tool once.

Nothing in this project needs a password, token, or API key, so an agent can do every step for you.

## Why this exists

Big conference weeks fill Luma with hundreds of side events. Luma has no search across event descriptions, and the official API that could help is behind a paid plan. The events you care about are often only mentioned inside a description, not in the title.

| What you want | How this tool does it |
| --- | --- |
| Find events whose description mentions something | `--keywords` matches title, hosts, guests and description |
| See the most relevant events first | `criteria.json` ranks events by priorities you define |
| Check every day without re-reading old events | Events you were shown move to an excluded list the next day |
| Skip events you already decided on | `--exclude` and `--restore` |
| Keep notes on events | `--note` |

## Quick start

Requirements: Python 3.9 or newer. Standard library only, nothing to install.

```bash
git clone https://github.com/yyu0310/luma-event-scanner.git
cd luma-event-scanner

# First run: name the calendars to watch (luma.com/<slug>) and, optionally, a keyword regex
python3 luma_scan.py --calendars my-calendar,another-calendar --keywords "grant|hackathon" --timezone America/New_York

# Optional: rank events by your own priorities
mkdir -p ~/.luma-event-scanner
cp examples/criteria.example.json ~/.luma-event-scanner/criteria.json   # then edit it

# Every later run (the calendars and keywords are remembered)
python3 luma_scan.py
```

Then open `~/.luma-event-scanner/candidates.md`. The first run downloads every event once at about two requests per second, so a calendar with 300 events takes a few minutes. Later runs only download new events.

## Commands

| Command | What it does |
| --- | --- |
| `python3 luma_scan.py` | List the calendars, scan new events, write the reports |
| `--data-dir DIR` | Where the ledger and reports live (default `~/.luma-event-scanner`) |
| `--full` | Rescan every event, including ones already scanned |
| `--note KEY "text"` | Attach a note to an event, it survives reruns |
| `--exclude KEY [reason]` | Put an event on the excluded list by hand |
| `--restore KEY` | Take an event off the excluded list |
| `--peek` | Build today's candidates without marking them as seen |
| `--timezone NAME` | Display timezone, for example `Asia/Singapore` (default: your system timezone) |
| `--rescan-days N` | Rescan already scanned events after N days (default 3) |

`KEY` is an event's `api_id` or the last part of its URL (`luma.com/<KEY>`).

## How ranking works

`criteria.json` is a list ordered from most to least important. Each criterion has a regex and two lists of fields to look in:

```json
{"tag": "V", "name": "Venture investors", "regex": "\\bVCs?\\b|venture|investors?",
 "strong": ["title", "host_names"], "weak": ["hosts"]}
```

- Fields you can use: `title`, `hosts`, `host_names`, `guests`, `categories`, `calendar`, `description`. `hosts` matches host names and bios, `host_names` matches names only.
- A hit in a `strong` field is a strong match, a hit in a `weak` field is a weak match.
- Each event is listed under the most important criterion it matches. Inside a section, strong matches come first, then earlier start times.
- Keeping `description` out of the strong list is usually right for common words such as "investor" or "AI", which appear in almost every description.

Without a `criteria.json` the tool only does the keyword scan.

## The excluded list

Every event listed in `candidates.md` moves to `excluded.md` the next day, so a daily run only shows what is new. Running the tool twice on the same day changes nothing. Use `--peek` when you only want a preview, and `--restore` if you excluded something by mistake. Events that matched none of your criteria are never excluded, so if a host edits the description later and it starts to match, it appears.

## Where your data lives

By default in `~/.luma-event-scanner/`, outside of any repository:

| File | Content |
| --- | --- |
| `ledger.json` | The state: every event seen, when it was scanned, notes, exclusions |
| `scanned.md` | Human-readable view of the ledger |
| `candidates.md` | Events that match your criteria and were not reviewed yet, ranked |
| `excluded.md` | Events you have already seen or excluded by hand |
| `criteria.json` | Your criteria. You write this one |
| `cache/` | Raw event details, so changing criteria needs no re-download |

Use one `--data-dir` per topic if you follow several unrelated things.

## How it works

1. `GET api.lu.ma/url` turns a calendar slug into its id.
2. `GET api.lu.ma/calendar/get-items` lists the upcoming events, page by page.
3. `GET api.lu.ma/event/get` downloads each event's detail: description, hosts, guests and categories. Details are cached.
4. Criteria are scored from the cached details, so editing `criteria.json` needs no network.
5. Events you were shown get a `shown_date`. An event whose `shown_date` is before today is excluded.

All requests are read-only, unauthenticated GETs at about two per second.

## Limitations

- **Unofficial.** The three endpoints above are undocumented and can change without notice. This project is based entirely on academic research and has no commercial use. It reads public pages at a low request rate and isn't affiliated with Luma. Please follow Luma's terms of service.
- **Public data only.** It can't create events or manage guests, so it doesn't replace the official API.
- **Text matching only.** It doesn't understand meaning. A sponsor that appears only as a logo image is invisible.
- **Only the calendars you name.** Events that are not in those calendars are not seen.
- **Tested on macOS with Python 3.9 and 3.13.** Linux and Windows should work because only the standard library is used, but they're untested. Time zone names on Windows need the `tzdata` package.

## Development

```bash
python3 -m unittest discover tests -v
```

The tests are offline. They replace the network with a small in-memory Luma calendar and write to temporary directories.

## License

[PolyForm Noncommercial 1.0.0](LICENSE). Free for academic research and other noncommercial use.
