"""Tiny API + static file server for the JS UI.

    python server.py            # http://localhost:8000

Runs are background jobs (an LLM run over 50 episodes takes minutes on a free
tier), so the UI starts a job and polls its progress.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

import sys

from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(line_buffering=True)  # show provider notices in the log immediately

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import PlainTextResponse, Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from promo_finder.llm import DEFAULT_MODEL  # noqa: E402
from promo_finder.parser import load_show_from_bytes  # noqa: E402
from promo_finder.pipeline import run, estimate  # noqa: E402
from promo_finder.report import write_all, to_csv  # noqa: E402
from promo_finder.export import build_zip, DEFAULT_PATTERN  # noqa: E402
from promo_finder.feedback import load_approvals, save_decision, analyse  # noqa: E402

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
WEB = ROOT / "web" / "dist"   # built React app (cd web && npm run build)

app = FastAPI(title="Promo Finder")
# The UI on Vercel calls this API from another origin, e.g. ALLOWED_ORIGINS=https://promo-finder.vercel.app
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Content-Disposition"])
JOBS: dict[str, dict] = {}


def parse_range(s: str):
    if not s.strip():
        return None
    out = []
    for part in s.split(","):
        a, _, b = part.strip().partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


@app.get("/api/config")
def config():
    # Which providers have a key configured (booleans only - key values never leave the server).
    keys = {
        "gemini": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "ollama": True,
        "none": True,
    }
    return {"default_model": DEFAULT_MODEL, "keys": keys}


@app.post("/api/estimate")
async def estimate_run(file: UploadFile = File(...), model: str = Form(DEFAULT_MODEL), episodes: str = Form(""),
                       montages: int = Form(4), judge: bool = Form(True)):
    """Read the upload and say what a run would involve - no LLM calls."""
    try:
        show = load_show_from_bytes(await file.read(), file.filename or "upload.zip")
        eps = parse_range(episodes)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(400, f"Could not read input: {ex}")
    found = [e for e in show.episodes if e.events]
    if not found:
        raise HTTPException(400, "No timestamped episodes found in that file.")
    est = estimate(show=show, out_dir=OUT, episodes=eps, montages=montages, judge=judge)
    uses_llm = model.strip().lower() not in ("", "none", "rules", "offline")
    return {"show": show.title, "episodes_found": len(found),
            "minutes_of_footage": round(sum(e.duration for e in found) / 60, 1),
            "ai_requests": est["max_new_requests"] if uses_llm else 0, **est,
            "approx_minutes": est["approx_minutes"] if uses_llm else [0, 0]}


@app.post("/api/run")
async def start_run(file: UploadFile = File(...), model: str = Form(DEFAULT_MODEL), api_key: str = Form(""),
                    episodes: str = Form(""), montages: int = Form(4), judge: bool = Form(True)):
    data = await file.read()
    try:
        show = load_show_from_bytes(data, file.filename or "upload.zip")
        eps = parse_range(episodes)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(400, f"Could not read input: {ex}")
    if not show.episodes or not any(e.events for e in show.episodes):
        raise HTTPException(400, "No timestamped episodes found in that file.")
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {"status": "running", "progress": 0.0, "message": "Starting…", "result": None, "error": None}

    def work():
        job = JOBS[job_id]
        try:
            res = run(show=show, model=model, api_key=api_key or None, out_dir=OUT, episodes=eps,
                      montages=montages, judge=judge,
                      progress=lambda m, f: job.update(progress=f, message=m))
            out = write_all(res)
            res["slug"] = out.resolve().relative_to(OUT.resolve()).as_posix()
            res["decisions"] = load_approvals(out)
            job.update(status="done", result=res, progress=1.0)
        except Exception as ex:  # noqa: BLE001
            job.update(status="error", error=str(ex))

    threading.Thread(target=work, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")
    return JOBS[job_id]


@app.get("/api/runs")
def runs():
    out = []
    for p in sorted(OUT.rglob("promos.json"), key=os.path.getmtime, reverse=True):
        try:
            d = json.loads(p.read_text())
            out.append({"slug": p.parent.relative_to(OUT).as_posix(), "show": d["show"], "model": d["model"], "created": d["created"],
                        "kept": d["counts"]["kept"]})
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def run_dir(slug: str) -> Path:
    d = (OUT / slug).resolve()
    if OUT.resolve() not in d.parents or not (d / "promos.json").exists():
        raise HTTPException(404, "no such run")
    return d


@app.get("/api/runs/{slug:path}")
def get_run(slug: str):
    d = run_dir(slug)
    res = json.loads((d / "promos.json").read_text())
    res["slug"] = slug
    res["decisions"] = load_approvals(d)
    return res


class Decision(BaseModel):
    promo_id: str
    status: str | None = None      # approved | rejected | None to clear
    reason: str = ""


@app.post("/api/decisions/{slug:path}")
def decide(slug: str, d: Decision):
    try:
        return save_decision(run_dir(slug), d.promo_id, d.status, d.reason)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.get("/api/feedback/{slug:path}")
def feedback(slug: str):
    d = run_dir(slug)
    return analyse(json.loads((d / "promos.json").read_text())["promos"], load_approvals(d))


class ExportReq(BaseModel):
    promos: list[dict]
    fps: int = 30
    video_pattern: str = DEFAULT_PATTERN


@app.post("/api/export")
def export_edit(req: ExportReq):
    if not req.promos:
        raise HTTPException(400, "nothing to export")
    if not (12 <= req.fps <= 120):
        raise HTTPException(400, "fps must be between 12 and 120")
    try:
        req.video_pattern.format(ep=1)
    except (KeyError, IndexError, ValueError):
        raise HTTPException(400, "video file pattern must use {ep}, e.g. episode-{ep:03d}.mp4")
    return Response(build_zip(req.promos, req.fps, req.video_pattern), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=promo_edit_export.zip"})


@app.post("/api/csv")
def csv_export(promos: list[dict]):
    return PlainTextResponse(to_csv(promos), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=approved_promos.csv"})


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="ui")
else:
    @app.get("/")
    def no_ui():
        return PlainTextResponse("UI not built yet: run `cd web && npm install && npm run build`, "
                                 "or use `npm run dev` on :5173.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", 8000)))
