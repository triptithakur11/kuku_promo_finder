"""Quality report for a promo run: hard-rule compliance, coverage, rules-vs-LLM
agreement, likely bad picks, and (optionally) precision against human labels.

    python eval/quality_check.py outputs/<show>/promos.json --input data/
    python eval/quality_check.py outputs/<show>/promos.json --input data/ --labels eval/labels.csv

labels.csv columns: id,verdict,note   (verdict = good | ok | bad)
Writes quality.md next to promos.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from promo_finder.parser import load_show, fmt_ts  # noqa: E402
from promo_finder.signals import candidate_windows, hook_score, cliff_score, HOOK_WINDOW  # noqa: E402
from promo_finder.feedback import load_approvals, analyse  # noqa: E402


def pct(n, d):
    return f"{(100 * n / d):.0f}%" if d else "n/a"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("promos")
    ap.add_argument("--input", "-i", required=True, help="the same screenplay pack the run used")
    ap.add_argument("--labels", default=None)
    ap.add_argument("--top", type=int, default=10, help="size of the 'post first' set to inspect closely")
    a = ap.parse_args(argv)

    res = json.loads(Path(a.promos).read_text())
    show = load_show(a.input)
    promos = res["promos"]
    n = len(promos)
    top = promos[: a.top]
    L = [f"# Quality report — {res['show']}", "", f"Run: `{res['model']}` at {res['created']}; {n} promos kept, "
         f"{res['counts']['rejected']} rejected by validation (of {res['counts']['proposed']} proposed).", ""]

    in_range = [p for p in promos if 20 <= p["duration"] <= 60]
    hook_ok, end_ok, names_heavy, bad = [], [], [], []
    for p in promos:
        s0 = p["segments"][0]
        ep0 = show.ep(s0["episode"])
        first = [e for e in ep0.events_between(s0["start_sec"], s0["start_sec"] + HOOK_WINDOW, ("dialogue", "action", "sfx"))
                 if e.start >= s0["start_sec"] - 0.5]
        hs = max((hook_score(e) for e in first), default=0.0)
        if hs >= 0.45:
            hook_ok.append(p["id"])
        s1 = p["segments"][-1]
        ep1 = show.ep(s1["episode"])
        last = ep1.events_between(s1["end_sec"] - 4, s1["end_sec"], ("dialogue", "action", "sfx"))
        cs = max((cliff_score(e, ep1) for e in last), default=0.0)
        if cs >= 0.3 or s1["end_sec"] >= ep1.duration - 3:
            end_ok.append(p["id"])
        # standalone proxy: how many distinct named speakers a stranger must track
        speakers = {re.sub(r"\s*\(.*", "", x.split(" ", 2)[2].split(":")[0]) for x in p["excerpt"]
                    if len(x.split(" ", 2)) > 2 and ":" in x.split(" ", 2)[2] and not x.split(" ", 2)[2].startswith("[")}
        if len(speakers) >= 5:
            names_heavy.append((p["id"], len(speakers)))
        if hs < 0.3 or cs < 0.2:
            bad.append((p, hs, cs))

    L += ["## 1. Hard rules (checked in code, not by the LLM)", "",
          f"| check | all promos | top {a.top} |", "|---|---|---|",
          f"| duration 20–60s | {pct(len(in_range), n)} | {pct(sum(1 for p in top if 20 <= p['duration'] <= 60), len(top))} |",
          f"| strong hook beat in first 3s (rule score ≥0.45) | {pct(len(hook_ok), n)} | {pct(sum(1 for p in top if p['id'] in hook_ok), len(top))} |",
          f"| ends on a cliffhanger cue or the episode's final stinger | {pct(len(end_ok), n)} | {pct(sum(1 for p in top if p['id'] in end_ok), len(top))} |",
          f"| timestamps snapped to real lines (all, enforced) | 100% | 100% |", ""]

    ep_counter = Counter(e for p in promos for e in p["episodes"])
    kinds = Counter(p["kind"] for p in promos)
    tropes = Counter(t.lower() for p in promos for t in p.get("tropes", []))
    no_promo = [e.number for e in show.episodes if e.number in res["episodes_processed"] and e.number not in ep_counter]
    L += ["## 2. Coverage and variety", "",
          f"- Promo types: {dict(kinds)}",
          f"- Episodes with ≥1 promo: {len(ep_counter)}/{len(res['episodes_processed'])}. "
          f"Episodes with none: {no_promo or 'none'}",
          f"- Top tropes: {', '.join(f'{t} ({c})' for t, c in tropes.most_common(8)) or 'n/a (rules-only run)'}",
          f"- Top {a.top} come from episodes: {[p['episodes'] for p in top]}", ""]

    if res["model"] != "rules-only":
        agree = 0
        llm_single = [p for p in promos if p["kind"] != "montage" and p["source"] == "llm"]
        for p in llm_single:
            s = p["segments"][0]
            ep = show.ep(s["episode"])
            for c in candidate_windows(ep, top_k=5):
                inter = max(0, min(c.end, s["end_sec"]) - max(c.start, s["start_sec"]))
                if inter / max(1, min(c.duration, s["duration"])) >= 0.5:
                    agree += 1
                    break
        L += ["## 3. Does the LLM agree with the cheap rules?", "",
              f"{pct(agree, len(llm_single))} of LLM single-episode picks overlap ≥50% with one of the top-5 rule windows. "
              "Low agreement is not automatically bad (rules can't read meaning), but picks the rules hate are the "
              "first ones to eyeball.", ""]

    L += ["## 4. Where it probably picks badly (auto-flagged, needs a human look)", ""]
    flagged = [p for p in promos if p["flags"]]
    L.append(f"- {len(flagged)} promos carry validation/judge warnings:")
    for p in flagged[:15]:
        L.append(f"  - #{p['rank']} {p['id']} ({p['segments'][0]['episode']}): {'; '.join(p['flags'])[:220]}")
    L.append(f"- {len(bad)} promos have a weak hook or weak ending by rule score:")
    for p, hs, cs in bad[:10]:
        L.append(f"  - #{p['rank']} {p['id']} Ep{p['episodes']} hook={hs:.2f} end={cs:.2f}: \"{p['hook'][:90]}\"")
    L.append(f"- {len(names_heavy)} promos ask a stranger to track ≥5 speakers (standalone risk): "
             f"{', '.join(f'{i} ({k})' for i, k in names_heavy[:12]) or 'none'}")
    ctx = [p for p in promos if p.get("context_needed")]
    L.append(f"- {len(ctx)} promos where the LLM itself said a stranger lacks context, e.g.:")
    for p in ctx[:6]:
        L.append(f"  - #{p['rank']} {p['id']}: {p['context_needed'][:160]}")
    late = [p for p in top if min(p["episodes"]) > 30]
    L.append(f"- {len(late)} of the top {a.top} start after episode 30 (heavier backstory, spoiler risk).")
    L.append("")

    decisions = load_approvals(Path(a.promos).parent)
    if a.labels and Path(a.labels).exists():
        for r in csv.DictReader(open(a.labels)):
            v = r.get("verdict", "").strip().lower()
            if r.get("id") and v:
                decisions.setdefault(r["id"], {"status": "approved" if v in ("good", "ok") else "rejected",
                                               "reason": r.get("note", "")})
    L += ["## 5. Human review (editor decisions)", ""]
    if decisions:
        fb = analyse(promos, decisions, top=a.top)
        top_prec = "n/a" if fb["precision_top"] is None else f"{fb['precision_top']:.0%}"
        L += [f"- Reviewed {fb['labelled']} promos: {fb['approved']} approved, {fb['rejected']} rejected → "
              f"precision {pct(fb['approved'], fb['labelled'])}",
              f"- Precision in the top {a.top}: {top_prec} "
              f"({fb['top_labelled']} of them reviewed)",
              f"- Why picks were rejected: {', '.join(f'{r} ({n})' for r, n in fb['reject_reasons']) or 'none yet'}", "",
              "Which score separates approved from rejected picks (bigger gap = more useful signal; "
              "use this to re-weight `rank.py`):", "", "| score | approved avg | rejected avg | gap |", "|---|---|---|---|"]
        for k, v in fb["score_gap"].items():
            L.append(f"| {k} | {v['approved'] if v['approved'] is not None else '-'} | "
                     f"{v['rejected'] if v['rejected'] is not None else '-'} | {v['gap'] if v['gap'] is not None else '-'} |")
        L.append("")
    else:
        L += ["No decisions yet. Approve/Reject promos in the UI (saved to approvals.json) or fill "
              "`eval/labels.csv` (id,verdict,note), then re-run.", ""]

    out = Path(a.promos).with_name("quality.md")
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
