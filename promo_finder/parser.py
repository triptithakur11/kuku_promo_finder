"""Parse timestamped microdrama screenplays into structured events.

Input: a .zip, a folder of .txt files, or a single .txt file.
Each episode file looks like:

    EPISODE NUMBER: Episode 1
    EPISODE LOGLINE: ...
    SCENE 01
    Scene heading: INT. CATHEDRAL – DAY
    Scene start: 00:00.00
    **LADY JULIANA (Confused, Breathless):**
    Start: (00:13.50) | End: (00:14.30)
    "Why?"

The parser is deliberately forgiving: unknown lines are attached to the
current event's text and problems are collected as warnings, so a new show
with slightly different formatting degrades gracefully instead of crashing.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

# MM:SS(.ff) or HH:MM:SS(.ff); "." or "," before the fraction. Four groups: hours, minutes, seconds, fraction.
TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"
RE_EP_NUM = re.compile(r"^EPISODE(?:\s+NUMBER)?\s*[:#]?\s*(?:Episode\s*)?(\d+)\b", re.I)
RE_LOGLINE = re.compile(r"^EPISODE LOGLINE:\s*(.*)", re.I)
RE_CONT = re.compile(r"^CONTINUITY NOTES:\s*(.*)", re.I)
RE_SCENE = re.compile(r"^SCENE\s+(\d+)", re.I)
RE_HEADING = re.compile(r"^Scene heading:\s*(.*)", re.I)
RE_SCENE_START = re.compile(r"^Scene start:\s*" + TS, re.I)
RE_SCENE_END = re.compile(r"^Scene end:\s*" + TS, re.I)
# "**JULIANA (Angry):**"  or, without markdown, an upper-case label alone on its line: "JULIANA (Angry):"
RE_BLOCK = re.compile(r"^(?:\*\*(.+?):\*\*|([A-Z][A-Z0-9 .'’&/-]*(?:\s*\([^)]*\))*):)\s*$")
RE_TIMES = re.compile(r"^Start:\s*\(?\s*" + TS + r"\s*\)?\s*[|,;]?\s*End:\s*\(?\s*" + TS + r"\s*\)?", re.I)
# "[00:12.0 - 00:14.5]", "(00:12 – 00:14)", "00:12.00 --> 00:14.50"
RE_TIMES_ALT = re.compile(r"^[\[(]?\s*" + TS + r"\s*(?:-->|-|–|—|to)\s*" + TS + r"\s*[\])]?\s*$", re.I)
RE_FILE_EP = re.compile(r"episode[-_ ]?0*(\d+)", re.I)

NON_DIALOGUE = {"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sfx", "SFX": "sfx",
                "SOUND": "sfx", "MUSIC": "sfx", "TEXT": "text", "SUPER": "text", "TITLE": "text"}


def ts_to_sec(m: tuple) -> float:
    hh, mm, ss, frac = m
    return int(hh or 0) * 3600 + int(mm) * 60 + int(ss) + float("0." + (frac or "0"))


def fmt_ts(sec: float) -> str:
    sec = max(0.0, sec)
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:05.2f}"


@dataclass
class Event:
    episode: int
    scene: int
    idx: int                 # index within episode
    kind: str                # dialogue | action | camera | sfx | text
    start: float
    end: float
    text: str = ""
    speaker: str = ""        # dialogue only, e.g. "LADY JULIANA"
    emotion: str = ""        # dialogue only, e.g. "Outraged, Accusing"
    voice: str = ""          # O.S. / V.O.

    def label(self) -> str:
        if self.kind == "dialogue":
            emo = f" ({self.emotion})" if self.emotion else ""
            return f"{self.speaker}{emo}: {self.text}"
        return f"[{self.kind.upper()}] {self.text}"


@dataclass
class Scene:
    number: int
    heading: str = ""
    start: float = 0.0
    end: float = 0.0


@dataclass
class Episode:
    number: int
    logline: str = ""
    continuity: str = ""
    source: str = ""
    scenes: list[Scene] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        ends = [s.end for s in self.scenes] + [e.end for e in self.events]
        return max(ends) if ends else 0.0

    def events_between(self, start: float, end: float, kinds=None) -> list[Event]:
        out = [e for e in self.events if e.end > start + 1e-6 and e.start < end - 1e-6]
        if kinds:
            out = [e for e in out if e.kind in kinds]
        return out

    def scene_at(self, t: float) -> Scene | None:
        for s in self.scenes:
            if s.start - 1e-6 <= t < s.end + 1e-6:
                return s
        return self.scenes[-1] if self.scenes else None


@dataclass
class Show:
    title: str
    episodes: list[Episode]

    def ep(self, n: int) -> Episode | None:
        for e in self.episodes:
            if e.number == n:
                return e
        return None

    def to_dict(self) -> dict:
        return {"title": self.title, "episodes": [asdict(e) for e in self.episodes]}


def _parse_speaker(raw: str) -> tuple[str, str, str]:
    """'ALEXANDER (O.S.) (Gasping)' -> ('ALEXANDER', 'Gasping', 'O.S.')
    'BLOND NOBLEMAN (Rupert) (Cold)' -> ('BLOND NOBLEMAN (Rupert)', 'Cold', '')"""
    parens = re.findall(r"\(([^)]*)\)", raw)
    name = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    voice, emotion, extra = "", "", []
    for p in parens:
        if p.upper().replace(" ", "") in {"O.S.", "V.O.", "O.C.", "CONT'D", "CONT’D"}:
            voice = p
        else:
            extra.append(p)
    if extra:
        emotion = extra[-1]
        # an earlier paren that looks like a proper name is part of the speaker
        for p in extra[:-1]:
            name += f" ({p})"
    return name, emotion, voice


def parse_episode_text(text: str, source: str = "", fallback_number: int | None = None) -> Episode:
    ep = Episode(number=fallback_number or 0, source=source)
    scene_no = 0
    cur: Event | None = None
    pending: dict | None = None  # block header seen, waiting for times
    idx = 0

    def flush():
        nonlocal cur
        if cur is not None:
            cur.text = cur.text.strip().strip('"').strip("“”").strip()
            ep.events.append(cur)
        cur = None

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if m := RE_EP_NUM.match(line):
            ep.number = int(m.group(1)); continue
        if m := RE_LOGLINE.match(line):
            ep.logline = m.group(1).strip(); continue
        if m := RE_CONT.match(line):
            ep.continuity = m.group(1).strip(); continue
        if line.startswith("---"):
            continue
        if m := RE_SCENE.match(line):
            flush(); pending = None
            scene_no = int(m.group(1))
            ep.scenes.append(Scene(number=scene_no)); continue
        if ep.scenes and (m := RE_HEADING.match(line)):
            ep.scenes[-1].heading = m.group(1).strip(); continue
        if ep.scenes and (m := RE_SCENE_START.match(line)):
            ep.scenes[-1].start = ts_to_sec(m.groups()); continue
        if ep.scenes and (m := RE_SCENE_END.match(line)):
            ep.scenes[-1].end = ts_to_sec(m.groups()); continue
        if line.lower().startswith("actions and dialogue"):
            continue
        if m := RE_BLOCK.match(line):
            flush()
            label = (m.group(1) or m.group(2)).strip()
            key = label.upper()
            if key in NON_DIALOGUE:
                pending = {"kind": NON_DIALOGUE[key]}
            else:
                name, emo, voice = _parse_speaker(label)
                pending = {"kind": "dialogue", "speaker": name, "emotion": emo, "voice": voice}
            continue
        if pending is not None and (m := (RE_TIMES.match(line) or RE_TIMES_ALT.match(line))):
            g = m.groups()
            start, end = ts_to_sec(g[0:4]), ts_to_sec(g[4:8])
            if end < start:
                ep.warnings.append(f"line {line_no}: end before start, swapped")
                start, end = end, start
            cur = Event(episode=ep.number, scene=scene_no, idx=idx, start=start, end=end, **pending)
            idx += 1
            pending = None
            continue
        if cur is not None:
            cur.text += (" " if cur.text else "") + line
        elif pending is not None:
            ep.warnings.append(f"line {line_no}: block without timestamps skipped")
            pending = None

    flush()
    for e in ep.events:
        e.episode = ep.number
    for s in ep.scenes:
        evs = [e for e in ep.events if e.scene == s.number]
        if evs and s.end <= s.start:
            s.start, s.end = min(e.start for e in evs), max(e.end for e in evs)
    if not ep.events:
        ep.warnings.append("no timestamped events found")
    return ep


def _sort_key(name: str) -> int:
    m = RE_FILE_EP.search(Path(name).name)
    return int(m.group(1)) if m else 10**6


def load_show(path: str | Path, title: str | None = None) -> Show:
    """Load every episode from a .zip, a folder (recursive) or a single .txt."""
    path = Path(path)
    files: list[tuple[str, str]] = []
    if path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith(".txt") and not Path(n).name.startswith("."):
                    files.append((n, z.read(n).decode("utf-8", errors="replace")))
        title = title or _guess_title([n for n, _ in files]) or path.stem
    elif path.is_dir():
        for p in path.rglob("*.txt"):
            if not p.name.startswith("."):
                files.append((str(p), p.read_text(encoding="utf-8", errors="replace")))
        title = title or _guess_title([n for n, _ in files]) or path.name
    elif path.is_file():
        files.append((str(path), path.read_text(encoding="utf-8", errors="replace")))
        title = title or path.parent.name
    else:
        raise FileNotFoundError(path)
    return _build_show(files, title)


def load_show_from_bytes(data: bytes, filename: str, title: str | None = None) -> Show:
    files: list[tuple[str, str]] = []
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.lower().endswith(".txt") and not Path(n).name.startswith("."):
                    files.append((n, z.read(n).decode("utf-8", errors="replace")))
    else:
        files.append((filename, data.decode("utf-8", errors="replace")))
    return _build_show(files, title or _guess_title([n for n, _ in files]) or Path(filename).stem)


def _guess_title(names: list[str]) -> str | None:
    parents = {Path(n).parent.name for n in names if Path(n).parent.name}
    return parents.pop() if len(parents) == 1 else None


def _build_show(files: list[tuple[str, str]], title: str) -> Show:
    files.sort(key=lambda x: (_sort_key(x[0]), x[0]))
    eps = []
    for i, (name, text) in enumerate(files, 1):
        fb = _sort_key(name)
        ep = parse_episode_text(text, source=name, fallback_number=fb if fb < 10**6 else i)
        eps.append(ep)
    eps.sort(key=lambda e: e.number)
    return Show(title=title, episodes=eps)


if __name__ == "__main__":
    import sys
    show = load_show(sys.argv[1])
    print(show.title, len(show.episodes), "episodes")
    for e in show.episodes:
        kinds = {}
        for ev in e.events:
            kinds[ev.kind] = kinds.get(ev.kind, 0) + 1
        print(f"Ep{e.number:>3} {fmt_ts(e.duration)} scenes={len(e.scenes)} {kinds} warn={len(e.warnings)}")
