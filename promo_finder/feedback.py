"""Editor decisions (approve / reject + reason) saved next to each run, so they become labelled data.

outputs/<show>/approvals.json:
    {"P003": {"status": "approved", "reason": "", "at": "2026-11-06 17:40:00"},
     "P011": {"status": "rejected", "reason": "Needs backstory", "at": "..."}}

`analyse()` turns those labels into the numbers a team would use to tune the tool:
precision of the top picks, the most common reject reasons, and which score dimension actually
separates approved from rejected promos (the evidence for re-weighting rank.py).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

FILE = "approvals.json"
REJECT_REASONS = ["Needs backstory", "Weak hook", "Ending resolves too much", "Bad cut point", "Too similar to another",
                  "Spoils too much", "Other"]


def load_approvals(run_dir: str | Path) -> dict:
    p = Path(run_dir) / FILE
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


def save_decision(run_dir: str | Path, promo_id: str, status: str | None, reason: str = "") -> dict:
    """status: 'approved' | 'rejected' | None (clear)."""
    data = load_approvals(run_dir)
    if status in (None, "", "clear"):
        data.pop(promo_id, None)
    else:
        if status not in ("approved", "rejected"):
            raise ValueError("status must be approved, rejected or clear")
        data[promo_id] = {"status": status, "reason": reason.strip()[:200], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    path = Path(run_dir) / FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)  # atomic, so a crash never leaves half a file
    return data


def analyse(promos: list[dict], decisions: dict, top: int = 10) -> dict:
    labelled = [p for p in promos if p["id"] in decisions]
    ok = [p for p in labelled if decisions[p["id"]]["status"] == "approved"]
    bad = [p for p in labelled if decisions[p["id"]]["status"] == "rejected"]
    top_l = [p for p in promos[:top] if p["id"] in decisions]
    top_ok = [p for p in top_l if decisions[p["id"]]["status"] == "approved"]

    def mean(rows, key):
        vals = []
        for p in rows:
            v = (p.get("scores") or {}).get(key) if key in ("hook", "cliffhanger", "standalone", "emotion") else p.get(key)
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        return round(sum(vals) / len(vals), 2) if vals else None

    dims = {}
    for k in ("hook", "cliffhanger", "standalone", "emotion", "rule_score", "final_score"):
        a, r = mean(ok, k), mean(bad, k)
        dims[k] = {"approved": a, "rejected": r, "gap": round(a - r, 2) if a is not None and r is not None else None}
    return {
        "labelled": len(labelled),
        "approved": len(ok),
        "rejected": len(bad),
        "precision": round(len(ok) / len(labelled), 3) if labelled else None,
        "precision_top": round(len(top_ok) / len(top_l), 3) if top_l else None,
        "top_labelled": len(top_l),
        "reject_reasons": Counter(decisions[p["id"]].get("reason") or "No reason" for p in bad).most_common(),
        "score_gap": dims,  # bigger positive gap = that score separates good from bad picks better
    }
