# Promo Finder — Kuku AI Generalist assignment, Problem 1

Reads a microdrama screenplay pack (timestamped `.txt` episodes, or a `.zip` of them) and finds the best
**20–60 second promo clips**: each opens on a hook in the first 3 seconds, ends on a cliffhanger and makes
sense to a stranger. For every promo you get the episode and start/end of each segment (in order), the hook,
the cliffhanger, one line on why it works, and a **posting order** with a reason.

An editor reviews the ranked list in a small React UI, approves the ones they like, and exports CSV/JSON.

> The input pack is Kuku's confidential content. `data/` is git-ignored. Don't commit it or publish it.

## How it works

```
screenplay .zip/.txt
   │  parser.py      regex parser → events {episode, scene, kind, speaker, emotion, start, end, text}
   ▼
   │  signals.py     cheap rules: hook score / cliffhanger score per line → candidate 20–60s windows
   ▼
   │  LLM pass 1     one request per episode: full timestamped script + rule candidates → 0–3 promos (JSON)
   │  LLM pass 2     one request: loglines + strongest beats from every episode → cross-episode montages
   ▼
   │  validate.py    code, not the LLM, owns timestamps: snap to real line boundaries, never cut mid-line,
   │                 enforce 20–60s, check a hook beat starts in the first 3s, drop/flag bad picks
   │  rank.py        75% LLM scores (hook/cliff/standalone/emotion) + 25% rule score − penalties; dedupe overlaps
   │  LLM pass 3     one "judge" request decides the posting order of the top 20 and names weak picks
   ▼
promos.json · promos.csv · promos.md · raw_llm/*.json (every prompt + unedited response)
```

If the LLM fails or is switched off, every step falls back to the rules, so the tool always gives an answer.

## Setup

```bash
cd kuku-promo-finder
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your GEMINI_API_KEY in .env
(cd web && npm install && npm run build)   # builds the React UI into web/dist
```

## Run

**Command line**

```bash
# 1. See what a run will cost BEFORE spending anything (no API calls)
python cli.py -i "path/to/pack.zip" --dry-run

# 2. Offline, rules only (free, instant)
python cli.py -i "path/to/pack.zip" --model none

# 3. Full run with the LLM, with a hard cap on requests
python cli.py -i "path/to/pack.zip" --max-calls 60

# Try a few episodes first
python cli.py -i "path/to/pack.zip" -e 1-5 --montages 0 --no-judge
```

**UI**

```bash
python server.py              # open http://localhost:8000
# for UI development with hot reload: (cd web && npm run dev) → http://localhost:5173
```

Upload the zip, pick a model from the dropdown (or **Rules only**), press **Find promos**. Then review each
card and **Approve** it or **Reject** it with a reason, and export. Recent runs are listed on the home page.
`/?run=<show-slug>` opens a saved run directly.

**Quality report**

```bash
python eval/quality_check.py outputs/<show-slug>/promos.json -i "path/to/pack.zip" [--labels eval/labels.csv]
```

## Handing promos to editors

**Export for editing** (in the UI, or on the command line) produces a zip containing:
- `edl/*.edl`: one CMX3600 edit list per promo. Import it into **Premiere Pro** (File > Import) or
  **DaVinci Resolve** (File > Import > Timeline). Each segment is linked to its episode file, with the hook and
  cliffhanger written as comments.
- `cut_promos.sh`: an ffmpeg script that cuts each promo and joins its segments into an .mp4:
  `VIDEO_DIR=/path/to/episodes ./cut_promos.sh`. This was tested on generated videos: a two-segment promo
  (29.5s + 9.5s) came out at exactly 39.0s.
- `promos.csv` and a `README.txt`.

```bash
python -m promo_finder.export outputs/<show-slug>/promos.json --approved-only --fps 30 \
    --video-pattern "episode-{ep:03d}.mp4"
```

## Editor decisions become data

Approve/Reject clicks, with reasons such as *Needs backstory*, *Weak hook* or *Ending resolves too much*,
are saved to `outputs/<show-slug>/approvals.json`. They aren't stored in the browser. `eval/quality_check.py`
turns them into:
- the precision of all picks, and of the top 10,
- the most common reasons picks were rejected,
- a table showing **which score actually separates approved from rejected picks**, which is the evidence for
  re-weighting `rank.py`. Over time it could be fed real ad metrics such as 3-second hold rate.

## Tests

```bash
python -m unittest discover -s tests -v      # 15 offline tests, no API calls, about 4s
```

The tests cover:
- the parser on an **unseen script format** (`tests/fixtures/odd_format_show/`, an original two-episode show
  using HH:MM:SS timecodes, plain labels, `-->` and bracket timestamps, a block with no time, and reversed times),
- junk input that must not crash,
- timestamp snapping and rejection of bad picks,
- the full pipeline in rules mode and with a fake LLM, including the cache and the request budget,
- the EDL and zip export,
- saving and analysing editor decisions.

See `docs/interview_demo.md` for a 5-minute "run it on a new show" script.

## Swapping the model

The model is a single `provider:model` string, given by `--model`, `PROMO_MODEL` in `.env`, or the UI field.

| provider | example | key |
|---|---|---|
| Gemini (default, Interactions API) | `gemini:gemini-3.8-flash` | `GEMINI_API_KEY` |
| Groq | `groq:llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| OpenRouter | `openrouter:<model>` | `OPENROUTER_API_KEY` |
| Ollama (local) | `ollama:llama3.1` | none |
| OpenAI | `openai:gpt-4o-mini` | `OPENAI_API_KEY` |
| Anthropic | `anthropic:<model>` | `ANTHROPIC_API_KEY` |
| any OpenAI-compatible API | `compat:<model>` | `LLM_BASE_URL`, `LLM_API_KEY` |
| no LLM | `none` | none |

Adding a provider means writing one `_call()` method in `promo_finder/llm.py`. Prompts live in `promo_finder/prompts.py`.

**Gemini specifics.** If the configured model times out or is unavailable, the tool switches once to the next
model in `GEMINI_FALLBACK_MODELS` (default `gemini-3.6-flash,gemini-3.1-flash-lite`) and keeps using that model
for the rest of the run. During development `gemini-3.8-flash` was returning 504s while 3.6 Flash answered in
about 3 seconds. `GEMINI_THINKING` (minimal/low/medium/high) sets reasoning depth.

## Cost and protecting a limited key

- A full 50-episode run makes **52 requests**: 50 episodes, 1 montage pass and 1 judge pass. That's about
  **180K input tokens** plus output. `--dry-run` prints the exact count.
- Responses are cached in `raw_llm/`. A rerun with the same prompt and model costs **0 requests**.
- Only rate-limit errors (429) are retried, at most twice. Timeouts aren't retried blindly.
- `--max-calls N` / `PROMO_MAX_CALLS` sets a hard budget. Past it, episodes fall back to rules and the log says so.
- `PROMO_RPM` throttles requests per minute (9 by default for Gemini's free tier).

## Outputs

`outputs/<show-slug>/`
- `promos.md`: ranked promos for a human to read, each with its script excerpt, flags, rejected picks and run log
- `promos.csv`: one row per promo, for the editor's sheet
- `promos.json`: everything, machine-readable
- `raw_llm/*.json`: every prompt and the **unedited** model response (the "raw outputs")
- `approvals.json`: editor decisions from the UI
- `quality.md`: written by `eval/quality_check.py`

`outputs/baseline_rules/` holds the rules-only run on the full pack, kept for comparison.

## Assumptions

See `docs/solution.md`. In short: the screenplay timestamps match the final cut. A promo can join segments
from several episodes. The ranking assumes the promos are acquisition ads aimed at strangers, so picks that
need backstory score lower and picks from early episodes get a small bonus, because a new viewer starts at
episode 1. The hook has to be an actual line or action, not only a camera move.

## Project layout

```
promo_finder/  parser.py signals.py llm.py prompts.py pipeline.py validate.py rank.py report.py
               export.py (EDL + ffmpeg)  feedback.py (approve/reject → labelled data)
cli.py         command line
server.py      FastAPI: /api/estimate, /api/run, /api/jobs/{id}, /api/runs, /api/decisions, /api/feedback,
               /api/export, /api/csv; serves web/dist
web/           React (Vite) UI: src/App.jsx, src/components/{Home,Running,Results,PromoCard,ModelSelect}.jsx
eval/          quality_check.py, labels.csv (optional extra labels)
tests/         test_promo_finder.py, fixtures/odd_format_show (an original show, not Kuku content)
docs/          solution.md (2-page write-up, export to PDF), interview_demo.md
```
