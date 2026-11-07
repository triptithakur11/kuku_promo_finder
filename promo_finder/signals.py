"""Cheap, deterministic signals: how 'hooky' / 'cliffhanger-y' is each event,
and rule-based candidate promo windows.

These rules do three jobs:
  1. shortlist candidates for the LLM (so it focuses on the right parts),
  2. act as a sanity score blended into the final rank,
  3. run the whole tool offline (`--model none`) when no API is available.

They are intentionally simple keyword/structure rules, tuned on genre knowledge
(slaps, reveals, betrayals, episode-ending stingers) - not on this show's answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parser import Episode, Event, fmt_ts

PROMO_MIN, PROMO_MAX = 20.0, 60.0
SWEET_MIN, SWEET_MAX = 25.0, 45.0
HOOK_WINDOW = 3.0

PHYSICAL = r"slap|strike|strikes|struck|hit|punch|crop|whip|lash|blood|bleed|wound|stab|knife|dagger|blade|sword|" \
           r"fire|flame|blaze|burn|smoke|explo|shatter|smash|crash|grab|seize|yank|shove|throw|hurl|choke|" \
           r"chain|shackle|iron|brand|kneel|kneels|kiss|collapse|faint|fall|drag|tear|rip|scream|gasp|slam|burst|" \
           r"arrest|gun|shot|poison|vial|ring|briar|thorn|mud|spit"
REVEAL = r"duke|duchess|heir|title|marry|married|marrying|wedding|wife|husband|bride|groom|betroth|engag|divorce|" \
         r"poison|witch|execut|hang|death|die|dead|alive|kill|murder|son|mother|father|sister|brother|" \
         r"pregnan|child|baby|betray|liar|lie|truth|secret|identity|disown|inherit|guilty|confess|framed|" \
         r"thief|theft|steal|stole|prison|gaol|dungeon|trial|crown|king|queen|royal|never|forever|who are you"
INTENSE_EMO = r"shout|scream|furious|fury|outrag|enrag|rage|venom|cruel|sadist|gloat|smug|menac|threat|" \
              r"horrif|shock|stun|desperat|sob|tear|chok|devastat|heartbr|panic|terrif|hyster|savage|" \
              r"seeth|livid|cold|icy|murder|contempt|disgust|mock|taunt|sneer|defian|accus|roar|bellow|snarl"
CLIFF_CUE = r"cliffhanger|ominous|sting|swell|cut to black|freeze|frozen|stunned|shock|realiz|gasp|bursts? in|" \
            r"door (?:bursts|slams|opens)|silhouette|reveal|unaware|watch(?:es|ing) from|hidden|smirk|" \
            r"to be continued|fade to black|dramatic|thunder|heartbeat|drone"
THREAT = r"\bwill\b.*\b(pay|regret|die|burn|hang|suffer|never)\b|or else|unless|until|if you|you('| wi)ll see|" \
         r"\bwait\b|\bwho\b|\bwhat\b.*\?|\bhow\b.*\?|not (?:yet|over)|this isn'?t over|mark my words"

R_PHYS, R_REV, R_EMO, R_CLIFF, R_THREAT = (re.compile(p, re.I) for p in (PHYSICAL, REVEAL, INTENSE_EMO, CLIFF_CUE, THREAT))


def _hits(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text or ""))


def hook_score(e: Event) -> float:
    """0..1: would this event stop a thumb in the first 3 seconds?"""
    t = e.text or ""
    s = 0.0
    if e.kind == "dialogue":
        s += 0.25
        s += min(0.30, 0.15 * _hits(R_EMO, e.emotion))
        s += min(0.30, 0.12 * _hits(R_REV, t))
        s += 0.10 if "!" in t else 0.0
        s += 0.05 if "?" in t else 0.0
        words = len(t.split())
        s += 0.10 if 2 <= words <= 10 else (-0.10 if words > 25 else 0.0)
    elif e.kind in ("action", "sfx"):
        s += 0.15
        s += min(0.45, 0.15 * _hits(R_PHYS, t))
        s += min(0.20, 0.10 * _hits(R_EMO, t))
    elif e.kind == "camera":
        s += min(0.25, 0.08 * _hits(R_PHYS, t))  # camera alone is a weak hook
    return max(0.0, min(1.0, s))


def cliff_score(e: Event, ep: Episode) -> float:
    """0..1: is this a good place to cut and leave the viewer hanging?"""
    t = e.text or ""
    s = 0.0
    s += min(0.40, 0.15 * _hits(R_CLIFF, t))
    if e.kind == "dialogue":
        s += 0.20 if "?" in t else 0.0
        s += 0.20 if R_THREAT.search(t) else 0.0
        s += min(0.20, 0.07 * _hits(R_REV, t))
        s += 0.10 if t.rstrip().endswith(("...", "…", "—", "-")) else 0.0
    if e.kind == "sfx":
        s += 0.10
    # Microdramas are written to end every episode on a stinger.
    dur = ep.duration
    if dur and e.end >= dur - 12:
        s += 0.35
    return max(0.0, min(1.0, s))


@dataclass
class Candidate:
    episode: int
    start: float
    end: float
    hook_event: Event
    cliff_event: Event
    hook: float
    cliff: float
    intensity: float
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def short(self) -> str:
        return (f"Ep{self.episode} {fmt_ts(self.start)}-{fmt_ts(self.end)} ({self.duration:.0f}s) "
                f"score={self.score:.2f} hook=\"{self.hook_event.label()[:80]}\" "
                f"end=\"{self.cliff_event.label()[:80]}\"")


def _content(ep: Episode) -> list[Event]:
    return [e for e in ep.events if e.kind in ("dialogue", "action", "sfx")]


def window_intensity(ep: Episode, start: float, end: float) -> float:
    evs = ep.events_between(start, end, kinds=("dialogue", "action", "sfx"))
    if not evs:
        return 0.0
    return sum(hook_score(e) for e in evs) / len(evs)


def candidate_windows(ep: Episode, top_k: int = 5) -> list[Candidate]:
    content = _content(ep)
    if not content:
        return []
    hooks = sorted(content, key=hook_score, reverse=True)[:15]
    ends = [e for e in content if cliff_score(e, ep) >= 0.25] or content[-3:]
    cands: list[Candidate] = []
    for h in hooks:
        start = h.start
        for c in ends:
            end = c.end
            dur = end - start
            if dur < PROMO_MIN or dur > PROMO_MAX:
                continue
            hs, cs = hook_score(h), cliff_score(c, ep)
            inten = window_intensity(ep, start, end)
            dur_fit = 1.0 if SWEET_MIN <= dur <= SWEET_MAX else 0.7
            # starting at a scene boundary/episode start helps the clip stand alone
            sc = ep.scene_at(start)
            fresh = 0.1 if (sc and abs(sc.start - start) < 4) or start < 4 else 0.0
            score = (0.38 * hs + 0.34 * cs + 0.18 * inten + fresh) * dur_fit
            reasons = [f"hook {hs:.2f}", f"cliff {cs:.2f}", f"intensity {inten:.2f}"]
            if fresh:
                reasons.append("starts at scene start")
            cands.append(Candidate(ep.number, start, end, h, c, hs, cs, inten, round(score, 4), reasons))
    cands.sort(key=lambda c: c.score, reverse=True)
    keep: list[Candidate] = []
    for c in cands:
        if all(_iou(c.start, c.end, k.start, k.end) < 0.4 for k in keep):
            keep.append(c)
        if len(keep) >= top_k:
            break
    return keep


def _iou(a0, a1, b0, b1) -> float:
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def top_moments(ep: Episode, k: int = 6) -> list[Event]:
    """Strongest individual beats in an episode (used to build cross-episode montages)."""
    content = _content(ep)
    scored = sorted(content, key=lambda e: max(hook_score(e), cliff_score(e, ep)), reverse=True)
    out: list[Event] = []
    for e in scored:
        if all(abs(e.start - o.start) > 6 for o in out):
            out.append(e)
        if len(out) >= k:
            break
    return sorted(out, key=lambda e: e.start)
