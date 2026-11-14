# Wrap-up, 2026-11-14: using Groq, Gemini and Cloudflare around the stack

A record of one day's work: what was asked, what was built, what was undone, what was learned, and what is still open.
It points to the evidence; it does not repeat it. Where a claim needs a number, the number is in the folder named.

## What was asked, and the rule that came out of it

The owner has API keys for Groq, Google Gemini and Cloudflare Workers AI and asked which of their repositories could be
advanced by using them. About 50 repositories were surveyed: the opening of each README and a search for model calls, with about twenty
read further.

The answer that mattered came after the first reply: **no AI goes into the stack, except the Watcher.** The keys are for
testing and for the one repository whose job is to write a plain-words account of a run. So the work split in two.

| Kind | Where | Status |
|---|---|---|
| Permanent: the Watcher can use these providers | WATCHER_MCU | merged (PRs 13 and 14), docs in PR 15 |
| Testing only: models graded against known answers, outside the stack | Reporting (`model_probe/`, `watcher_providers/`) | merged (PR 3) |
| Undone: model adapters inside CNS | CNS | built and reverted the same day, net change zero |

## What exists now

- **WATCHER_MCU**: `watcher narrate --provider groq|gemini|cloudflare --model NAME`. One request, no retries, the same
  oath as Claude, an answer cut off at the output limit counts as an error. Two prompt rules added after the first live
  test (name every declined check; no verdict words). PR 13 (narrators), PR 14 (prompt), PR 15 (CHANGELOG and README
  ledger, open when this was written).
- **Reporting, `model_probe/`**: sends ASSAY's specimens to a model and scores each answer against the answer ASSAY
  already records, with no model as judge. It never writes into ASSAY and nothing imports it.
- **Reporting, `watcher_providers/`**: what each model did on a Watcher record with a trap in it.
- **CNS**: five commits on a working branch (four adapters, one revert) with no net difference from `main`, and the
  suite back at 2198 passing. The branch can be deleted. Nothing from it reached `main`.

## What the testing found

Detail and counts are in the two folders. In short:

1. **The oath checks that a sentence cites the record, not that the account is complete.** The first Groq account said
   an empty unmeasured list meant nothing was omitted, beside seven declined checks it never named. Every sentence cited
   a real id, so the oath dropped nothing. A prompt rule fixed that on all five models tried afterwards, but only
   in the prompt; no code enforces it.
2. **Word-level scores can read 1.00 on a changed file.** In the reconstruction task, recall and precision stayed at
   1.00 on answers with 15 changed characters (added parentheses, trailing commas, quotes). Only a strict
   whitespace-stripped comparison, `layout_only`, showed them.
3. **A repeated error is a finding; a varying answer is a sample.** Llama missed the same test in all three runs.
   gpt-oss gave an exact result in one run and a reworded sentence in another. One run proves little either way.
4. **The question can be the problem.** The first "can this test fail" prompt let a model count a crash as a way to
   fail, and one model scored 2 of 4 for a defensible reason. The prompt was fixed before any comparison was written.
5. **Provider names go stale fast.** On the day, a Groq Llama, a Cloudflare Llama and Gemini 2.5 Flash were each
   refused as retired or closed to new users, and Gemini's newest flash models returned 503 "high demand".
   A small Gemini model worked.
6. **Process, not model:** CI type-checks the tests as well as the package, so checking only the package missed two
   errors; a commit pushed after a pull request merged does not join it (PR 14 had to carry the prompt fix alone).

## What was not done

These were on the first survey and were not built. They are listed so they are not mistaken for done.

- **The harness the first plan called for.** It asked for models to be run as the code-changing tool under SWIZZLE's
  own oracles. What exists grades models against ASSAY's key instead; SWIZZLE's pipeline was not run.
- **Triad-42 on different model families**, a live semantic gate or upstream for ZTS and GSA, real embeddings for ATS,
  more jury runs in UAI-2, and a live implementation of Research's AI port. None started.
- **Code enforcement in the Watcher** (refuse an account that mentions the scan without naming the declined checks, or
  drop verdict words in the oath). The prompt rules cover the first and mostly the second; code was offered and not chosen.
- **Reading everything.** Several live runs were checked only for lines about declined checks; three of the fifteen
  changes in the gpt-oss vanguard runs were past the listing cap and were never read.
- **Gemini's larger flash models.** Not run: 503 or timeout. One small Gemini model is the whole Gemini row.

## Open items

| Item | Who | Note |
|---|---|---|
| WATCHER_MCU PR 15 (docs) | owner | Documentation only; no code or test changed |
| Delete the CNS working branch | owner | Net change zero; its history is the record of the reverted adapters |
| Read the three hidden vanguard changes | any | Raise `limit` in `scoring.changes` (no flag for it yet) and rescore a saved gpt-oss answer that had 15 changes |
| Run Gemini's larger flash models again | owner | Needs Google capacity; same two commands as the smaller model |
| Decide on code enforcement in the Watcher | owner | The README's KNOWN DEFECTS records why it matters |

## How to repeat any of it

- `model_probe/README.md`: `python probe.py --controls --assay PATH-TO-ASSAY` needs no key and shows what the scale
  means; a run needs one provider key in the environment.
- `watcher_providers/README.md`: the fixture is `tests/fixtures/warden_0_13_6_declined_record.json` in WATCHER_MCU;
  `watcher narrate FIXTURE --provider P --model M`, then compare with `--no-model`.
- Keys are read from the environment and never written by the harness or the narrators; their errors carry a status
  and not the text of the error.
