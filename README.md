# Reporting

Written-up analyses. Two of the four folders (`compas/` and `model_probe/`) carry code to reproduce them. The other two (`watcher_providers/` and `wrap_up_2026-11-14/`) are written records with no code in this repository.

| Folder | What it is |
|---|---|
| [`compas/`](compas/README.md) | ProPublica's public COMPAS recidivism data run through the `interconnected_zeta`, `interconnected_beta` and `interconnected_delta` pipeline, with delta's four-fifths screen checked against explicit reference groups and matched flag rates. Includes what the screen does and does not show. |
| [`model_probe/`](model_probe/README.md) | A test harness that sends ASSAY's specimens to models from Groq, Gemini and Cloudflare and scores each answer against the answer ASSAY already records. Not part of the stack. |
| [`watcher_providers/`](watcher_providers/README.md) | A live test of the Watcher's Groq, Gemini and Cloudflare narrators on one record with a trap in it, and what each model did. |
| [`wrap_up_2026-11-14/`](wrap_up_2026-11-14/README.md) | The day's work in one place: what was asked, built, reverted, learned and left open, with pointers to the evidence. |

Each folder has its own README with run instructions, results and limits.

## Role Within ≡TACK

- **What it is.** A collection of written analyses, two of them with code to reproduce them (see the top of this file), not a library and not part of the stack's runtime.
- **Authority matrix.** Evaluation, and in part policy definition, evidence generation and evidence verification, all inside its own analyses: `compas/` applies a hand-chosen rule and delta's four-fifths screen to a public dataset, and `model_probe/` scores model answers against the answers ASSAY records, saves each run, and can score saved answers again. None of this gates, enforces or authorizes anything in ≡TACK. No consumer was looked for across the library, so "nothing reads it" is INFERRED from its purpose and was not checked. It consumes other repositories (the interconnected_zeta, beta and delta packages, ASSAY's specimens, WATCHER_MCU) as inputs to its analyses.
- **Does not own.** Any of those repositories' behavior. Findings here describe one run of one analysis and are not guarantees about them.
- **Depended on by.** UNKNOWN (not inspected here).
- **Verified versus declared.** `compas/` and `model_probe/` have test suites that were run for this README (EXECUTED 2026-11-15 at `a6c77aa`, Python 3.13: `compas` 62 passed, 2 skipped, which matches its own README for a run without the cached dataset; `model_probe` 6 passed). The live model results in `model_probe/` and `watcher_providers/` were not re-run (they need provider keys that are not available here), so they are REPORTED only. `wrap_up_2026-11-14/` is a narrative and was not re-checked.
- **Pins (checked 2026-11-18).** `compas/requirements.txt` pins interconnected_delta, interconnected_zeta and interconnected_beta at commits dated 2026-09-28. They are 115, 52 and 63 commits behind those repositories today, and code changed in all three since (VERIFIED from their histories). The comment in that file saying later commits are README-only is no longer true; it sits in a non-README file and was left as it is. The example prints the same report, and its 64 tests pass, at the pins and at today's versions (EXECUTED 2026-11-18, with the dataset downloaded once).
- **Data source.** The COMPAS file is not in this repository. `compas/compas_data.py` downloads it from ProPublica's public `compas-analysis` repository on GitHub the first time the example runs, checks it against a pinned SHA-256, and caches a reduced copy that git ignores. The Apache-2.0 license here covers this repository's code and text, not that data. The source repository has no license file in its top folder (INSPECTED 2026-11-18), and the terms for reusing the data are UNKNOWN. The raw file holds personal details of real people; `compas/README.md` says how that is handled.
- **Other file.** `MOVED_Elegant_v1.md` is a pointer note: the Elegant criteria moved to the Streamline repository, and the change governor lives in the Elegant (Warden) repository.
