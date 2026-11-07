"""Scoring, de-duplication and ranking.

final_score blends (a) the LLM's judgement and (b) the deterministic rule score,
so one hallucinated '10/10' can't push a clip with no hook to the top, and so
the ranking still works with the LLM switched off.
"""
from __future__ import annotations

from .parser import Show
from .signals import hook_score, cliff_score, window_intensity, SWEET_MIN, SWEET_MAX
from .validate import Promo, promo_events, hook_event, overlap

W_LLM = {"hook": 0.30, "cliffhanger": 0.30, "standalone": 0.25, "emotion": 0.15}
LLM_WEIGHT = 0.75
DUP_OVERLAP = 0.5


def rule_score(show: Show, p: Promo) -> float:
    evs = promo_events(show, p)
    if not evs:
        return 0.0
    h = hook_event(show, p)
    hs = hook_score(h) if h else 0.0
    last_ep = show.ep(p.segments[-1].episode)
    cs = max(cliff_score(e, last_ep) for e in evs[-2:])
    inten = sum(window_intensity(show.ep(s.episode), s.start, s.end) * s.duration for s in p.segments) / max(p.duration, 1)
    return round(0.4 * hs + 0.4 * cs + 0.2 * inten, 4)


def llm_score(p: Promo) -> float | None:
    if not p.scores:
        return None
    tot = 0.0
    for k, w in W_LLM.items():
        try:
            v = float(p.scores.get(k, 5))
        except (TypeError, ValueError):
            v = 5.0
        tot += w * max(0.0, min(10.0, v)) / 10
    return tot


def score(show: Show, p: Promo) -> float:
    p.rule_score = rule_score(show, p)
    ls = llm_score(p)
    s = p.rule_score if ls is None else LLM_WEIGHT * ls + (1 - LLM_WEIGHT) * p.rule_score
    if p.context_needed and p.context_needed.strip().lower() not in ("", "none", "n/a"):
        s -= 0.04
    s -= 0.03 * len(p.flags)  # every validation warning costs a little
    if not (SWEET_MIN <= p.duration <= SWEET_MAX):
        s -= 0.02
    # Assumption: an ad's promise should pay off soon after a new viewer starts at episode 1.
    first_ep = min(p.episodes) if p.episodes else 99
    if first_ep <= 10:
        s += 0.03
    p.final_score = round(s, 4)
    return p.final_score


def dedupe(promos: list[Promo]) -> tuple[list[Promo], list[tuple[Promo, str]]]:
    keep, dropped = [], []
    for p in sorted(promos, key=lambda x: x.final_score, reverse=True):
        dup = next((k for k in keep if overlap(p, k) >= DUP_OVERLAP), None)
        if dup:
            dropped.append((p, f"duplicate of {dup.id} ({overlap(p, dup):.0%} shared footage)"))
        else:
            keep.append(p)
    return keep, dropped


def apply_order(promos: list[Promo], order: list[dict] | None, weak: list[dict] | None) -> list[Promo]:
    """Put judge-ordered promos first (in judge order), then the rest by score."""
    by_id = {p.id: p for p in promos}
    for w in weak or []:
        p = by_id.get(str(w.get("id", "")))
        if p:
            p.flags.append(f"judge: {w.get('problem', 'weak')}")
    ranked, seen = [], set()
    for o in order or []:
        p = by_id.get(str(o.get("id", "")))
        if p and p.id not in seen:
            p.rank_reason = o.get("reason", "")
            ranked.append(p)
            seen.add(p.id)
    rest = sorted((p for p in promos if p.id not in seen), key=lambda x: x.final_score, reverse=True)
    out = ranked + rest
    for i, p in enumerate(out, 1):
        p.rank = i
        if not p.rank_reason:
            p.rank_reason = f"score {p.final_score:.2f}"
    return out
