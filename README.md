# Reporting

Written-up analyses, each with the code to reproduce it.

| Folder | What it is |
|---|---|
| [`compas/`](compas/README.md) | ProPublica's public COMPAS recidivism data run through the `interconnected_zeta`, `interconnected_beta` and `interconnected_delta` pipeline, with delta's four-fifths screen checked against explicit reference groups and matched flag rates. Includes what the screen does and does not show. |
| [`model_probe/`](model_probe/README.md) | A test harness that sends ASSAY's specimens to models from Groq, Gemini and Cloudflare and scores each answer against the answer ASSAY already records. Not part of the stack. |
| [`watcher_providers/`](watcher_providers/README.md) | A live test of the Watcher's Groq, Gemini and Cloudflare narrators on one record with a trap in it, and what each model did. |
| [`wrap_up_2026-11-14/`](wrap_up_2026-11-14/README.md) | The day's work in one place: what was asked, built, reverted, learned and left open, with pointers to the evidence. |

Each folder has its own README with run instructions, results and limits.
