"""Write results as JSON (machines), CSV (editor sheet) and Markdown (human review)."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path


def seg_str(p: dict) -> str:
    return " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in p["segments"])


def to_csv(promos: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "id", "type", "title", "segments", "duration_s", "hook", "cliffhanger", "why",
                "rank_reason", "final_score", "rule_score", "llm_hook", "llm_cliff", "llm_standalone",
                "llm_emotion", "context_needed", "flags", "source"])
    for p in promos:
        sc = p.get("scores") or {}
        w.writerow([p["rank"], p["id"], p["kind"], p["title"], seg_str(p), p["duration"], p["hook"],
                    p["cliffhanger"], p["why"], p["rank_reason"], p["final_score"], p["rule_score"],
                    sc.get("hook", ""), sc.get("cliffhanger", ""), sc.get("standalone", ""), sc.get("emotion", ""),
                    p["context_needed"], " | ".join(p["flags"]), p["source"]])
    return buf.getvalue()


def to_markdown(result: dict, top: int | None = None) -> str:
    promos = result["promos"][:top] if top else result["promos"]
    L = [f"# Promo picks — {result['show']}", "",
         f"Model: `{result['model']}` · run {result['created']} · episodes {len(result['episodes_processed'])} · "
         f"{result['counts']['kept']} promos kept, {result['counts']['rejected']} rejected", "",
         "## Ranking (post in this order)", "",
         "| # | ID | Type | Segments | Sec | Hook | Why post here |", "|---|---|---|---|---|---|---|"]
    for p in promos:
        L.append(f"| {p['rank']} | {p['id']} | {p['kind']} | {seg_str(p)} | {p['duration']:.0f} | "
                 f"{p['hook'][:90].replace('|', '/')} | {p['rank_reason'][:120].replace('|', '/')} |")
    L.append("")
    for p in promos:
        sc = p.get("scores") or {}
        L += [f"## #{p['rank']} · {p['id']} · {p['title'] or '(untitled)'}", "",
              f"- **Type:** {p['kind']} · **Duration:** {p['duration']:.1f}s · **Score:** {p['final_score']:.2f} "
              f"(rules {p['rule_score']:.2f}; LLM h/c/s/e = {sc.get('hook', '-')}/{sc.get('cliffhanger', '-')}/"
              f"{sc.get('standalone', '-')}/{sc.get('emotion', '-')})",
              "- **Segments (in order):**"]
        for s in p["segments"]:
            L.append(f"  - Episode {s['episode']}: {s['start']} → {s['end']} ({s['duration']:.1f}s)")
        L += [f"- **Hook (first 3s):** {p['hook']}",
              f"- **Cliffhanger:** {p['cliffhanger']}",
              f"- **Why it works:** {p['why']}",
              f"- **Why this rank:** {p['rank_reason']}"]
        if p["context_needed"]:
            L.append(f"- **Context a stranger lacks:** {p['context_needed']}")
        if p["flags"]:
            L.append(f"- **⚠ Flags:** {'; '.join(p['flags'])}")
        L += ["", "<details><summary>Script excerpt</summary>", "", "```"] + p["excerpt"] + ["```", "</details>", ""]
    if result.get("rejected"):
        L += ["## Rejected proposals", ""]
        for r in result["rejected"]:
            L.append(f"- {r['promo']['id']} ({seg_str(r['promo']) or 'no segments'}): {r['reason']}")
    if result.get("log"):
        L += ["", "## Run log", ""] + [f"- {x}" for x in result["log"]]
    return "\n".join(L) + "\n"


def write_all(result: dict, out_dir: str | Path | None = None) -> Path:
    out = Path(out_dir or result["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    saved = {k: v for k, v in result.items() if k != "out_dir"}
    (out / "promos.json").write_text(json.dumps(saved, indent=2, ensure_ascii=False))
    (out / "promos.csv").write_text(to_csv(result["promos"]))
    (out / "promos.md").write_text(to_markdown(result))
    return out
