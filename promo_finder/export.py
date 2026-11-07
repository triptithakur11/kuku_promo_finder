"""Hand approved promos to editors in formats their tools already read.

* CMX3600 EDL per promo  -> import into Premiere Pro / DaVinci Resolve / Avid; each segment
                             becomes an event on the timeline, linked to the episode's source file.
* cut_promos.sh          -> ffmpeg script that cuts and joins each promo into an .mp4 once the
                             episode videos are available (frame-accurate re-encode).
* promos.csv / README    -> the same picks as a sheet, plus how to use the files.

    python -m promo_finder.export outputs/<show>/promos.json --approved-only --fps 30 \
        --video-pattern "episode-{ep:03d}.mp4" --out exports/

Assumption: one video file per episode whose timeline matches the screenplay timestamps.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

from .report import to_csv

DEFAULT_PATTERN = "episode-{ep:03d}.mp4"


def tc(seconds: float, fps: int) -> str:
    """Seconds -> non-drop-frame timecode HH:MM:SS:FF."""
    frames = int(max(0.0, seconds) * fps + 0.5)  # round half up (Python round() is banker's rounding)
    ff = frames % fps
    s = frames // fps
    return f"{s // 3600:02d}:{(s // 60) % 60:02d}:{s % 60:02d}:{ff:02d}"


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "promo"


def promo_name(p: dict) -> str:
    return f"{p.get('rank', 0):02d}_{p['id']}_{_slug(p.get('title') or 'promo')}"


def to_edl(p: dict, fps: int = 30, pattern: str = DEFAULT_PATTERN) -> str:
    """One promo as a CMX3600 EDL. Record timecode starts at 01:00:00:00 (broadcast convention)."""
    lines = [f"TITLE: {p['id']} {(p.get('title') or '')[:60]}".rstrip(), "FCM: NON-DROP FRAME", ""]
    rec = 3600.0
    for i, s in enumerate(p["segments"], 1):
        src_in, src_out = s["start_sec"], s["end_sec"]
        dur = src_out - src_in
        reel = f"EP{s['episode']:03d}"[:8]
        lines.append(f"{i:03d}  {reel:<8} AA/V  C        {tc(src_in, fps)} {tc(src_out, fps)} "
                     f"{tc(rec, fps)} {tc(rec + dur, fps)}")
        lines.append(f"* FROM CLIP NAME: {pattern.format(ep=s['episode'])}")
        if i == 1:
            lines.append(f"* COMMENT: HOOK - {(p.get('hook') or '')[:150]}")
        if i == len(p["segments"]):
            lines.append(f"* COMMENT: CLIFFHANGER - {(p.get('cliffhanger') or '')[:150]}")
        lines.append("")
        rec += dur
    return "\n".join(lines)


def to_ffmpeg_script(promos: list[dict], pattern: str = DEFAULT_PATTERN) -> str:
    out = [
        "#!/usr/bin/env bash",
        "# Cuts each promo from the episode videos and joins its segments into one .mp4.",
        "# Usage: VIDEO_DIR=/path/to/episodes ./cut_promos.sh      (needs ffmpeg)",
        f"# Expected file names: {pattern.format(ep=1)}, {pattern.format(ep=2)}, ...",
        "set -euo pipefail",
        'VIDEO_DIR="${VIDEO_DIR:-.}"',
        'OUT_DIR="${OUT_DIR:-promos_out}"',
        'mkdir -p "$OUT_DIR"',
        "",
    ]
    for p in promos:
        name = promo_name(p)
        out.append(f"# #{p.get('rank')} {p['id']} - {(p.get('title') or '').replace(chr(10), ' ')[:70]}")
        parts = [f"{name}_part{j}.mp4" for j in range(len(p["segments"]))]
        for part, s in zip(parts, p["segments"]):
            src = f'"$VIDEO_DIR/{pattern.format(ep=s["episode"])}"'
            out.append(f"ffmpeg -hide_banner -loglevel error -y -ss {s['start_sec']:.2f} -to {s['end_sec']:.2f} "
                       f'-i {src} -c:v libx264 -preset veryfast -crf 18 -c:a aac "$OUT_DIR/{part}"')
        if len(parts) == 1:
            out.append(f'mv "$OUT_DIR/{parts[0]}" "$OUT_DIR/{name}.mp4"')
        else:
            files = " ".join(f'"{x}"' for x in parts)
            out.append(f"printf \"file '%s'\\n\" {files} > \"$OUT_DIR/{name}_list.txt\"")
            out.append(f'(cd "$OUT_DIR" && ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 '
                       f'-i "{name}_list.txt" -c copy "{name}.mp4" && rm -f {files} "{name}_list.txt")')
        out.append(f'echo "made $OUT_DIR/{name}.mp4"')
        out.append("")
    return "\n".join(out)


README = """Promo Finder export
===================

edl/        One CMX3600 edit decision list per promo.
            Premiere Pro: File > Import > choose the .edl, then relink the media to your episode files.
            DaVinci Resolve: File > Import > Timeline > Pre-Conform EDL.
            Reel EP001 = episode 1 ({example}). Hook and cliffhanger are written as comments.
cut_promos.sh  Cuts and joins every promo with ffmpeg:
            VIDEO_DIR=/path/to/episode/videos ./cut_promos.sh
promos.csv  The same promos as a spreadsheet.

Frame rate used for timecodes: {fps} fps. Timestamps come from the screenplay, so check them against the
final cut before publishing.
"""


def build_zip(promos: list[dict], fps: int = 30, pattern: str = DEFAULT_PATTERN) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in promos:
            z.writestr(f"edl/{promo_name(p)}.edl", to_edl(p, fps, pattern))
        script = zipfile.ZipInfo("cut_promos.sh")
        script.external_attr = 0o755 << 16  # executable
        z.writestr(script, to_ffmpeg_script(promos, pattern))
        z.writestr("promos.csv", to_csv(promos))
        z.writestr("README.txt", README.format(fps=fps, example=pattern.format(ep=1)))
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export promos as EDLs + ffmpeg script")
    ap.add_argument("promos", help="outputs/<show>/promos.json")
    ap.add_argument("--approved-only", action="store_true", help="only promos approved in approvals.json")
    ap.add_argument("--ids", default="", help="comma-separated promo ids, e.g. P003,P010")
    ap.add_argument("--top", type=int, default=0, help="only the top N ranked")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--video-pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--out", default="exports")
    a = ap.parse_args(argv)

    path = Path(a.promos)
    promos = json.loads(path.read_text())["promos"]
    if a.approved_only:
        from .feedback import load_approvals
        st = load_approvals(path.parent)
        promos = [p for p in promos if st.get(p["id"], {}).get("status") == "approved"]
    if a.ids:
        want = {x.strip() for x in a.ids.split(",")}
        promos = [p for p in promos if p["id"] in want]
    if a.top:
        promos = promos[: a.top]
    if not promos:
        raise SystemExit("No promos selected.")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{path.parent.name}_edit_export.zip"
    target.write_bytes(build_zip(promos, a.fps, a.video_pattern))
    print(f"Wrote {target} ({len(promos)} promos)")


if __name__ == "__main__":
    main()
