# Watcher providers: what each model did with the same record

Record of a live test of `watcher narrate --provider` (WATCHER_MCU pull requests 13 and 14), run on 2026-11-14 by the
owner on their own machine with their own keys. The fixture is `tests/fixtures/warden_0_13_6_declined_record.json` in
WATCHER_MCU: a rejected run, 27 findings, a suite that never ran, and seven Ghost checks that were declined and so not
run (mutate, kernel, structure, tests, project, secrets, correlate), with an empty `unmeasured` list.

That last pair is the trap. A reader who sees an empty unmeasured list can conclude nothing was skipped. The
deterministic template (`--no-model`) says both. The question was whether a model account does.

## What was found

| Provider | Model | Prompt | Declined checks named as not run | Verdict words of its own | Other |
|---|---|---|---|---|---|
| Groq | openai/gpt-oss-120b | before fix | **no**: wrote "unmeasured list is empty, meaning nothing was omitted from measurement" | "confirming" on ASSAY 5 of 7 | "found no gaps" quoted from a line that also says seven checks were not run |
| Groq | openai/gpt-oss-120b | after fix | yes, all seven, in one sentence | "confirming" again | |
| Groq | qwen/qwen3.8-27b | after fix | yes, all seven, and said again that declined means not run | none seen | long account, some repetition |
| Cloudflare | @cf/openai/gpt-oss-120b | after fix | yes, all seven, one sentence each | none seen | one bold section label dropped by the oath |
| Cloudflare | @cf/meta/llama-3.3-70b-instruct-fp8-fast | after fix | yes, all seven, and wrote "does not mean that nothing was skipped" | none seen | |
| Gemini | gemini-3.8-flash, gemini-3.7-flash | after fix | **not tested**: Google returned HTTP 503 ("high demand") on every attempt | | |

"After fix" is the narrator prompt change in PR 14: name every declined check whenever the scan or the unmeasured list
is mentioned, and add no verdict word to a result.

## What this shows

1. **The oath cannot catch an incomplete account.** Every misleading sentence from the first Groq run cited a real id,
   so the oath dropped nothing (`Dropped by the oath: Nothing`). The oath checks that a sentence cites something that
   exists, not that the sentence is true or complete. A model account needs a person comparing it with the template.
2. **A prompt rule worked for the serious fault and not the small one.** Naming declined checks held on all four models
   after the fix. The "no verdict words" rule did not hold for Groq gpt-oss-120b.
3. **Cloudflare and Groq both serve gpt-oss-120b**, and both named the declined checks after the fix. Only Groq's run
   showed "confirming". One run each cannot say whether that is the provider or chance.
4. **Provider failures were reported cleanly.** A wrong key (401), a retired model (404 on Groq and Gemini, 410 on
   Cloudflare) and an overloaded model (503) each exited 3 with the status and without echoing the key.

## What this does not show

- Only the lines matching `declined|not run|omitted|confirming` were read for the Cloudflare and Qwen runs, so the rest
  of those accounts has not been reviewed. The full accounts were not saved to this repository.
- One fixture, one run per model. No repeat runs.
- Gemini produced no account at all.
- Model ids used were the ones each provider listed on the day. Several providers retired older models recently, so
  these ids will age.
- The write-up of a model's accuracy on code is a separate harness: see `../model_probe/`.
