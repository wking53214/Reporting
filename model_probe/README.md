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
A provider error (rate limit, overloaded model, token limit) is recorded as an error row and is
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
