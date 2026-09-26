# luma-event-scanner

[繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

**Free Luma calendar scanner.** It reads the full description of every upcoming event in the calendars you name, matches them against your keywords, ranks them by your priorities, and remembers what you have already reviewed, so tomorrow's list only shows what is new.

No paid API needed. Luma's official API requires Luma Plus, which [costs $59 a month billed annually](https://luma.com/pricing). This tool reads public event pages, so it costs nothing.

## Install with an AI coding agent

Copy this into Claude Code, Codex CLI, or any coding agent:

> Clone https://github.com/yyu0310/luma-event-scanner, read AGENTS.md, then help me set it up. Ask me which Luma calendars to watch and what I care about. A calendar's slug is the last part of its luma.com URL. Write a criteria.json for me from examples/criteria.example.json, then run the tool once.

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

