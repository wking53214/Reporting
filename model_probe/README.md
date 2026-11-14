# model_probe: models graded against ASSAY's answer key

A test harness. Not part of the stack: nothing imports it, it imports nothing from the stack, and it never writes into
ASSAY. It sends ASSAY specimens to models from Groq, Gemini and Cloudflare Workers AI and scores each answer
mechanically against the correct answer ASSAY already records. No model grades another model.

The question it answers: when a model is asked to look at, or to restore, code whose correct answer is known in
advance, how often does it get it right, and how often does it say something the code does not support?

## The three tasks

| Task | Specimen (ASSAY `MANIFEST.md`) | The model is asked | Correct answer | Score |
|---|---|---|---|---|
| `cannot_fail` | 3.6, `failure-modes/cannot_fail/test_governance_boots.py` | for each of four test functions, CAN_FAIL or CANNOT_FAIL | CANNOT_FAIL for all four | share called CANNOT_FAIL |
| `status_claims` | 3.7, `failure-modes/status_claims/README.md` | for each of seven status labels, BACKED or UNBACKED, given a folder that holds only the README | UNBACKED for all seven | share called UNBACKED |
| `reconstruct` | 1, `pairs/` (vanguard and sre) | to restore a flattened one-line file to normal layout, changing nothing | the source itself, with only layout changed | `layout_only` (strict), `parses`, `class_cover`, `recall`, `precision` |

For `reconstruct`: `layout_only` is true when, with all whitespace removed, the answer is character for character the
source. It is the strict test. `recall` and `precision` read words only, so a changed number, operator or string
passes them; `layout_only` does not. `class_cover` is the share of the source's classes the answer still defines (ASSAY's own measure
in `MANIFEST.md` section 1); `recall` is the share of the source's words kept; `precision` is the share of the
answer's words that were in the source, so `1 - precision` is how much the model made up or changed.

## Run it

```bash
python probe.py --controls --assay ../../ASSAY                 # no network: what the scale means
read -rs -p "Groq key: " GROQ_API_KEY; export GROQ_API_KEY; echo
python probe.py --assay ../../ASSAY --provider groq --model openai/gpt-oss-120b
```

Keys come from `GROQ_API_KEY`, `GEMINI_API_KEY`, or `CLOUDFLARE_API_TOKEN` with `CLOUDFLARE_ACCOUNT_ID`, and are never
written. Each run makes a folder under `runs/` with `rows.jsonl` (digests, usage, scores) and the raw answers as text so
a person can read them. `python probe.py --rescore runs/<folder>` scores saved answers again with no model, for when the scorer is improved.
`--repeat N` runs the whole set N times, each in its own folder, to show the spread between runs.
A request refused as too large (HTTP 413, which Groq's free tier answers when the minute's token total would be
exceeded) is retried after 65 seconds, and rate limits and overload (429, 5xx) after a shorter wait. A provider error that persists (rate limit, overloaded model, token limit) is recorded as an error row and is
not scored as a wrong answer.

## What the scale means (the controls, run with no model)

| Answer | parses | class_cover | recall | precision |
|---|---|---|---|---|
| vanguard: ASSAY's own verified reconstruction | yes | 0.83 | 1.00 | 0.85 |
| sre: ASSAY's own verified reconstruction | yes | 1.00 | 0.98 | 0.46 |
| either: the flat file returned unchanged | no | 1.00 | 1.00 | 1.00 |

`class_cover` of 0.83 for vanguard and 1.00 for sre are the same figures `MANIFEST.md` records for those pairs
(5 of 6 and 11 of 11), which is the check that this scorer measures what ASSAY measures. The verified reconstructions
are themselves rewrites (ASSAY documents a rename and made thresholds configurable), so a perfect model restoring
layout only is expected to score higher on precision than they do. Returning the file unchanged keeps every word and
fails only `parses`, which is why `parses` is the first thing to read.

## Results, 2026-11-14

Run by the owner on their own machine and keys, with the scorer and prompts as committed at `501bb4a`. Counts are
runs that returned an answer; an error row (HTTP 413, 429) is left out of the count, not scored as a miss. Two earlier
Groq gpt-oss-120b runs under the old `cannot_fail` wording and the first scorer are not counted.

| Model (host) | cannot_fail, all 4 right | status_claims, all 7 right | vanguard changed layout only | vanguard changes per run | sre changed layout only |
|---|---|---|---|---|---|
| gpt-oss-120b (Groq) | 5 of 5 | 5 of 5 | 0 of 3 | 1, 5, 15 | 3 of 3 |
| gpt-oss-120b (Cloudflare) | 3 of 3 | 3 of 3 | 0 of 3 | 15, 1, 15 | 3 of 3 |
| qwen3.8-27b (Groq) | 2 of 2 | 3 of 3 | 0 of 3 | 1, 1, 1 | 2 of 2 |
| llama-3.3-70b-instruct-fp8-fast (Cloudflare) | **0 of 3** | 3 of 3 | 0 of 3 | 1, 3, 3 | 3 of 3 |

Errors left out: Groq gpt-oss had four HTTP 413 refusals before the retry was added; Qwen had two HTTP 429 refusals.

What the rows show:

- **Every model passed `status_claims`, in every run.** Seven unbacked labels were seen as unbacked each time.
- **Llama missed the same test every time.** In all three runs it scored 3 of 4 and called `test_gateway_is_called` CAN_FAIL.
  That test asserts only on a mock it has just called itself, so ASSAY's answer (CANNOT_FAIL) holds. This is a repeated
  error, not noise. The other three models never made it.
- **No model returned vanguard unchanged in layout.** All of them repaired `from __future import annotations`, which
  is damaged in the source and which ASSAY's own reconstruction also repairs. Beyond that they split:
  Qwen added nothing else in three runs. Llama sometimes put quotes around one type name (3 changes).
  gpt-oss either stopped at the repair (1 change) or reformatted fully, adding parentheses, trailing commas and
  quotes (15 changes), and did so on both hosts.
- **The 15-change list was the same on both hosts.** The first twelve changes listed were identical in three separate
  gpt-oss runs, one on Groq and two on Cloudflare. The three beyond the listing cap were not read. This points at the
  model, not the host, with three runs as the evidence.
- **sre came back with layout changed only in every run that returned it**, apart from one early Groq run that
  reworded a sentence ("calculates" to "calculate"; that run is among the uncounted early ones).
- **The word scores read 1.00 throughout**, including runs with 15 changed characters. `layout_only` is what showed them.

What it does not show: that any change altered what the code does (none listed alters a value or operator, but the
hidden three were not read), that sre is easier than vanguard (vanguard's damaged import may be the cause), or anything
about models and files other than these. Three runs per model is a small sample.

## Limits

- `layout_only` measures obedience to "change nothing", not quality. The flattened vanguard source contains
  `from __future import annotations` (the underscores were lost in the copy-paste), and ASSAY's own reconstruction
  repairs it. A model that repairs it too fails `layout_only` while doing something sensible. Read the `changes` list
  to tell a helpful repair from a silent change such as a reworded sentence.
- The `cannot_fail` question is a judgment about what "can fail" means. A test with no assertion still fails if the
  code crashes, so a careful model can answer CAN_FAIL and be defensible. The prompt now says a crash does not count;
  an earlier wording did not, and one run under it scored 2 of 4 for that reason, not clearly a model error.
- One run is one sample. Models differ run to run; repeat before comparing two models.
- A high score on 3.6 and 3.7 shows a model can see these two constructed failures. It does not show it can see
  others. These specimens say what they are in their own text, and a model may recognise them.
- Free tiers throttle large requests. The reconstruction prompts are long (10 to 16 KB in, a similar amount out), so
  expect error rows on small free-tier limits. An error row is not a model failure.
- The harness measures what a model says about code. It runs no model-written code.
