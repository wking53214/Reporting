# COMPAS example: a real outcome-labelled cohort through delta

This runs ProPublica's public COMPAS recidivism data (6,172 defendants after
their published filter) through the pipeline in `interconnected_zeta`,
`interconnected_beta` and `interconnected_delta` (Keys and Locks, then
Decisions, then delta's ledger, outcome obligations and four-fifths screen).

It compares two systems on the same people:

- **a simple rule:** flag for review when 2 or more of 4 recorded
  criminal-history factors are present (4+ priors, any juvenile record, a
  felony charge, age under 25). It never sees race or COMPAS's own score;
- **COMPAS's own classification:** a score text of "Low" is the favorable outcome.

COMPAS is a well-known public benchmark here, not a target domain. This is a
worked example of what delta's screen does and does not tell you, not a
validated pretrial risk tool. The rule's thresholds are judgment calls.

**On the word "outcome".** The dataset's `two_year_recid` column records whether
a person was charged again within two years. That is an arrest-based record, not
a proven offence, and it can itself differ by group. This README says
"re-charged" for that reason. Delta asks for a provenance class (verified,
attested or estimated) whenever an outcome is resolved. This example stamps
`PROVENANCE_VERIFIED` because the value comes from the dataset's recorded column;
that is a choice made here, and nothing else about the outcome is checked.

**A warning about the outcome that changes some numbers.** The file holds
screenings from 2013 and 2014, but follow-up stopped around April 2016. People
screened from 2014-04-01 on (875 of the 6,172 rows) could not have been followed
for two full years, and in this file 99.7% of them are people who *were*
re-charged: they appear to be in the file because of the outcome. Re-charge rates
that include them are biased upward. This README therefore shows re-charge rates
on the **complete-follow-up** rows (5,297) first and the full file second. Results
that do not read the outcome (section 1) are unaffected.

## Run it

```bash
pip install --no-deps -r compas/requirements.txt   # pinned delta, zeta, beta
pip install pytest                                  # only to run the tests
python compas/run_compas_audit.py
python -m pytest compas/tests
```

`--no-deps` is deliberate: delta and beta declare unpinned git dependencies on
each other that pip cannot reconcile with the pins, and the three packages need
nothing else.

With the dataset cached (run the example once first), the tests give 64 passed.
Without it, 62 pass and the two tests that need the real file are reported as
skipped.
The pipeline tests import delta, zeta and beta and fail to import, rather than
skip, if they are missing.

## The data, and personal information

The raw file lists real defendants with names, dates of birth, case numbers and
jail dates. This code never writes any of that to disk:

- the raw file is downloaded into memory from ProPublica's public repository and
  checked against a pinned SHA-256, so a changed upstream file cannot silently
  change the results;
- only the columns the audit reads are kept, and only that minimized copy
  (about 400 KB) is cached under `compas/data/`, with owner-only permissions. The
  directory is git-ignored. The cache is checked against its own pinned hash each
  time it is read. The screening date is read once to work out whether a person
  could have been followed for two years (`full_followup`); the date itself is
  not kept;
- the raw bytes are never saved.

## What the run shows

### 0. Check the published error rates on the right subset

ProPublica's published error rates are computed on all 7,214 raw rows. On those
rows this example reproduces them to the whole percent the article reports. On the
6,172 filtered rows the same rates come out different, and that is expected, not
an error.

| | African-American | Caucasian | Published (whole %) |
|---|---|---|---|
| False positive rate, 7,214 rows | 44.8% | 23.5% | 45 / 23 |
| False negative rate, 7,214 rows | 28.0% | 47.7% | 28 / 48 |
| False positive rate, 6,172 rows | 42.3% | 22.0% | |
| False negative rate, 6,172 rows | 28.5% | 49.6% | |
| False positive rate, 5,297 rows with complete follow-up | 42.4% | 22.0% | |
| False negative rate, 5,297 rows with complete follow-up | 28.4% | 50.4% | |

A false positive here means not re-charged within two years but scored Medium or
High; a false negative means re-charged but scored Low. Restricting to complete
follow-up barely moves the error rates (the largest change is 0.8 points, in the
Caucasian false negative rate).

**Follow-up completeness.** This is the check behind the warning above:

| Screened | Rows | Re-charged within two years |
|---|---|---|
| Before 2014-04-01 (complete follow-up) | 5,297 | 36.6% |
| From 2014-04-01 on (follow-up cut short) | 875 | 99.7% |

The jump is not a change in behaviour. Follow-up ended, and the pattern suggests
that rows without a re-charge are mostly missing from the file after that date.

### 1. Decision disparate impact (the four-fifths screen)

The four-fifths rule comes from US employment-selection guidance (the EEOC
Uniform Guidelines, 29 CFR 1607.4(D)): a group whose favorable rate is under 80%
of the highest group's is a signal of adverse impact, and the guideline itself
cautions that differences based on small numbers may not be statistically
significant. Here favorable means "not flagged" (the rule) or "scored Low" (COMPAS).

**1a. The screen exactly as delta ships it.** It compares every group to the
highest-rate group, and which group that is can change between systems:

| | Reference group (highest rate) | African-American ratio |
|---|---|---|
| This rule | Asian, n=31 | 0.61 |
| COMPAS | Other, n=343 | 0.53 |

For the rule, the reference is a group of 31, so that ratio rests on a very small
sample. For COMPAS the reference is a group of 343, a legitimately sized
comparison. The two figures are therefore not measured against the same group and
should not be set side by side. Delta's screen refuses cohorts under 30 in total
and drops groups with under 1.0 effective weight (essentially none), but has no
size floor per group, which is why an 11-person group can appear in its output.
Delta's docstring says the function was extracted from `sentinel_os`, so
changing it is a separate decision; this example leaves it alone and reports 1b
beside it.

**1b. Against one explicit reference group, with uncertainty.** Using Caucasian
defendants as the reference (a choice: it is the largest comparison group, not
the only defensible one), with a 95% interval:

| Group | n | This rule: ratio (interval) | COMPAS: ratio (interval) |
|---|---|---|---|
| African-American | 3,175 | **0.69** (0.66 to 0.73) | **0.63** (0.60 to 0.67) |
| Hispanic | 509 | 0.98 (0.92 to 1.04) | 1.08 (1.02 to 1.15) |
| Other | 343 | 1.03 (0.96 to 1.11) | 1.19 (1.12 to 1.27) |
| Asian | 31 | not interpreted (n under 100) | not interpreted |
| Native American | 11 | not interpreted (n under 100) | not interpreted |

Both systems fall below 0.8 for African-American defendants under either
reference choice (0.69 and 0.63 here; 0.61 and 0.53 in 1a), and in 1b the whole
interval sits below 0.8, so that is not sampling noise. The reference row has no
interval, because its ratio to itself is exactly 1. The minimum group size of 100
is this example's own choice, not a legal standard.

**1c. Comparing the two systems fairly.** The systems do not flag the same share
of people (the rule leaves 60.2% unflagged, COMPAS's "Low" leaves 55.4%), and a
ratio moves with where the cut is placed. A fairer comparison than raw rates is at
the same unflagged share. A `*` marks a cut the system really produces; an
unmarked value is a hypothetical, an expected value over a random split of the
people sitting exactly on the boundary:

| Unflagged share | This rule | COMPAS |
|---|---|---|
| 55.4% | 0.684 | 0.634 * |
| 60.2% | 0.695 * | 0.663 |
| 65.0% | 0.739 | 0.689 |
| 70.0% | 0.780 | 0.723 |
| 90.0% | 0.910 * | 0.900 |

At matched rates the rule is a little more even than COMPAS (by 0.01 to 0.06), and
both are under 0.8 at every share shown up to 70% (they pass at 90%). The
difference between the two systems has not been tested for significance.
"Measurably less discriminatory than COMPAS" is not supported by this run.

A rule can pass the screen by flagging almost nobody: the 90% row passes because
only 10% of people are flagged. The ratio is only meaningful alongside the share
flagged.

### 2. Outcome calibration

Read back from delta's resolved obligations (the script checks that what comes back
equals what was recorded). Within the same decision, were people re-charged at
different rates by race? On the **complete-follow-up** rows (the clean comparison):

| Decision | African-American re-charged | Caucasian re-charged | Gap |
|---|---|---|---|
| Standard monitoring | 30.3% (n=1,395) | 24.3% (n=1,345) | 5.9 points |
| Flag for review | 57.9% (n=1,282) | 45.8% (n=483) | 12.1 points |

On every row, including the truncated follow-up, the same table reads 38.1% and
32.1% (gap 6.0) for standard monitoring and 66.3% and 56.5% (gap 9.8) for flag for
review. Those figures are inflated by the 875 selected rows, and the flagged
bucket's gap is understated there (9.8 against 12.1).

On the complete-follow-up rows, 43.5% of African-American and 30.0% of Caucasian
defendants were re-charged within two years, so the groups' base rates differ.
With different base rates and an imperfect classifier, equal calibration and equal
error rates cannot both hold. That is a statement about what can be achieved
together; it does not by itself explain or excuse a gap of this size, and it does
not say which fairness measure a system should satisfy. Test 1 and test 2 ask
different questions, and both can fail together.

## Limits

- **Arrest-based records.** Priors, juvenile records, charge degree and the
  re-charge outcome all come from arrests and charging. They can reflect
  differences in policing and charging, so a gap here is not by itself evidence
  about behaviour or about intent. "Recorded", not "objective", is the right word
  for the rule's inputs.
- **Selected follow-up.** The 875 rows screened from 2014-04-01 on are almost all
  re-charged people, which biases any re-charge rate computed on the full file.
  The cut date is this example's reading of the data (the jump is unmistakable in
  the monthly rates), not a documented ProPublica rule.
- The four-fifths rule is a screening signal, not a legal finding.
- The rule's thresholds were chosen by hand and are not validated against the
  pretrial-risk literature.
- Decision timestamps in the ledger are synthetic (one minute apart). Screening
  dates are used only to derive the follow-up flag and are not kept.
- One jurisdiction's records from 2013 and 2014 only.
- COMPAS's own score is used only as the comparison, never as an input.

## Files

- `run_compas_audit.py`: the pipeline and the report.
- `compas_audit.py`: plain-Python statistics (reference-group ratios with
  intervals, matched-rate comparison, error rates). No delta needed.
- `compas_data.py`: download, hash checks, minimizing (including the derived
  `full_followup` flag), ProPublica's filter.
- `requirements.txt`: the pinned pipeline.
- `tests/`: `test_compas_helpers.py` (standard library only) and
  `test_compas_pipeline.py` (needs delta, zeta and beta).
