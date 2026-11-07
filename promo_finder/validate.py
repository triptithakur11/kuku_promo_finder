"""Promo data model + hard checks on anything the LLM (or the rules) propose.

The LLM is never trusted with timestamps: every segment is mapped back onto
real screenplay lines, snapped to line boundaries (so we never cut mid-sentence),
clamped to the episode, and the 20-60s / hook-in-3s rules are checked in code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .parser import Show, Episode, Event, fmt_ts
from .signals import PROMO_MIN, PROMO_MAX, HOOK_WINDOW, hook_score, cliff_score

SNAP_TOL = 2.5        # seconds we allow the LLM to be off before flagging
MIN_SEGMENT = 1.5


@dataclass
class Segment:
    episode: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {"episode": self.episode, "start": fmt_ts(self.start), "end": fmt_ts(self.end),
                "start_sec": round(self.start, 2), "end_sec": round(self.end, 2),
                "duration": round(self.duration, 2)}


@dataclass
class Promo:
    id: str
    kind: str                      # single | multi | montage
    title: str
    segments: list[Segment]
    hook: str = ""
    cliffhanger: str = ""
    why: str = ""
    scores: dict = field(default_factory=dict)      # LLM 1-10 scores
    context_needed: str = ""
    tropes: list[str] = field(default_factory=list)
    source: str = "llm"            # llm | rules
    rule_score: float = 0.0
    final_score: float = 0.0
    rank: int = 0
    rank_reason: str = ""
    flags: list[str] = field(default_factory=list)
    excerpt: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.segments)

    @property
    def episodes(self) -> list[int]:
        out = []
        for s in self.segments:
            if s.episode not in out:
                out.append(s.episode)
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["segments"] = [s.to_dict() for s in self.segments]
        d["duration"] = round(self.duration, 2)
        d["episodes"] = self.episodes
        return d


def parse_ts(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m2 = re.match(r"^\s*\(?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?\)?\s*$", str(v))
    if m2:
        hh, mm, ss, fr = m2.groups()
        return int(hh or 0) * 3600 + int(mm) * 60 + int(ss) + float("0." + (fr or "0"))
    try:
        return float(v)
    except ValueError:
        return None


def _nearest(values: list[float], t: float) -> float:
    return min(values, key=lambda v: abs(v - t)) if values else t


def snap_segment(ep: Episode, start: float, end: float, flags: list[str]) -> Segment | None:
    dur = ep.duration
    s, e = max(0.0, min(start, dur)), max(0.0, min(end, dur))
    if e < s:
        s, e = e, s
    content = [x for x in ep.events if x.kind != "camera"] or ep.events
    starts = sorted({x.start for x in content} | {0.0})
    ends = sorted({x.end for x in content} | {dur})
    ns, ne = _nearest(starts, s), _nearest(ends, e)
    if abs(ns - s) > SNAP_TOL or abs(ne - e) > SNAP_TOL:
        flags.append(f"ep{ep.number}: timestamps moved >{SNAP_TOL}s to fit real lines "
                     f"({fmt_ts(s)}-{fmt_ts(e)} -> {fmt_ts(ns)}-{fmt_ts(ne)})")
    s, e = ns, ne
    # never cut through a line of dialogue
    for x in ep.events:
        if x.kind == "dialogue" and x.start < s - 0.05 < x.end - 0.3:
            s = x.start
        if x.kind == "dialogue" and x.start + 0.3 < e + 0.05 < x.end:
            e = x.end
    if e - s < MIN_SEGMENT:
        flags.append(f"ep{ep.number}: dropped a {e - s:.1f}s segment")
        return None
    return Segment(ep.number, round(s, 2), round(e, 2))


def promo_events(show: Show, p: Promo, kinds=("dialogue", "action", "sfx")) -> list[Event]:
    out = []
    for seg in p.segments:
        ep = show.ep(seg.episode)
        if ep:
            out += ep.events_between(seg.start, seg.end, kinds=kinds)
    return out


def hook_event(show: Show, p: Promo) -> Event | None:
    """First non-camera beat that starts inside the first HOOK_WINDOW seconds."""
    if not p.segments:
        return None
    seg = p.segments[0]
    ep = show.ep(seg.episode)
    cands = [e for e in ep.events_between(seg.start, seg.start + HOOK_WINDOW, ("dialogue", "action", "sfx"))
             if e.start >= seg.start - 0.5]
    return max(cands, key=hook_score) if cands else None


def check_promo(show: Show, p: Promo) -> tuple[bool, str]:
    """Snap + validate in place. Returns (ok, reason_if_rejected)."""
    fixed = []
    for seg in p.segments:
        ep = show.ep(seg.episode)
        if ep is None:
            p.flags.append(f"unknown episode {seg.episode}")
            continue
        s = snap_segment(ep, seg.start, seg.end, p.flags)
        if s:
            fixed.append(s)
    merged: list[Segment] = []
    for s in fixed:
        if merged and merged[-1].episode == s.episode and s.start <= merged[-1].end + 0.3 and s.end >= merged[-1].start:
            merged[-1].end = max(merged[-1].end, s.end)
            merged[-1].start = min(merged[-1].start, s.start)
        else:
            merged.append(s)
    p.segments = merged
    if not p.segments:
        return False, "no valid segments"
    if len(p.segments) > 1 and p.kind == "single":
        p.kind = "multi" if len(p.episodes) == 1 else "montage"
    for a, b in zip(p.segments, p.segments[1:]):
        if a.episode == b.episode and b.start < a.start and p.kind != "montage":
            p.flags.append("segments out of playback order (non-linear cut)")
    d = p.duration
    if d < PROMO_MIN - 1:
        return False, f"too short ({d:.1f}s)"
    if d > PROMO_MAX + 3:
        return False, f"too long ({d:.1f}s)"
    if not (PROMO_MIN <= d <= PROMO_MAX):
        p.flags.append(f"duration {d:.1f}s slightly outside 20-60s")
    h = hook_event(show, p)
    if h is None:
        p.flags.append("no dialogue/action beat in first 3s (visual-only open)")
    last = promo_events(show, p)
    if last:
        ep = show.ep(p.segments[-1].episode)
        if cliff_score(last[-1], ep) < 0.15 and p.segments[-1].end < ep.duration - 12:
            p.flags.append("weak cut point by rules (check the ending resolves too much)")
    p.excerpt = [f"E{e.episode:02d} {fmt_ts(e.start)} {e.label()}" for e in promo_events(show, p)]
    return True, ""


def overlap(a: Promo, b: Promo) -> float:
    """Fraction of the shorter promo's footage shared with the other."""
    inter = 0.0
    for x in a.segments:
        for y in b.segments:
            if x.episode == y.episode:
                inter += max(0.0, min(x.end, y.end) - max(x.start, y.start))
    short = min(a.duration, b.duration) or 1
    return inter / short
