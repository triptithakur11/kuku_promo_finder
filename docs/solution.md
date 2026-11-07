# Promo Finder: Kuku AI Generalist assignment, Problem 1

**Name / Roll no / Branch:** _fill in_ · **Prototype:** _GitHub link_ · **Raw outputs:** `outputs/` · **Video:** _optional link_

> DRAFT. Replace every `[[…]]` with numbers and examples from **your** full Gemini run and your own
> spot-check. The decisions in here should be ones you can defend in the interview.

## 1. Why Problem 1
Promos are the paid-acquisition engine for microdrama, and Kuku releases new shows every week. Today an
editor watches every episode to pick moments. The input is structured (every line is timestamped) and the
output can be checked (timestamps, durations, hook, cliffhanger), so I could build something real in
2–3 hours that an editor would use the next day. I scoped it to *finding and ranking* promos. Editing is out
of scope, as the brief says.

## 2. Assumptions (the brief was silent on these)
- Screenplay timestamps match the final cut, so a script timestamp is a video timestamp.
- The promos are **acquisition** ads for strangers. "Makes sense alone" and "the promise pays off early" outweigh
  raw drama. Picks from episodes 1–10 get a small ranking bonus, because the viewer lands on episode 1.
- The hook must be a line, action or sound. A camera move alone doesn't count. "First 3 seconds" is checked
  against line start times.
- Promos may join segments, and the segments can come from different episodes (montages). Montages are built
  only from pre-cut "beats" that the code extracted, so the LLM can't invent footage.
- Cutting mid-line is never acceptable. Segment edges snap to line boundaries.
- Spoilers (for example "he is secretly the Duke") are fine. That reveal *is* the genre's selling point.

## 3. How it works: what goes to AI and what stays code
| Step | Who | Why |
|---|---|---|
| Parse script → timestamped events | **code** (regex) | deterministic, free, tolerant of format drift |
| Hook / cliffhanger keyword scores, candidate windows | **code** (rules) | cheap shortlist, sanity check, offline fallback |
| Pick 0–3 promos per episode, write hook/cliffhanger/why, score 1–10 | **LLM** (1 request/episode) | needs understanding of meaning, tone and standalone-ness |
| Cross-episode montages from pre-cut beats | **LLM** (1 request) | needs a story-level view |
| Timestamp snapping, 20–60s, hook-in-3s, dedupe | **code** | the LLM is never trusted with numbers |
| Final score = 75% LLM + 25% rules − penalties | **code** | one inflated "10/10" can't carry a clip that has no hook |
| Posting order for the top 20 plus "weak pick" call-outs | **LLM judge** (1 request) | variety and launch strategy |
| Approve / reject (with a reason) before anything is posted | **human** (UI) | the editor stays accountable, and every click becomes labelled data |
| Export to EDL (Premiere/Resolve) and an ffmpeg cut script | **code** | fits the editor's existing tools |

The model is one string (`gemini:gemini-3.8-flash`, `groq:…`, `ollama:…`, `anthropic:…`, `none`). Prompts are in
one file. Every prompt and its unedited response is saved to `raw_llm/`, which also serves as a cache.

## 4. Results on the input pack (50 episodes)
- Run: `[[model actually used]]`, `[[N]]` requests, `[[time]]`. Kept `[[k]]` promos, rejected `[[r]]` (reasons in `promos.md`).
- Top 5 to post first, and why: `[[paste from promos.md ranking table, 1 line each]]`
- Rules-only baseline (`outputs/baseline_rules/`): 82 promos, all 20–60s. Readable, but it ranks clips that
  need context (#1 is a thug shouting "Get out of the way!" in Ep15) and puts the Ep24 riding-crop slap at the
  *end* of a clip instead of using it as the hook. This gap is why the LLM pass exists.

## 5. How I know it's good, and where it fails
**Automatic checks** (`eval/quality_check.py` → `quality.md`): % of promos at 20–60s, a strong hook beat in
the first 3s, an ending on a cliffhanger cue, episode coverage, overlap with the rule shortlist, and
standalone risk (≥5 speakers to track). `[[paste numbers]]`.
*Caveat:* these checks reuse my own rules, so they are partly circular. They catch broken picks. They don't
prove good ones.

**Human review:** I approved or rejected the top `[[10–15]]` in the UI, giving a reason for each reject.
Precision: `[[x%]]` overall and `[[y%]]` in the top 10. Most common reject reason: `[[…]]`. The quality report
also shows which score best separates approved from rejected picks (`[[e.g. standalone]]`), which tells me how to re-weight.
**Blind gold set:** before looking at the output, I picked my own promos for episodes `[[1–5]]`. The tool found
`[[k of n]]` of mine.
**Robustness:** 15 offline tests, including an original show in a different script format (HH:MM:SS timecodes,
no markdown, broken blocks). It parses, logs warnings and still produces promos.

**Where it picks badly** (fill in real examples from your run):
- Clips that assume backstory: late-episode villains, side characters (Prudence, Father Thomas). `[[example]]`
- The rules over-reward shouting and question marks, and under-reward quiet but devastating lines.
- Montages can join beats with costume or continuity jumps that look odd on screen. The script doesn't show this.
- Everything depends on the script matching the cut. Real footage could differ (trims, reshoots).
- I can't judge visuals. A great slap with a weak line can lose to a strong line in a dull shot.

## 6. Scale and cost (every show, every week)
- About 52 requests per 50-episode show (one per episode, plus montage and judge passes) and about 180K input tokens.
  That is within Gemini's free tier for a few shows. On a paid Flash-class model it costs cents per show
  (`[[check current price]]`). Episodes are independent, so they can run in parallel. Cached reruns are free.
- Built-in guards: `--dry-run` shows the cost before you spend, `--max-calls` sets a hard budget, only rate
  limits are retried, and the tool falls back to a working model once if the primary times out.
- Next steps: 1) feed back real ad metrics (3-second hold rate, CTR, installs) to tune the score weights;
  2) add a vision model on the actual video to check the visual hook and the cut points;
  3) set up a per-show style config (tropes, banned spoilers); 4) let the approve/reject clicks become labelled data.

## 7. AI tools I used, and where they got it wrong
I used Claude Code (Opus) to scaffold the parser, pipeline, React UI and docs. I made the scoping, assumption,
weighting and ranking decisions myself and reviewed the code. Where the AI was wrong:
- It first targeted `gemini-2.5-flash`. The API returned **404, no longer available to new users**, because the
  assistant's knowledge of current models was out of date. I switched to Gemini 3.x through the Interactions API.
- It sent `response_mime_type` to the Interactions API, which rejected it (**400: needs `response_format`**).
- `gemini-3.8-flash` kept returning **504 timeouts**. The first retry logic stacked 5 retries on top of a
  3-model fallback, so **one episode could burn about 15 requests** on my limited key. I caught this, capped
  retries to rate limits only, and added `--dry-run` and `--max-calls`.
- `[[one example of the LLM picking a bad promo, from your run]]`
