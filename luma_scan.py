#!/usr/bin/env python3
"""luma-event-scanner: scan Luma calendars for events that match your criteria.

It lists the upcoming events of the Luma calendars you name, reads each event's
full description, ranks the events by your priorities, and remembers which ones
you have already reviewed so that tomorrow's list only shows what is new.

First run (calendars are the slugs in luma.com/<slug>):
  python3 luma_scan.py --calendars my-calendar,another-calendar --keywords "grant|hackathon"
Every later run:
  python3 luma_scan.py
Other commands:
  --data-dir DIR                where the ledger and reports live (default ~/.luma-event-scanner)
  --full                        rescan every event
  --note KEY TEXT               attach a note to an event (survives reruns)
  --exclude KEY [REASON...]     put an event on the excluded list by hand
  --restore KEY                 take an event off the excluded list
  --peek                        build today's candidates without marking them as seen
  --timezone NAME               display timezone, e.g. Asia/Singapore (default: system timezone)
  --today YYYY-MM-DD            pretend today is this date (for testing)

KEY is an event's api_id or the last part of its URL (luma.com/<KEY>).

Optional criteria file DATA_DIR/criteria.json, ordered from most to least important:
  [{"tag": "A", "name": "Display name", "regex": "foo|bar",
    "strong": ["title", "host_names"], "weak": ["description"]}]
Fields you can match: title, hosts (name + bio), host_names (name only), guests,
categories, calendar, description. A hit in a "strong" field is a strong match, a hit
in a "weak" field is a weak match. Without this file only keyword scanning runs.

Files written to the data directory:
  ledger.json      the state: every event seen, when it was scanned, notes, exclusions
  scanned.md       human-readable view of the ledger
  candidates.md    events that match your criteria and were not reviewed yet, ranked
  excluded.md      events you have already seen or excluded by hand
  cache/           raw event details (changing criteria does not need a re-download)

Standard library only. Read-only requests to api.lu.ma, no credentials.
Unofficial: these endpoints are undocumented and may change without notice.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

SLEEP = 0.5  # seconds between requests, about 2 requests per second
CHECKPOINT_EVERY = 25
DEFAULT_RESCAN_DAYS = 3  # hosts often add sponsors late, so already scanned events are rescanned
DEFAULT_DATA_DIR = os.path.join("~", ".luma-event-scanner")
UA = {"User-Agent": "luma-event-scanner/0.1 (+https://github.com/yyu0310/luma-event-scanner)"}
FIELDS = ("title", "hosts", "host_names", "guests", "categories", "calendar", "description")

LEDGER = "ledger.json"
SCANNED_REPORT = "scanned.md"
CANDIDATES = "candidates.md"
EXCLUDED = "excluded.md"
CRITERIA = "criteria.json"

DISPLAY_TZ = None  # set in main(); None means the system timezone
TZ_LABEL = "local time"


def log(msg):
    print(msg, flush=True)


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def fetch(url):
    log(f"    GET {url}")
    time.sleep(SLEEP)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def set_timezone(name):
    """Choose the timezone used to display event times."""
    global DISPLAY_TZ, TZ_LABEL
    if name:
        if ZoneInfo is None:
            sys.exit("--timezone needs Python 3.9 or newer")
        try:
            DISPLAY_TZ = ZoneInfo(name)
        except Exception:
            sys.exit(f"Unknown timezone {name!r}. Use an IANA name such as Asia/Singapore or America/New_York")
        TZ_LABEL = name
    else:
        DISPLAY_TZ = datetime.now().astimezone().tzinfo
        TZ_LABEL = "local time"


def fmt_time(start_at):
    try:
        dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    except ValueError:
        return start_at[:16] or "?"
    return dt.astimezone(DISPLAY_TZ).strftime("%m/%d %H:%M")


def strings(o):
    """Yield every string value in a JSON tree (description text, host names, sponsors)."""
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k != "type":  # descriptions are ProseMirror trees; "type" holds node names like paragraph/bold
                yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def find_key(o, key):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield v
            else:
                yield from find_key(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from find_key(v, key)


def find_cal_id(o):
    if isinstance(o, dict):
        v = o.get("api_id")
        if isinstance(v, str) and v.startswith("cal-"):
            return v
        for x in o.values():
            r = find_cal_id(x)
            if r:
                return r
    elif isinstance(o, list):
        for x in o:
            r = find_cal_id(x)
            if r:
                return r


# ---------- criteria scoring ----------

def host_names(d):
    return [h.get("name") for h in d.get("hosts") or [] if isinstance(h, dict) and h.get("name")]


def extract(d):
    """Pull the plain-text fields used for scoring out of an event detail JSON."""
    ev = d.get("event") or {}

    def people(lst):
        return " ".join(f"{x.get('name') or ''} {x.get('bio_short') or ''}" for x in lst or [] if isinstance(x, dict))

    return {
        "title": ev.get("name") or "",
        "hosts": people(d.get("hosts")),
        "host_names": " | ".join(host_names(d)),
        "guests": people(d.get("featured_guests")),
        "categories": " ".join((c.get("name") or "") for c in d.get("categories") or [] if isinstance(c, dict)),
        "calendar": (d.get("calendar") or {}).get("name") or "",
        "description": " ".join(s for v in find_key(d, "description_mirror") for s in strings(v)),
    }


def evaluate(fields, criteria):
    """Return one (level, matched text) per criterion: 2 strong, 1 weak, 0 no match."""
    out = []
    for c in criteria:
        rx = re.compile(c["regex"], re.I)
        level, term = 0, ""
        for lvl, keys in ((2, c.get("strong", [])), (1, c.get("weak", []))):
            for k in keys:
                m = rx.search(fields.get(k, ""))
                if m:
                    level, term = lvl, m.group(0)
                    break
            if level:
                break
        out.append((level, term))
    return out


def tags_text(res, criteria):
    return " ".join(f"{c['tag']}{'*' if lv == 2 else '.'}{term.lower()[:24]}"
                    for c, (lv, term) in zip(criteria, res) if lv)


def rank_key(res, start_at):
    return tuple(-lv for lv, _ in res) + (start_at,)


def first_tier(res):
    """Index (from 0) of the most important criterion this event matched."""
    return next(i for i, (lv, _) in enumerate(res) if lv)


def load_criteria(dd):
    p = os.path.join(dd, CRITERIA)
    if not os.path.exists(p):
        return None
    try:
        crit = read_json(p)
        for c in crit:
            re.compile(c["regex"])
            for k in c.get("strong", []) + c.get("weak", []):
                if k not in FIELDS:
                    sys.exit(f"{CRITERIA}: unknown field {k!r}. Valid fields: {', '.join(FIELDS)}")
        return crit
    except (json.JSONDecodeError, KeyError, re.error) as ex:
        sys.exit(f"{CRITERIA} is malformed ({ex!r}). Fix it and run again")


def cache_path(dd, eid):
    return os.path.join(dd, "cache", f"evt_{eid}.json")


def load_cached(dd, eid):
    p = cache_path(dd, eid)
    if not os.path.exists(p):
        return None
    try:
        return read_json(p)
    except json.JSONDecodeError:
        return None


# ---------- ledger ----------

def load_state(path):
    if not os.path.exists(path):
        return {"config": {}, "calendars": {}, "events": {}, "notes": {}, "runs": []}
    try:
        return read_json(path)
    except json.JSONDecodeError as ex:
        sys.exit(f"{path} is corrupted ({ex}). Stopping so the ledger is not overwritten; fix or restore it by hand")


def save_state(state, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def list_calendar(slug, state):
    """Return {api_id: (name, start_at, url_slug)} for a calendar, or None if it cannot be found."""
    cal = state["calendars"].get(slug)
    if not cal:
        u = fetch("https://api.lu.ma/url?url=" + urllib.parse.quote(slug))
        cal = find_cal_id(u.get("data", u))
        if not cal:
            log(f"  [{slug}] no calendar api_id found, skipping")
            return None
        state["calendars"][slug] = cal
    out, cursor, page = {}, None, 0
    while True:
        q = {"calendar_api_id": cal, "period": "future", "pagination_limit": "50"}
        if cursor:
            q["pagination_cursor"] = cursor
        d = fetch("https://api.lu.ma/calendar/get-items?" + urllib.parse.urlencode(q))
        for e in d.get("entries", []):
            ev = e.get("event") or {}
            if ev.get("api_id"):
                out[ev["api_id"]] = (ev.get("name") or "", ev.get("start_at") or "", ev.get("url") or "")
        page += 1
        if not d.get("has_more") or not d.get("next_cursor"):
            break
        cursor = d["next_cursor"]
        if page >= 100:
            log(f"  [{slug}] hit the 100 page limit, the list may be incomplete")
            break
    log(f"  [{slug}] cal={cal} pages={page} events={len(out)}")
    return out


# ---------- reports ----------

def esc(s):
    return re.sub(r"\s+", " ", str(s)).replace("|", "/")


def link(ev):
    return f"[{esc(ev['name'])}](https://luma.com/{ev['url']})"


def write_scanned_report(state, run_at, path):
    cfg, evs, notes = state["config"], state["events"], state["notes"]
    rows = sorted(evs.items(), key=lambda kv: kv[1].get("start_at", ""))

    def line(eid, ev, with_snip):
        cols = [fmt_time(ev["start_at"]), link(ev), "/".join(ev.get("calendars", [])), esc(notes.get(eid, ""))]
        if with_snip:
            cols.insert(2, esc(" ... ".join(ev.get("snippets", [])))[:200])
        return "| " + " | ".join(cols) + " |"

    hits = [(k, v) for k, v in rows if v.get("hit")]
    new = [(k, v) for k, v in rows if v.get("first_seen") == run_at]
    unscanned = [(k, v) for k, v in rows if not v.get("last_scanned")]
    L = [
        "# Luma scan ledger (generated, do not edit by hand; use luma_scan.py --note for notes)",
        "",
        f"Updated: {run_at} | {len(evs)} events in the ledger | {len(hits)} keyword hits | "
        f"{len(new)} new this run | {len(unscanned)} not scanned yet",
        f"Keywords: `{cfg.get('keywords') or '(none)'}` | Calendars: {', '.join(cfg.get('calendars', []))} | Times in {TZ_LABEL}",
    ]
    if cfg.get("keywords"):
        L += ["", "## Keyword hits", "", "| Time | Event | Matched text | Calendar | Note |", "|---|---|---|---|---|"]
        L += [line(k, v, True) for k, v in hits] or ["| (none) | | | | |"]
    L += ["", "## New this run (first time seen)", "", "| Time | Event | Calendar | Note |", "|---|---|---|---|"]
    L += [line(k, v, False) for k, v in new] or ["| (none) | | | |"]
    if unscanned:
        L += ["", "## Not scanned (detail download failed, retried next run)", "",
              "| Time | Event | Calendar | Note |", "|---|---|---|---|"]
        L += [line(k, v, False) for k, v in unscanned]
    L += ["", "## All scanned", "", "| Time | Event | Calendar | Note |", "|---|---|---|---|"]
    L += [line(k, v, False) for k, v in rows if v.get("last_scanned")]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def is_excluded(ev, today):
    return bool(ev.get("excluded")) or bool(ev.get("shown_date") and ev["shown_date"] < today)


def write_excluded(state, criteria, dd, today):
    """Excluded list: excluded by hand, or already listed in a candidates file before today."""
    rows = []
    for eid, ev in state["events"].items():
        if not is_excluded(ev, today):
            continue
        d = load_cached(dd, eid)
        tags = tags_text(evaluate(extract(d), criteria), criteria) if (d and criteria) else ""
        reason = ev.get("excluded_reason") if ev.get("excluded") else f"listed in the candidates of {ev['shown_date']}"
        rows.append((ev.get("start_at", ""), ev, reason, tags, state["notes"].get(eid, "")))
    rows.sort(key=lambda r: r[0])
    L = ["# Excluded events (generated, do not edit by hand)", "",
         f"{len(rows)} events. They no longer appear in {CANDIDATES}. "
         "Bring one back with `luma_scan.py --restore <slug or api_id>`.", "",
         "| Time | Event | Reason | Matched then | Note |", "|---|---|---|---|---|"]
    L += [f"| {fmt_time(ev.get('start_at', ''))} | {link(ev)} | {esc(reason)} | {esc(tags)} | {esc(note)} |"
          for _, ev, reason, tags, note in rows] or ["| (none) | | | | |"]
    with open(os.path.join(dd, EXCLUDED), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return len(rows)


def build_candidates(state, criteria, dd, listed, today):
    """Return (ranked candidates, number of events without a cached detail)."""
    items, unanalysed = [], 0
    for eid, ev in listed.items():
        if is_excluded(ev, today):
            continue
        d = load_cached(dd, eid)
        if d is None:
            unanalysed += 1
            continue
        res = evaluate(extract(d), criteria)
        if any(lv for lv, _ in res):
            items.append((eid, ev, res, host_names(d)))
    items.sort(key=lambda it: rank_key(it[2], it[1].get("start_at", "")))
    return items, unanalysed


def write_candidates(state, criteria, dd, items, unanalysed, today, peek):
    notes = state["notes"]
    L = [f"# Candidates ({today})", "",
         "Criteria in order of importance. Each event sits under the most important criterion it matches; "
         "inside a section strong matches come first, then earlier start times:", ""]
    L += [f"{i}. **{c['tag']}** {c['name']}" for i, c in enumerate(criteria, 1)]
    L += ["", f"{len(items)} events | {unanalysed} without cached details yet | Times in {TZ_LABEL} | "
              "Match column: `*` strong match (title, host, guest ...), `.` weak match"]
    L += ["**Preview mode (--peek): these events will not be excluded.**" if peek
          else f"Events listed here move to [{EXCLUDED}]({EXCLUDED}) from tomorrow on."]
    for i, c in enumerate(criteria):
        tier = [it for it in items if first_tier(it[2]) == i]
        L += ["", f"## Criterion {i + 1}: {c['name']} ({len(tier)} events)", ""]
        if not tier:
            L.append("(none)")
            continue
        L += ["| # | Time | Event | Match | Hosts | Note |", "|---|---|---|---|---|---|"]
        for n, (eid, ev, res, hosts) in enumerate(tier, 1):
            L.append(f"| {n} | {fmt_time(ev['start_at'])} | {link(ev)} | {esc(tags_text(res, criteria))} | "
                     f"{esc(', '.join(hosts[:3]))} | {esc(notes.get(eid, ''))} |")
    with open(os.path.join(dd, CANDIDATES), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ---------- commands ----------

def resolve(state, key):
    key = key.rstrip("/").split("/")[-1]
    for eid, ev in state["events"].items():
        if key in (eid, ev.get("url")):
            return eid, ev
    return None, None


def main():
    ap = argparse.ArgumentParser(description="Scan Luma calendars for events that match your criteria")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help=f"where to keep the ledger and reports (default {DEFAULT_DATA_DIR})")
    ap.add_argument("--calendars", help="calendar slugs, comma separated, e.g. my-calendar,another (luma.com/<slug>)")
    ap.add_argument("--keywords", help="optional case-insensitive regex matched against an event's title, hosts, guests and description")
    ap.add_argument("--rescan-days", type=int, help=f"rescan already scanned events after this many days (default {DEFAULT_RESCAN_DAYS})")
    ap.add_argument("--timezone", help="display timezone, IANA name such as Asia/Singapore (default: system timezone)")
    ap.add_argument("--full", action="store_true", help="rescan every event")
    ap.add_argument("--note", nargs=2, metavar=("KEY", "TEXT"), help="attach a note to an event")
    ap.add_argument("--exclude", nargs="+", metavar="KEY_AND_REASON", help="exclude an event: KEY [reason...]")
    ap.add_argument("--restore", metavar="KEY", help="take an event off the excluded list")
    ap.add_argument("--peek", action="store_true", help="build candidates without marking them as seen")
    ap.add_argument("--today", help="pretend today is this date, YYYY-MM-DD (for testing)")
    args = ap.parse_args()

    dd = os.path.expanduser(args.data_dir)
    os.makedirs(dd, exist_ok=True)
    state_path = os.path.join(dd, LEDGER)
    report_path = os.path.join(dd, SCANNED_REPORT)
    state = load_state(state_path)
    today = args.today or datetime.now().astimezone().date().isoformat()
    criteria = load_criteria(dd)

    if args.timezone:
        state["config"]["timezone"] = args.timezone
    set_timezone(state["config"].get("timezone"))

    if args.note or args.exclude or args.restore:
        key = args.note[0] if args.note else (args.exclude[0] if args.exclude else args.restore)
        eid, ev = resolve(state, key)
        if not eid:
            log(f"{key} is not in the ledger (use an api_id or the last part of the event URL)")
            sys.exit(1)
        if args.note:
            state["notes"][eid] = args.note[1]
            log(f"Note saved: {ev['name']} -> {args.note[1]}")
        elif args.exclude:
            ev["excluded"] = True
            ev["excluded_reason"] = " ".join(args.exclude[1:]) or "excluded by hand"
            log(f"Excluded: {ev['name']} ({ev['excluded_reason']})")
        else:
            for k in ("excluded", "excluded_reason", "shown_date"):
                ev.pop(k, None)
            log(f"Restored: {ev['name']} (it will show up in the candidates again)")
        save_state(state, state_path)
        write_scanned_report(state, state["runs"][-1]["at"] if state["runs"] else now(), report_path)
        n = write_excluded(state, criteria, dd, today)
        log(f"The excluded list now has {n} events")
        return 0

    # Command line beats the settings saved in the ledger; without either, stop.
    cfg = state["config"]
    if args.calendars:
        cfg["calendars"] = [s.strip() for s in args.calendars.split(",") if s.strip()]
    if args.keywords:
        cfg["keywords"] = args.keywords
    if args.rescan_days is not None:
        cfg["rescan_days"] = args.rescan_days
    cfg.setdefault("rescan_days", DEFAULT_RESCAN_DAYS)
    if not cfg.get("calendars"):
        sys.exit("First run needs --calendars (they are saved in the ledger for later runs)")
    pattern = None
    if cfg.get("keywords"):
        try:
            pattern = re.compile(r".{0,80}(?:%s).{0,80}" % cfg["keywords"], re.I | re.S)
        except re.error as ex:
            sys.exit(f"--keywords is not a valid regex: {ex}")

    run_at = now()
    log(f"=== Run {run_at} (today={today}) ledger {state_path} holds {len(state['events'])} events ===")
    log(f"Settings: calendars={cfg['calendars']} keywords={cfg.get('keywords')!r} "
        f"rescan after {cfg['rescan_days']} days | criteria file: "
        f"{str(len(criteria)) + ' criteria' if criteria else 'none (keyword scan only)'}")

    listed, ok_cals = {}, 0
    for slug in cfg["calendars"]:
        try:
            got = list_calendar(slug, state)
        except Exception as ex:
            log(f"  [{slug}] could not list the calendar: {ex!r}. Skipping it this run (ledger untouched)")
            continue
        if got is None:
            continue
        ok_cals += 1
        for eid, (name, start, url) in got.items():
            ev = state["events"].setdefault(eid, {"first_seen": run_at, "calendars": []})
            ev.update(name=name, start_at=start, url=url)
            if slug not in ev["calendars"]:
                ev["calendars"].append(slug)
            listed[eid] = ev

    if ok_cals == 0:
        sys.exit("None of the calendars could be read (network, mistyped slug, or Luma changed). Ledger left untouched")

    cutoff = datetime.now().astimezone() - timedelta(days=cfg["rescan_days"])
    todo, no_cache = [], 0
    for eid, ev in listed.items():
        last = ev.get("last_scanned")
        missing = not os.path.exists(cache_path(dd, eid))
        no_cache += missing
        if args.full or missing or not last or datetime.fromisoformat(last) < cutoff:
            todo.append(eid)
    todo.sort(key=lambda e: listed[e]["start_at"])
    n_new = sum(1 for e in listed.values() if e["first_seen"] == run_at)
    log(f"{len(listed)} events listed | {n_new} new | {no_cache} without cached details | "
        f"{len(todo)} to scan (--full={args.full})")

    new_hits, fails = [], []
    os.makedirs(os.path.join(dd, "cache"), exist_ok=True)
    for i, eid in enumerate(todo, 1):
        ev = listed[eid]
        try:
            d = fetch("https://api.lu.ma/event/get?event_api_id=" + eid)
            with open(cache_path(dd, eid), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            snips = []
            if pattern:
                # Only the event's own text. The raw JSON also carries boilerplate such as the
                # description Luma attaches to every event in a category, which would match anything.
                f = extract(d)
                text = " ".join(f[k] for k in ("title", "hosts", "guests", "description"))
                snips = [m.group(0).strip() for m in pattern.finditer(text)][:3]
            ev["snippets"] = snips
            ev["hit"] = bool(snips)
            ev["last_scanned"] = now()
            if snips and not ev.get("hit_first_seen"):
                ev["hit_first_seen"] = run_at
                new_hits.append(eid)
            log(f"  [{i}/{len(todo)}] {fmt_time(ev['start_at'])} {ev['name'][:50]} -> {'hit' if snips else 'no hit'}")
        except Exception as ex:
            fails.append(eid)
            log(f"  [{i}/{len(todo)}] {ev['name'][:50]} detail download failed: {ex!r} (not marked as scanned, retried next run)")
        if i % CHECKPOINT_EVERY == 0:
            save_state(state, state_path)

    digest = None
    if criteria:
        items, unanalysed = build_candidates(state, criteria, dd, listed, today)
        write_candidates(state, criteria, dd, items, unanalysed, today, args.peek)
        if not args.peek:
            for _, ev, _, _ in items:  # listed today, excluded from tomorrow on
                ev.setdefault("shown_date", today)
        digest = (items, unanalysed)

    state["runs"].append({"at": run_at, "listed": len(listed), "new": n_new, "scanned": len(todo) - len(fails),
                          "new_hits": len(new_hits), "fail": len(fails)})
    save_state(state, state_path)
    write_scanned_report(state, run_at, report_path)
    n_excl = write_excluded(state, criteria, dd, today)

    log("=== Summary ===")
    log(f"Listed {len(listed)} | new {n_new} | scanned {len(todo) - len(fails)} | failed {len(fails)} | new keyword hits {len(new_hits)}")
    for eid in new_hits:
        ev = listed[eid]
        log(f"  New keyword hit: {fmt_time(ev['start_at'])} {ev['name']} https://luma.com/{ev['url']}")
    if digest:
        items, unanalysed = digest
        per_tier = [sum(1 for it in items if first_tier(it[2]) == i) for i in range(len(criteria))]
        log(f"Candidates: {len(items)} ({'preview, nothing excluded' if args.peek else 'excluded from tomorrow on'}) | "
            + " | ".join(f"criterion {i + 1} {c['tag']}: {n}" for i, (c, n) in enumerate(zip(criteria, per_tier)))
            + f" | without details {unanalysed} | excluded list {n_excl}")
        for eid, ev, res, hosts in items[:15]:
            log(f"  {fmt_time(ev['start_at'])} {ev['name'][:60]} | {tags_text(res, criteria)}")
        log(f"Candidates file: {os.path.join(dd, CANDIDATES)}")
    log(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
