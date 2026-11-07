"""Offline tests - no API calls. Run:  python -m unittest discover -s tests -v

Uses a small original fixture show in a *different* screenplay format (tests/fixtures/odd_format_show)
to prove the tool copes with a show it has never seen. Tests on the real Kuku pack run only if data/ exists.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from promo_finder import pipeline  # noqa: E402
from promo_finder.export import build_zip, tc, to_edl  # noqa: E402
from promo_finder.feedback import analyse, load_approvals, save_decision  # noqa: E402
from promo_finder.llm import BaseLLM, parse_json, BudgetExceeded  # noqa: E402
from promo_finder.parser import load_show, load_show_from_bytes, parse_episode_text  # noqa: E402
from promo_finder.validate import Promo, Segment, check_promo, parse_ts  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "odd_format_show"
DATA = ROOT / "data"


class FakeLLM(BaseLLM):
    """Returns canned, deliberately sloppy JSON, so the validation layer has something to catch."""
    provider = "fake"

    def _call(self, system, user, json_mode):
        self.spend()
        if "MONTAGE" in user:
            ids = re.findall(r"^(E\d+-B\d+) ", user, re.M)
            return json.dumps({"montages": [{"title": "Trailer", "beats": ids[:3] + ["E99-B9"], "hook": "h",
                                             "cliffhanger": "c", "why": "w",
                                             "scores": {"hook": 9, "cliffhanger": 8, "standalone": 7, "emotion": 9}}]})
        if "POSTING ORDER" in user:
            ids = re.findall(r"^(P\d+) \|", user, re.M)
            return "```json\n" + json.dumps({"order": [{"id": i, "reason": "test"} for i in ids[::-1]],
                                             "weak": [{"id": ids[0], "problem": "needs backstory"}]}) + "\n```"
        return json.dumps({"promos": [
            {"title": "main", "segments": [{"start": "00:00.40", "end": "00:31.00"}], "hook": "slam", "cliffhanger": "threat",
             "why": "z", "scores": {"hook": 8, "cliffhanger": 7, "standalone": 6, "emotion": 8}},
            {"title": "too short", "segments": [{"start": "00:01.00", "end": "00:06.00"}], "scores": {}},
        ]})


class ParserTests(unittest.TestCase):
    def test_unseen_format_parses(self):
        show = load_show(FIXTURE)
        self.assertEqual([e.number for e in show.episodes], [1, 2])
        ep1, ep2 = show.episodes
        self.assertEqual(len(ep1.events), 14)                       # HH:MM:SS,ff + bracket times + plain labels
        self.assertEqual(ep1.events[1].speaker, "MAYA")
        self.assertEqual(ep1.events[1].emotion, "Furious")
        self.assertAlmostEqual(ep1.duration, 52.0)
        kinds = {e.kind for e in ep2.events}
        self.assertTrue({"dialogue", "action", "sfx"} <= kinds)     # "Start:, End:", "-->", "( – )" all understood
        self.assertEqual(len(ep2.warnings), 2)                      # bad block skipped, reversed times swapped
        swapped = [e for e in ep2.events if e.speaker == "ETHAN" and e.emotion == "Shaken"][0]
        self.assertLess(swapped.start, swapped.end)

    def test_garbage_does_not_crash(self):
        ep = parse_episode_text("hello\nthis is not a screenplay\n**BROKEN", "junk.txt", 1)
        self.assertEqual(ep.events, [])
        self.assertIn("no timestamped events found", ep.warnings)
        show = load_show_from_bytes(b"\x00\xff junk", "junk.txt")
        self.assertEqual(len(show.episodes), 1)

    def test_zip_upload(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for f in FIXTURE.glob("*.txt"):
                z.writestr(f"My Show/{f.name}", f.read_text())
        show = load_show_from_bytes(buf.getvalue(), "pack.zip")
        self.assertEqual(show.title, "My Show")
        self.assertEqual(len(show.episodes), 2)

    def test_timestamp_formats(self):
        self.assertAlmostEqual(parse_ts("01:14.30"), 74.3)
        self.assertAlmostEqual(parse_ts("(00:13.50)"), 13.5)
        self.assertAlmostEqual(parse_ts("01:00:02,5"), 3602.5)
        self.assertIsNone(parse_ts("soon"))

    @unittest.skipUnless((DATA).exists(), "Kuku input pack not present")
    def test_real_pack(self):
        show = load_show(DATA)
        self.assertEqual(len(show.episodes), 50)
        self.assertEqual(sum(len(e.events) for e in show.episodes), 3727)
        self.assertEqual(sum(len(e.warnings) for e in show.episodes), 0)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.show = load_show(FIXTURE)

    def test_snaps_to_real_lines_and_never_cuts_mid_line(self):
        p = Promo("T1", "single", "t", [Segment(1, 4.0, 27.0)])   # starts inside a line, ends inside a line
        ok, _ = check_promo(self.show, p)
        self.assertTrue(ok)
        s = p.segments[0]
        starts = {e.start for e in self.show.ep(1).events}
        ends = {e.end for e in self.show.ep(1).events}
        self.assertIn(s.start, starts)
        self.assertIn(s.end, ends)

    def test_rejects_too_short_and_unknown_episode(self):
        self.assertFalse(check_promo(self.show, Promo("T2", "single", "t", [Segment(1, 0.5, 7.2)]))[0])
        self.assertFalse(check_promo(self.show, Promo("T3", "single", "t", [Segment(9, 0, 30)]))[0])


class PipelineTests(unittest.TestCase):
    def test_rules_only_end_to_end_on_unseen_show(self):
        with tempfile.TemporaryDirectory() as d:
            res = pipeline.run(FIXTURE, model="none", out_dir=d, progress=lambda *a: None)
        self.assertGreater(len(res["promos"]), 0)
        for p in res["promos"]:
            self.assertTrue(19 <= p["duration"] <= 63)

    def test_llm_path_with_fake_model(self):
        orig = pipeline.get_llm
        pipeline.get_llm = lambda spec=None, key=None: FakeLLM("fake")
        try:
            with tempfile.TemporaryDirectory() as d:
                res = pipeline.run(FIXTURE, model="fake:x", out_dir=d, progress=lambda *a: None)
                cached = pipeline.run(FIXTURE, model="fake:x", out_dir=d, progress=lambda *a: None)
        finally:
            pipeline.get_llm = orig
        self.assertEqual(res["counts"]["llm_requests"], 4)        # 2 episodes + montage + judge
        self.assertEqual(cached["counts"]["llm_requests"], 0)     # second run fully cached
        reasons = " ".join(r["reason"] for r in res["rejected"])
        self.assertIn("too short", reasons)                       # sloppy LLM pick caught in code
        self.assertTrue(any("judge:" in f for p in res["promos"] for f in p["flags"]))

    def test_budget_cap(self):
        llm = FakeLLM("fake")
        llm.max_calls = 1
        llm.complete("s", "u")
        with self.assertRaises(BudgetExceeded):
            llm.complete("s", "u")

    def test_parse_json_tolerates_fences(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json('Sure! {"a": 2} hope that helps'), {"a": 2})


class ExportAndFeedbackTests(unittest.TestCase):
    PROMO = {"id": "P001", "rank": 1, "title": "Landlord reveal", "hook": "slam", "cliffhanger": "locket",
             "segments": [{"episode": 1, "start": "00:00.50", "end": "00:30.00", "start_sec": 0.5, "end_sec": 30.0},
                          {"episode": 2, "start": "00:20.50", "end": "00:30.00", "start_sec": 20.5, "end_sec": 30.0}],
             "kind": "montage", "duration": 39.0, "why": "", "rank_reason": "", "final_score": 0.7, "rule_score": 0.6,
             "scores": {"hook": 8}, "context_needed": "", "flags": [], "source": "llm"}

    def test_timecode(self):
        self.assertEqual(tc(3661.5, 30), "01:01:01:15")
        self.assertEqual(tc(0.5, 25), "00:00:00:13")

    def test_edl_events_are_contiguous(self):
        edl = to_edl(self.PROMO, fps=30)
        rows = [l for l in edl.splitlines() if l[:3].isdigit()]
        self.assertEqual(len(rows), 2)
        self.assertIn("EP001", rows[0])
        self.assertEqual(rows[0].split()[-1], rows[1].split()[-2])   # record out of event 1 == record in of event 2
        self.assertIn("episode-001.mp4", edl)

    def test_zip_contents(self):
        z = zipfile.ZipFile(io.BytesIO(build_zip([self.PROMO])))
        names = z.namelist()
        self.assertIn("cut_promos.sh", names)
        self.assertTrue(any(n.startswith("edl/") for n in names))
        self.assertIn("concat", z.read("cut_promos.sh").decode())

    def test_decisions_saved_and_analysed(self):
        with tempfile.TemporaryDirectory() as d:
            save_decision(d, "P001", "approved")
            save_decision(d, "P002", "rejected", "Needs backstory")
            save_decision(d, "P003", "approved")
            save_decision(d, "P003", None)                       # undo
            dec = load_approvals(d)
        self.assertEqual(set(dec), {"P001", "P002"})
        promos = [dict(self.PROMO, id="P001", scores={"hook": 9}), dict(self.PROMO, id="P002", scores={"hook": 5})]
        a = analyse(promos, dec)
        self.assertEqual(a["precision"], 0.5)
        self.assertEqual(a["reject_reasons"], [("Needs backstory", 1)])
        self.assertEqual(a["score_gap"]["hook"]["gap"], 4.0)


if __name__ == "__main__":
    unittest.main()
