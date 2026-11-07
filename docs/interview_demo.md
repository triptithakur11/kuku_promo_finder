# Interview demo: "run it on a new show"

Kuku will hand you a new screenplay pack in the interview. This is a 5-minute script for that.
Practise it once on `tests/fixtures/odd_format_show/`, a small original show I wrote in a different
script format, so you've already seen the tool cope with an unfamiliar layout.

## 0. Before the call (2 min)
```bash
cd kuku-promo-finder && source .venv/bin/activate
python -m unittest discover -s tests          # 15 offline tests, all should pass
python server.py                              # http://localhost:8000
```
Have the UI open. In `.env`, set `PROMO_MODEL=gemini:gemini-3.6-flash` (or whatever model they provide).

## 1. Sanity-check the new input (30 s, free)
```bash
python -m promo_finder.parser path/to/new_pack.zip       # episodes, durations, line counts, warnings
python cli.py -i path/to/new_pack.zip --dry-run          # AI requests, tokens and minutes before spending anything
```
If the parser reports warnings, open `promos.md → Run log` after the run. Bad blocks are skipped and logged, not fatal.

## 2. Instant baseline, then the real run
```bash
python cli.py -i path/to/new_pack.zip --model none                       # rules only, takes seconds
python cli.py -i path/to/new_pack.zip -e 1-5 --max-calls 8               # AI on 5 episodes, capped
```
Or in the UI: drop the zip, choose a model from the dropdown, set Episodes to `1-5`, then Find promos.

**If they give you a stronger model through their API:** pick it in the dropdown, or pass
`--model compat:<model>` with `LLM_BASE_URL` and `LLM_API_KEY` set. Nothing else changes.

## 3. Review like an editor (1–2 min)
- Open the top 3. Read the script excerpt for each and say out loud why it does or doesn't work.
- Reject one with a reason (e.g. *Needs backstory*). Approve two.
- Click **Export for editing**. Show that the zip holds an EDL per promo and `cut_promos.sh`.

## 4. Close with the numbers
```bash
python eval/quality_check.py outputs/<show>/promos.json -i path/to/new_pack.zip
```
This reports hard-rule compliance, coverage, flagged picks, precision from your approve/reject clicks, and
which score separates good picks from bad ones.

## Questions to expect, and short answers
- **Why not let the LLM output timestamps directly?** It gets them roughly right, not exactly. Code snaps every
  edge to a real line, enforces 20–60s and drops what it can't fix. You'll see these in "Rejected".
- **Why blend 75% LLM with 25% rules?** One overconfident 10/10 can't carry a clip that has no hook. With the
  LLM off, the rules still rank.
- **How would you tune it?** Use the approve/reject clicks in `approvals.json`. The quality report shows which
  score actually separates approved from rejected picks. Re-weight `rank.py`, then later use ad metrics
  (3-second hold rate, CTR).
- **Cost at scale?** About 52 requests per 50-episode show. Responses are cached, so reruns are free. Episodes
  are independent, so they can run in parallel on a paid tier.
- **Where does it fail?** Clips that need backstory, quiet but powerful lines that the rules under-score, and
  continuity jumps in montages. Visuals are invisible to it, because it only reads the script.
