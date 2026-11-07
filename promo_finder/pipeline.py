"""End-to-end orchestration: parse -> rules -> LLM per episode -> montages -> validate -> rank -> judge."""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Callable

from . import prompts
from .llm import BaseLLM, get_llm, parse_json, LLMError
from .parser import Show, Episode, load_show, fmt_ts
from .signals import candidate_windows, top_moments
from .validate import Promo, Segment, check_promo, parse_ts
from .rank import score, dedupe, apply_order

Progress = Callable[[str, float], None]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "show"


class RawStore:
    """Saves every prompt/response unedited (required 'raw outputs') and doubles as a cache."""

    def __init__(self, folder: Path, use_cache: bool = True):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache

    def call(self, llm: BaseLLM, name: str, system: str, user: str) -> tuple[str, bool]:
        h = hashlib.sha256(f"{llm.name}\n{system}\n{user}".encode()).hexdigest()[:16]
        path = self.folder / f"{name}.json"
        if self.use_cache and path.exists():
            try:
                old = json.loads(path.read_text())
                if old.get("hash") == h and old.get("response"):
                    return old["response"], True
            except json.JSONDecodeError:
                pass
        t0 = time.time()
        resp = llm.complete(system, user, json_mode=True)
        path.write_text(json.dumps({"name": name, "model": llm.name, "hash": h, "seconds": round(time.time() - t0, 1),
                                    "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "system": system, "prompt": user, "response": resp}, indent=2, ensure_ascii=False))
        return resp, False


def transcript(ep: Episode, camera: bool = True, max_camera_chars: int = 110) -> str:
    lines = []
    for e in ep.events:
        if e.kind == "camera":
            if not camera:
                continue
            txt = e.text if len(e.text) <= max_camera_chars else e.text[:max_camera_chars] + "…"
            lines.append(f"[{fmt_ts(e.start)}-{fmt_ts(e.end)}] CAMERA: {txt}")
        elif e.kind == "dialogue":
            emo = f" ({e.emotion})" if e.emotion else ""
            lines.append(f"[{fmt_ts(e.start)}-{fmt_ts(e.end)}] {e.speaker}{emo}: \"{e.text}\"")
        else:
            lines.append(f"[{fmt_ts(e.start)}-{fmt_ts(e.end)}] {e.kind.upper()}: {e.text}")
    return "\n".join(lines)


def _promo_from_rule(c, pid: str) -> Promo:
    p = Promo(id=pid, kind="single", title=f"Ep{c.episode} rule pick",
              segments=[Segment(c.episode, c.start, c.end)],
              hook=c.hook_event.label(), cliffhanger=c.cliff_event.label(),
              why="Rule pick: " + ", ".join(c.reasons), source="rules")
    return p


def _promos_from_llm(data: dict, episode: int, start_id: int) -> list[Promo]:
    out = []
    for i, d in enumerate((data or {}).get("promos", []) or []):
        segs = []
        for s in d.get("segments", []) or []:
            a, b = parse_ts(s.get("start")), parse_ts(s.get("end"))
            if a is not None and b is not None:
                segs.append(Segment(int(s.get("episode", episode) or episode), a, b))
        out.append(Promo(id=f"P{start_id + i:03d}", kind="single" if len(segs) == 1 else "multi",
                         title=str(d.get("title", ""))[:80], segments=segs, hook=str(d.get("hook", "")),
                         cliffhanger=str(d.get("cliffhanger", "")), why=str(d.get("why", "")),
                         scores=d.get("scores") or {}, context_needed=str(d.get("context_needed", "") or ""),
                         tropes=list(d.get("tropes") or []), source="llm"))
    return out


def run(input_path: str | Path | None = None, *, show: Show | None = None, model: str | None = None,
        api_key: str | None = None, out_dir: str | Path = "outputs", episodes: list[int] | None = None,
        montages: int = 4, judge: bool = True, per_episode_rules: int = 2, use_cache: bool = True,
        progress: Progress | None = None) -> dict:
    say = progress or (lambda msg, frac: print(f"[{frac:5.0%}] {msg}"))
    show = show or load_show(input_path)
    eps = [e for e in show.episodes if not episodes or e.number in episodes]
    llm = get_llm(model, api_key)
    out = Path(out_dir) / slugify(show.title)
    raw = RawStore(out / "raw_llm", use_cache=use_cache)
    log: list[str] = []
    say(f"Loaded '{show.title}': {len(eps)} episodes, model={llm.name if llm else 'rules-only'}", 0.0)
    state = {"frac": 0.0}
    if llm is not None:
        llm.notify = lambda msg: say(msg, state["frac"])
    for e in eps:
        for w in e.warnings:
            log.append(f"parse ep{e.number}: {w}")

    proposals: list[Promo] = []
    pid = 1
    premise = show.episodes[0].logline if show.episodes else ""

    for i, ep in enumerate(eps):
        cands = candidate_windows(ep, top_k=5)
        frac = 0.05 + 0.65 * i / max(1, len(eps))
        if llm is None:
            for c in cands[:per_episode_rules]:
                proposals.append(_promo_from_rule(c, f"P{pid:03d}")); pid += 1
            continue
        state["frac"] = frac
        say(f"Episode {ep.number} ({i + 1} of {len(eps)}): asking {llm.name}… usually 10–60s", frac)
        cand_txt = "\n".join(f"- {c.short()}" for c in cands) or "(none)"
        user = prompts.EPISODE_PROMPT.format(title=show.title, premise=premise, episode=ep.number,
                                             duration=fmt_ts(ep.duration), logline=ep.logline or "(none)",
                                             continuity=ep.continuity or "(none)", transcript=transcript(ep),
                                             candidates=cand_txt)
        try:
            resp, cached = raw.call(llm, f"episode_{ep.number:03d}", prompts.SYSTEM, user)
            say(f"Episode {ep.number}: {'cached' if cached else 'LLM done'}", frac)
            new = _promos_from_llm(parse_json(resp), ep.number, pid)
            for p in new:  # the LLM may only cite this episode in the per-episode pass
                for s in p.segments:
                    s.episode = ep.number
        except (LLMError, ValueError, json.JSONDecodeError) as ex:
            log.append(f"ep{ep.number}: LLM failed ({str(ex)[:200]}); fell back to rules")
            say(f"Episode {ep.number}: LLM failed, using rules", frac)
            new = [_promo_from_rule(c, f"P{pid + j:03d}") for j, c in enumerate(cands[:per_episode_rules])]
        proposals += new
        pid += len(new)

    if llm is not None and montages > 0 and len(eps) > 1:
        state["frac"] = 0.72
        say(f"Designing cross-episode trailers with {llm.name}…", 0.72)
        beats, beat_map = [], {}
        for ep in eps:
            for j, ev in enumerate(top_moments(ep, k=5), 1):
                bid = f"E{ep.number:02d}-B{j}"
                ctx = ep.events_between(ev.start - 2.5, ev.end + 5.0, kinds=("dialogue", "action", "sfx"))
                s0 = min([ev.start] + [x.start for x in ctx if x.start >= ev.start - 2.5])
                s1 = max([ev.end] + [x.end for x in ctx if x.end <= ev.end + 5.0])
                beat_map[bid] = (ep.number, s0, s1)
                txt = " / ".join(x.label()[:120] for x in ctx)[:400]
                beats.append(f"{bid} [{fmt_ts(s0)}-{fmt_ts(s1)}, {s1 - s0:.0f}s]: {txt}")
        guide = "\n".join(f"Ep{e.number}: {e.logline}" for e in eps)
        user = prompts.MONTAGE_PROMPT.format(title=show.title, guide=guide, beats="\n".join(beats), n=montages)
        try:
            resp, _ = raw.call(llm, "montages", prompts.SYSTEM, user)
            for d in parse_json(resp).get("montages", []) or []:
                segs = [Segment(*beat_map[b]) for b in d.get("beats", []) if b in beat_map]
                bad = [b for b in d.get("beats", []) if b not in beat_map]
                p = Promo(id=f"P{pid:03d}", kind="montage", title=str(d.get("title", ""))[:80], segments=segs,
                          hook=str(d.get("hook", "")), cliffhanger=str(d.get("cliffhanger", "")),
                          why=str(d.get("why", "")), scores=d.get("scores") or {},
                          context_needed=str(d.get("context_needed", "") or ""), tropes=list(d.get("tropes") or []))
                if bad:
                    p.flags.append(f"LLM cited unknown beats {bad}")
                proposals.append(p); pid += 1
        except (LLMError, ValueError, json.JSONDecodeError) as ex:
            log.append(f"montages: LLM failed ({str(ex)[:200]})")

    say("Validating timestamps and scoring", 0.82)
    valid, rejected = [], []
    for p in proposals:
        ok, why = check_promo(show, p)
        if ok:
            score(show, p)
            valid.append(p)
        else:
            rejected.append({"promo": p.to_dict(), "reason": why})
    kept, dups = dedupe(valid)
    rejected += [{"promo": p.to_dict(), "reason": r} for p, r in dups]

    order, weak = None, None
    if llm is not None and judge and kept:
        state["frac"] = 0.9
        say(f"Asking {llm.name} for the posting order…", 0.9)
        top = sorted(kept, key=lambda x: x.final_score, reverse=True)[:20]
        cand = "\n".join(
            f"{p.id} | {p.kind} | eps {p.episodes} | {p.duration:.0f}s | score {p.final_score:.2f} | "
            f"hook: {p.hook[:140]} | ends: {p.cliffhanger[:140]} | why: {p.why[:140]} | "
            f"context needed: {p.context_needed[:100] or '-'}" for p in top)
        user = prompts.JUDGE_PROMPT.format(title=show.title, candidates=cand, n=min(10, len(top)))
        try:
            resp, _ = raw.call(llm, "judge", prompts.SYSTEM, user)
            data = parse_json(resp)
            order, weak = data.get("order"), data.get("weak")
        except (LLMError, ValueError, json.JSONDecodeError) as ex:
            log.append(f"judge: LLM failed ({str(ex)[:200]})")
    ranked = apply_order(kept, order, weak)

    result = {
        "show": show.title,
        "model": llm.name if llm else "rules-only",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "episodes_processed": [e.number for e in eps],
        "counts": {"proposed": len(proposals), "valid": len(valid), "kept": len(ranked), "rejected": len(rejected),
                   "llm_requests": llm.calls if llm else 0},
        "promos": [p.to_dict() for p in ranked],
        "rejected": rejected,
        "log": log,
        "out_dir": str(out),
    }
    say(f"Done: {len(ranked)} promos ({len(rejected)} rejected)", 1.0)
    return result


def estimate(input_path=None, *, show: Show | None = None, out_dir="outputs", episodes=None, montages=4,
             judge=True) -> dict:
    """Dry run: how many LLM requests a run would make and roughly how many tokens - no API calls."""
    show = show or load_show(input_path)
    eps = [e for e in show.episodes if not episodes or e.number in episodes]
    raw_dir = Path(out_dir) / slugify(show.title) / "raw_llm"
    cached = sum(1 for e in eps if (raw_dir / f"episode_{e.number:03d}.json").exists())
    in_tokens = sum(len(transcript(e)) + len(prompts.EPISODE_PROMPT) + len(prompts.SYSTEM) + 1500 for e in eps) // 4
    extra = (1 if montages and len(eps) > 1 else 0) + (1 if judge else 0)
    return {"episodes": len(eps), "episode_requests": len(eps), "episode_requests_cached": cached,
            "montage_and_judge_requests": extra, "max_new_requests": len(eps) - cached + extra,
            "approx_input_tokens": in_tokens + extra * 12000,
            # rough: 10-45s per request with medium thinking, run one after another
            "approx_minutes": [round((len(eps) - cached + extra) * 10 / 60, 1), round((len(eps) - cached + extra) * 45 / 60, 1)],
            "note": "cached = an earlier raw response exists; it is reused only if prompt+model are unchanged"}
