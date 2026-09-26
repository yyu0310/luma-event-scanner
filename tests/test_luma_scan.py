"""Offline tests for luma_scan.py. Run from the repository root: python3 -m unittest discover tests -v

Nothing here touches the network: luma_scan.fetch is replaced by a fake that serves
a tiny in-memory Luma calendar, and every test writes into its own temporary directory.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import luma_scan as L  # noqa: E402


def doc(*texts):
    """A description shaped like Luma's ProseMirror tree."""
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": t, "marks": [{"type": "bold"}]}]} for t in texts]}


CAL_EVENTS = [
    {"api_id": "evt-1", "name": "Alpha Ventures Night", "start_at": "2026-10-07T07:00:00.000Z", "url": "alpha"},
    {"api_id": "evt-2", "name": "AI Builders Meetup", "start_at": "2026-10-06T07:00:00.000Z", "url": "ai-meetup"},
    {"api_id": "evt-3", "name": "Community Dinner", "start_at": "2026-10-08T07:00:00.000Z", "url": "dinner"},
    {"api_id": "evt-4", "name": "Yoga in the Park", "start_at": "2026-10-09T07:00:00.000Z", "url": "yoga"},
]

DETAILS = {
    "evt-1": {"event": {"name": "Alpha Ventures Night", "description_mirror": doc("Meet other founders")},
              "hosts": [{"name": "Alpha Ventures", "bio_short": "early stage fund"}],
              "categories": [{"name": "Crypto"}], "calendar": {"name": "Demo"}},
    "evt-2": {"event": {"name": "AI Builders Meetup", "description_mirror": doc("Demos and pizza")},
              "hosts": [{"name": "Dana", "bio_short": None}],
              "categories": [{"name": "AI"}], "calendar": {"name": "Demo"}},
    "evt-3": {"event": {"name": "Community Dinner", "description_mirror": doc("Investors are welcome")},
              "hosts": [{"name": "Bob", "bio_short": "angel investor"}],
              "categories": [], "calendar": {"name": "Demo"}},
    "evt-4": {"event": {"name": "Yoga in the Park", "description_mirror": doc("Bring a mat")},
              "hosts": [{"name": "Sam", "bio_short": None}], "categories": [], "calendar": {"name": "Demo"}},
}

CRITERIA = [
    {"tag": "V", "name": "Venture investors", "regex": r"\bventures?\b|\binvestors?\b",
     "strong": ["title", "host_names"], "weak": ["hosts"]},
    {"tag": "A", "name": "AI related", "regex": r"\bAI\b", "strong": ["title", "categories"], "weak": []},
]


def make_fetch(events=None, details=None, fail=False):
    events = CAL_EVENTS if events is None else events
    details = DETAILS if details is None else details

    def fake(url):
        if fail:
            raise OSError("network down")
        if "/url?" in url:
            return {"kind": "calendar", "data": {"calendar": {"api_id": "cal-TEST"}}}
        if "calendar/get-items" in url:
            return {"entries": [{"event": e} for e in events], "has_more": False}
        if "event/get" in url:
            eid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["event_api_id"][0]
            return details[eid]
        raise AssertionError(f"unexpected url {url}")
    return fake


class ScoringTests(unittest.TestCase):
    def test_extract_separates_host_names_from_bios(self):
        f = L.extract(DETAILS["evt-1"])
        self.assertEqual(f["host_names"], "Alpha Ventures")
        self.assertIn("early stage fund", f["hosts"])
        self.assertNotIn("early stage fund", f["host_names"])

    def test_description_text_has_no_node_names(self):
        f = L.extract(DETAILS["evt-1"])
        self.assertIn("Meet other founders", f["description"])
        self.assertNotIn("paragraph", f["description"])
        self.assertNotIn("bold", f["description"])

    def test_strong_weak_and_none(self):
        self.assertEqual([lv for lv, _ in L.evaluate(L.extract(DETAILS["evt-1"]), CRITERIA)], [2, 0])
        self.assertEqual([lv for lv, _ in L.evaluate(L.extract(DETAILS["evt-3"]), CRITERIA)], [1, 0])
        self.assertEqual([lv for lv, _ in L.evaluate(L.extract(DETAILS["evt-2"]), CRITERIA)], [0, 2])
        self.assertEqual([lv for lv, _ in L.evaluate(L.extract(DETAILS["evt-4"]), CRITERIA)], [0, 0])

    def test_word_boundaries(self):
        f = {k: "" for k in L.FIELDS}
        f["title"] = "MAIN stage"
        self.assertEqual(L.evaluate(f, CRITERIA)[1][0], 0)  # "MAIN" must not match \bAI\b

    def test_ranking_follows_criteria_order(self):
        items = {
            "only_second": L.rank_key([(0, ""), (2, "x")], "2026-10-07"),
            "first_strong": L.rank_key([(2, "x"), (0, "")], "2026-10-07"),
            "first_weak": L.rank_key([(1, "x"), (0, "")], "2026-10-07"),
            "both": L.rank_key([(2, "x"), (2, "y")], "2026-10-07"),
        }
        self.assertEqual(sorted(items, key=items.get), ["both", "first_strong", "first_weak", "only_second"])

    def test_ties_break_by_start_time(self):
        self.assertLess(L.rank_key([(2, "x")], "2026-10-06"), L.rank_key([(2, "x")], "2026-10-08"))

    def test_first_tier(self):
        self.assertEqual(L.first_tier([(0, ""), (1, "x"), (2, "y")]), 1)

    def test_exclusion_rule(self):
        self.assertTrue(L.is_excluded({"shown_date": "2026-09-28"}, "2026-09-29"))
        self.assertFalse(L.is_excluded({"shown_date": "2026-09-29"}, "2026-09-29"))
        self.assertTrue(L.is_excluded({"excluded": True}, "2026-09-29"))
        self.assertFalse(L.is_excluded({}, "2026-09-29"))

    def test_malformed_detail_does_not_crash(self):
        self.assertEqual(L.extract({})["title"], "")
        self.assertEqual(L.host_names({}), [])
        self.assertEqual(L.extract({"hosts": [None, "x"], "categories": [None]})["hosts"], "")

    def test_criteria_file_errors(self):
        with tempfile.TemporaryDirectory() as dd:
            def load(text):
                with open(os.path.join(dd, L.CRITERIA), "w") as f:
                    f.write(text)
                return L.load_criteria(dd)
            self.assertIsNone(L.load_criteria(tempfile.mkdtemp()))
            with self.assertRaises(SystemExit):
                load("{broken")
            with self.assertRaises(SystemExit):
                load('[{"tag":"X","name":"n","regex":"(","strong":["title"]}]')
            with self.assertRaises(SystemExit):
                load('[{"tag":"X","name":"n","regex":"a","strong":["nosuchfield"]}]')
            self.assertEqual(len(load('[{"tag":"X","name":"n","regex":"a","strong":["title"]}]')), 1)


class RunTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dd = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        with open(os.path.join(self.dd, L.CRITERIA), "w") as f:
            json.dump(CRITERIA, f)

    def run_tool(self, *args, fetch=None):
        argv = ["luma_scan.py", "--data-dir", self.dd, "--timezone", "UTC", *args]
        with patch.object(L, "fetch", fetch or make_fetch()), patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()):
            return L.main()

    def read(self, name):
        with open(os.path.join(self.dd, name), encoding="utf-8") as f:
            return f.read()

    def first_run(self, day="2026-10-01", *extra):
        return self.run_tool("--calendars", "demo", "--keywords", "investors", "--today", day, *extra)

    def test_first_run_writes_everything_and_ranks(self):
        self.assertEqual(self.first_run(), 0)
        for name in (L.LEDGER, L.SCANNED_REPORT, L.CANDIDATES, L.EXCLUDED, "cache/evt_evt-1.json"):
            self.assertTrue(os.path.exists(os.path.join(self.dd, name)), name)
        cand = self.read(L.CANDIDATES)
        self.assertLess(cand.index("Alpha Ventures Night"), cand.index("Community Dinner"))  # V strong before V weak
        self.assertLess(cand.index("Community Dinner"), cand.index("AI Builders Meetup"))  # criterion 1 before 2
        self.assertNotIn("Yoga in the Park", cand)
        ledger = json.loads(self.read(L.LEDGER))
        self.assertEqual(len(ledger["events"]), 4)
        self.assertTrue(ledger["events"]["evt-3"]["hit"])  # keyword "investors" is in its description
        self.assertFalse(ledger["events"]["evt-4"]["hit"])

    def test_keyword_scan_ignores_category_boilerplate(self):
        # Luma attaches the same category description to every event in that category.
        details = {k: json.loads(json.dumps(v)) for k, v in DETAILS.items()}
        for d in details.values():
            d["categories"] = [{"name": "Crypto", "description": "Join Ethereum hackathons and learn about zk"}]
        details["evt-2"]["event"]["description_mirror"] = doc("A real hackathons afterparty")
        self.run_tool("--calendars", "demo", "--keywords", "hackathons", "--today", "2026-10-01",
                      fetch=make_fetch(details=details))
        events = json.loads(self.read(L.LEDGER))["events"]
        self.assertEqual([k for k, v in events.items() if v["hit"]], ["evt-2"])

    def test_settings_are_remembered(self):
        self.first_run()
        self.assertEqual(self.run_tool("--today", "2026-10-01"), 0)  # no flags on the second run
        cfg = json.loads(self.read(L.LEDGER))["config"]
        self.assertEqual(cfg["calendars"], ["demo"])
        self.assertEqual(cfg["keywords"], "investors")
        self.assertEqual(cfg["timezone"], "UTC")

    def test_same_day_rerun_keeps_candidates(self):
        self.first_run("2026-10-01")
        self.run_tool("--today", "2026-10-01")
        self.assertIn("Alpha Ventures Night", self.read(L.CANDIDATES))

    def test_next_day_excludes_what_was_listed(self):
        self.first_run("2026-10-01")
        self.run_tool("--today", "2026-10-02")
        cand, excl = self.read(L.CANDIDATES), self.read(L.EXCLUDED)
        self.assertNotIn("Alpha Ventures Night", cand)
        for name in ("Alpha Ventures Night", "AI Builders Meetup", "Community Dinner"):
            self.assertIn(name, excl)
        self.assertNotIn("Yoga in the Park", excl)  # never matched, never listed, so not excluded

    def test_peek_does_not_exclude(self):
        self.first_run("2026-10-01", "--peek")
        self.run_tool("--today", "2026-10-02")
        self.assertIn("Alpha Ventures Night", self.read(L.CANDIDATES))

    def test_new_event_shows_up_after_exclusion(self):
        self.first_run("2026-10-01")
        events = CAL_EVENTS + [{"api_id": "evt-5", "name": "Late Capital Summit", "start_at": "2026-10-10T07:00:00.000Z", "url": "late"}]
        details = dict(DETAILS, **{"evt-5": {"event": {"name": "Late Capital Summit"}, "hosts": [{"name": "Zed Ventures"}],
                                             "categories": [], "calendar": {}}})
        self.run_tool("--today", "2026-10-02", fetch=make_fetch(events, details))
        cand = self.read(L.CANDIDATES)
        self.assertIn("Late Capital Summit", cand)
        self.assertNotIn("Alpha Ventures Night", cand)

    def test_exclude_and_restore(self):
        self.first_run("2026-10-01", "--peek")
        self.run_tool("--exclude", "alpha", "already", "registered", "--today", "2026-10-01")
        self.assertIn("already registered", self.read(L.EXCLUDED))
        self.run_tool("--today", "2026-10-01", "--peek")
        self.assertNotIn("Alpha Ventures Night", self.read(L.CANDIDATES))
        self.run_tool("--restore", "alpha", "--today", "2026-10-01")
        self.run_tool("--today", "2026-10-01", "--peek")
        self.assertIn("Alpha Ventures Night", self.read(L.CANDIDATES))

    def test_unknown_event_key_exits(self):
        self.first_run()
        with self.assertRaises(SystemExit) as cm:
            self.run_tool("--restore", "does-not-exist")
        self.assertEqual(cm.exception.code, 1)

    def test_notes_survive_reruns(self):
        self.first_run()
        self.run_tool("--note", "alpha", "registered on 10/1")
        self.run_tool("--full", "--today", "2026-10-01")
        self.assertEqual(json.loads(self.read(L.LEDGER))["notes"]["evt-1"], "registered on 10/1")
        self.assertIn("registered on 10/1", self.read(L.SCANNED_REPORT))

    def test_all_calendars_failing_stops_and_keeps_ledger(self):
        self.first_run()
        before = self.read(L.LEDGER)
        with self.assertRaises(SystemExit):
            self.run_tool("--today", "2026-10-02", fetch=make_fetch(fail=True))
        self.assertEqual(self.read(L.LEDGER), before)

    def test_failed_first_run_creates_no_ledger(self):
        with self.assertRaises(SystemExit):
            self.run_tool("--calendars", "demo", fetch=make_fetch(fail=True))
        self.assertFalse(os.path.exists(os.path.join(self.dd, L.LEDGER)))

    def test_corrupt_ledger_stops(self):
        with open(os.path.join(self.dd, L.LEDGER), "w") as f:
            f.write("{broken")
        with self.assertRaises(SystemExit):
            self.first_run()
        self.assertEqual(self.read(L.LEDGER), "{broken")  # untouched

    def test_first_run_without_calendars_exits(self):
        with self.assertRaises(SystemExit):
            self.run_tool("--today", "2026-10-01")

    def test_without_criteria_file_only_keyword_scan_runs(self):
        os.remove(os.path.join(self.dd, L.CRITERIA))
        self.first_run()
        self.assertFalse(os.path.exists(os.path.join(self.dd, L.CANDIDATES)))
        self.assertTrue(json.loads(self.read(L.LEDGER))["events"]["evt-3"]["hit"])

    def test_keywords_are_optional(self):
        self.assertEqual(self.run_tool("--calendars", "demo", "--today", "2026-10-01"), 0)
        self.assertFalse(any(e.get("hit") for e in json.loads(self.read(L.LEDGER))["events"].values()))
        self.assertIn("Alpha Ventures Night", self.read(L.CANDIDATES))

    def test_invalid_regex_and_timezone_exit(self):
        with self.assertRaises(SystemExit):
            self.run_tool("--calendars", "demo", "--keywords", "(")
        with self.assertRaises(SystemExit):
            self.run_tool("--calendars", "demo", "--timezone", "Not/AZone")

    def test_event_times_use_the_chosen_timezone(self):
        self.run_tool("--calendars", "demo", "--timezone", "Asia/Singapore", "--today", "2026-10-01")
        self.assertIn("10/07 15:00", self.read(L.CANDIDATES))  # 07:00 UTC is 15:00 in Singapore


if __name__ == "__main__":
    unittest.main()
