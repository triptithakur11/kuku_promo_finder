"""Find promos in a microdrama screenplay pack.

Examples
  python cli.py --input pack.zip                                  # default model (PROMO_MODEL or Gemini Flash)
  python cli.py --input data/ --model none                        # offline, rules only
  python cli.py --input pack.zip --model groq:llama-3.3-70b-versatile
  python cli.py --input pack.zip --episodes 1-10 --no-judge
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from promo_finder.pipeline import run, estimate  # noqa: E402  (after load_dotenv so env vars apply)
from promo_finder.report import write_all  # noqa: E402


def parse_range(s: str | None) -> list[int] | None:
    if not s:
        return None
    out: list[int] = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kuku promo finder")
    ap.add_argument("--input", "-i", required=True, help=".zip, folder of .txt episodes, or one .txt")
    ap.add_argument("--model", "-m", default=None, help="provider:model, e.g. gemini:gemini-3.8-flash, "
                    "groq:llama-3.3-70b-versatile, ollama:llama3.1, openai:gpt-4o-mini, anthropic:<model>, none")
    ap.add_argument("--out", "-o", default="outputs", help="output root folder")
    ap.add_argument("--episodes", "-e", default=None, help="subset, e.g. 1-10 or 1,4,7")
    ap.add_argument("--montages", type=int, default=4, help="number of cross-episode montage promos (0 = off)")
    ap.add_argument("--no-judge", action="store_true", help="skip the LLM posting-order pass")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached LLM responses")
    ap.add_argument("--top", type=int, default=10, help="how many to print")
    ap.add_argument("--max-calls", type=int, default=None,
                    help="hard cap on real LLM requests; episodes past the cap fall back to rules")
    ap.add_argument("--dry-run", action="store_true", help="print how many requests/tokens a run would use; no API calls")
    a = ap.parse_args(argv)

    if a.max_calls is not None:
        os.environ["PROMO_MAX_CALLS"] = str(a.max_calls)
    if a.dry_run:
        est = estimate(a.input, out_dir=a.out, episodes=parse_range(a.episodes), montages=a.montages,
                       judge=not a.no_judge)
        for k, v in est.items():
            print(f"{k:>28}: {v}")
        return 0

    res = run(a.input, model=a.model, out_dir=a.out, episodes=parse_range(a.episodes), montages=a.montages,
              judge=not a.no_judge, use_cache=not a.no_cache)
    out = write_all(res)
    print(f"\nTop {a.top} promos for '{res['show']}' ({res['model']}):")
    for p in res["promos"][:a.top]:
        segs = " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in p["segments"])
        print(f"{p['rank']:>3}. [{p['id']}] {segs} ({p['duration']:.0f}s)  hook: {p['hook'][:70]}")
    print(f"\nLLM requests made this run: {res['counts']['llm_requests']}")
    print(f"Wrote {out}/promos.json, promos.csv, promos.md (raw LLM responses in {out}/raw_llm/)")
    if res["log"]:
        print(f"{len(res['log'])} warnings — see the 'Run log' section of promos.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
