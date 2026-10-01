"""Run ProPublica's COMPAS data through zeta Locks, beta Decisions and delta's
ledger, outcome obligations and four-fifths screen.

Two systems are compared on the same 6,172 defendants:

  - a simple rule: flag a defendant for review when 2 or more of 4 recorded
    criminal-history factors are present (4+ priors, any juvenile record, a
    felony charge, age under 25). It never sees race or COMPAS's own score;
  - COMPAS's own classification (score_text "Low" is the favorable outcome).

What this script is, and is not
-------------------------------
It is a worked example of delta handling a real, outcome-labelled cohort,
and of what the four-fifths screen does and does not tell you. It is not a
validated pretrial risk tool, and the rule's thresholds are judgment calls.
COMPAS is a benchmark here, not a target domain.

The "outcome" is the dataset's two_year_recid column: whether the person was
charged again within two years. That is an arrest-based record, not a proven
offence, and it can itself differ by group (see the README limits). It is also not a
clean two-year rate for people screened after about April 2014: the data were
collected before two years had passed, and nearly all of those rows are people who
were re-charged. Re-charge rates are therefore reported on the full file and on the
subset with complete follow-up (compas_data.FOLLOWUP_CUTOFF).

Run (from the repository root, after ``pip install --no-deps -r compas/requirements.txt``):

    python compas/run_compas_audit.py

The first run downloads the dataset (about 2.5 MB) from ProPublica's public
repository, checks it against a pinned SHA-256, and caches only the columns
this audit reads.
"""

import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compas_audit import (  # noqa: E402
    MIN_GROUP_N,
    PUBLISHED_FNR_PERCENT,
    PUBLISHED_FPR_PERCENT,
    confusion_rates,
    group_rates,
    matched_rate_ratio,
    ratio_vs_reference,
    risk_factor_count,
    risk_factors,
)
from compas_data import (  # noqa: E402
    EXPECTED_FILTERED_ROWS,
    EXPECTED_RAW_ROWS,
    apply_propublica_filter,
    load_raw,
)

from beta import DecisionEngine, DecisionRule, DecisionRuleRegistry  # noqa: E402
from delta import (  # noqa: E402
    PROVENANCE_VERIFIED,
    CohortDecision,
    DecisionLedger,
    DecisionObligationTracker,
    MaturationRule,
    check_statistical_outcome_equity,
)
from delta.obligation import OUTCOME_RESOLVED  # noqa: E402
from zeta import Combination, Key, KeySet, LockEvaluator, LockRegistry, LockSpec  # noqa: E402

REFERENCE_GROUP = "Caucasian"
COMPARED = ("African-American", REFERENCE_GROUP)
FOUR_FIFTHS_CLASS = "four_fifths_adverse_impact"


# --- the decision system under test -----------------------------------------

def detect_keys(row) -> KeySet:
    present = risk_factors(row)
    return KeySet([
        Key(name=name, present=flag, reason=f"{name}={flag}")
        for name, flag in present.items()
    ])


def build_lock_registry() -> LockRegistry:
    return LockRegistry([
        LockSpec(
            lock_id="elevated_risk_lock",
            required_keys=("high_priors", "juvenile_history", "felony_charge", "young_age"),
            combination=Combination.N_OF_M,
            n=2,
            dwell_threshold=1,  # one point-in-time assessment, no debounce
        ),
    ])


def build_decision_registry() -> DecisionRuleRegistry:
    return DecisionRuleRegistry([
        DecisionRule(
            decision_id="flag_review",
            decision="FLAG_FOR_REVIEW",
            open_locks=("elevated_risk_lock",),
            priority=10,
            reasoning_template="{decision}: 2+ recorded risk factors present ({open_locks})",
            instructions="Route to judicial review before the pretrial release decision.",
        ),
        DecisionRule(
            decision_id="standard_monitoring",
            decision="STANDARD_MONITORING",
            closed_locks=("elevated_risk_lock",),
            priority=0,
            reasoning_template="{decision}: fewer than 2 recorded risk factors present",
            instructions="Standard pretrial monitoring track.",
        ),
    ])


def build_pipeline():
    """The Lock evaluator and decision engine for the rule above."""
    lock_registry = build_lock_registry()
    return LockEvaluator(lock_registry), DecisionEngine(build_decision_registry(), lock_registry)


def decide_row(row, ts, lock_evaluator, decision_engine):
    """One defendant through Keys, Locks and the decision engine."""
    subject = f"defendant_{row['id']}"
    keys = detect_keys(row)
    return decision_engine.decide(subject, keys, lock_evaluator.evaluate_all(subject, keys, ts), ts)


def expected_decision(row) -> str:
    """The same rule written plainly, used to cross-check the pipeline."""
    return "FLAG_FOR_REVIEW" if risk_factor_count(row) >= 2 else "STANDARD_MONITORING"


def calibration_from_obligations(obligations, race_by_subject, decision_by_fingerprint, followup_by_subject):
    """(decision, race, not_recharged, full_followup) read back from the RESOLVED obligations.

    An obligation resolved with ``favorable=None`` (genuinely ambiguous) is refused,
    as delta's own cohort bridge refuses it: it would otherwise be counted as a
    re-charge by default.
    """
    records = []
    for ob in obligations.all():
        if ob.state != OUTCOME_RESOLVED:
            raise SystemExit(f"obligation {ob.obligation_id} is {ob.state}, not RESOLVED")
        if ob.favorable is None:
            raise SystemExit(f"obligation {ob.obligation_id} resolved with no favorable/unfavorable call")
        records.append((
            decision_by_fingerprint[ob.decision_fingerprint],
            race_by_subject[ob.subject_id],
            bool(ob.favorable),
            followup_by_subject[ob.subject_id],
        ))
    return records


# --- report helpers ---------------------------------------------------------

def pct(value) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def section(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def report_error_rates(raw, filtered) -> None:
    section("0. DATA CHECK: error rates on the subset ProPublica published them on")
    print("Positive prediction = score_text Medium or High. FPR = not re-charged within two")
    print("years but flagged. FNR = re-charged but scored Low. Published figures are whole")
    print("percents (African-American / Caucasian):")
    print(f"  published FPR {PUBLISHED_FPR_PERCENT['African-American']}% / {PUBLISHED_FPR_PERCENT['Caucasian']}%,"
          f"  FNR {PUBLISHED_FNR_PERCENT['African-American']}% / {PUBLISHED_FNR_PERCENT['Caucasian']}%\n")
    complete = [r for r in filtered if r["full_followup"] == "1"]
    for label, rows in (
        (f"all {len(raw)} raw rows", raw),
        (f"{len(filtered)} filtered rows", filtered),
        (f"{len(complete)} filtered rows with complete two-year follow-up", complete),
    ):
        print(f"  on {label}:")
        for race in COMPARED:
            c = confusion_rates(rows, race)
            print(f"    {race:17s} n={c['n']:5d}  FPR {c['false_positives']}/{c['not_recharged']} = {pct(c['fpr'])}"
                  f"   FNR {c['false_negatives']}/{c['recharged']} = {pct(c['fnr'])}")
    print("\nThe published rates are the ones on the raw rows. The filtered subset gives")
    print("different (not wrong) rates, so check against the subset the figure came from.")
    report_followup(filtered)


def report_followup(filtered) -> None:
    print("\n  Follow-up completeness (people screened from 2014-04-01 on could not have been")
    print("  followed for two full years when the data were collected):")
    for label, flag in (("complete follow-up", "1"), ("truncated follow-up", "0")):
        rows = [r for r in filtered if r["full_followup"] == flag]
        recharged = sum(1 for r in rows if r["two_year_recid"] == "1")
        print(f"    {label:20s} n={len(rows):5d}  re-charged {recharged}/{len(rows)} = {pct(recharged / len(rows))}")
    print("  The truncated rows are almost all people who WERE re-charged: they were kept in the")
    print("  file because of the outcome. Rates that read two_year_recid are biased upward unless")
    print("  they use the complete-follow-up rows.")


def report_calibration(records, label: str) -> None:
    print(f"\n  === {label} ({len(records)} rows) ===")
    for decision_value in ("STANDARD_MONITORING", "FLAG_FOR_REVIEW"):
        print(f"  -- {decision_value} --")
        rates = {}
        for race in COMPARED:
            outcomes = [ok for dv, r, ok, _ in records if dv == decision_value and r == race]
            rates[race] = sum(outcomes) / len(outcomes)
            print(f"    {race:17s} n={len(outcomes):5d}  not re-charged {rates[race]:.1%}"
                  f"  (re-charged {1 - rates[race]:.1%})")
        gap = (rates[COMPARED[1]] - rates[COMPARED[0]]) * 100
        print(f"    Within this bucket, {COMPARED[0]} defendants were re-charged {gap:.1f} points more often.")


def report_delta_screen(label: str, cohort) -> None:
    findings = check_statistical_outcome_equity(cohort)
    print(f"\n  {label}")
    if not findings:
        print("    delta's screen found no four-fifths violations.")
        return
    sizes = Counter(group for d in cohort for group in d.group_distribution)
    flagged = [f for f in findings if f.classification == FOUR_FIFTHS_CLASS]
    for f in findings:
        if f.classification != FOUR_FIFTHS_CLASS:  # e.g. cohort too small to say anything
            print(f"    [{f.classification}] {f.evidence.get('detail', '')}")
    if flagged:
        evidence = flagged[0].evidence
        top = evidence["highest_group_favorable_rate"]
        names = [g for g, rate in evidence["all_group_rates"].items() if rate == top]
        reference = ", ".join(f"{g} (n={sizes.get(g, '?')})" for g in names)
        print(f"    delta compares each group to the HIGHEST-rate group: {reference}, rate {top}.")
        for f in flagged:
            e = f.evidence
            print(f"    [{f.classification}] {e['group']} (n={sizes.get(e['group'], '?')}): "
                  f"rate {e['group_favorable_rate']} / {top} = {e['ratio']}")


def report_reference_table(label: str, rows, favorable) -> None:
    print(f"\n  {label}  (reference group: {REFERENCE_GROUP})")
    print(f"    {'group':18s} {'n':>5s} {'rate':>7s} {'ratio':>7s}   95% interval     verdict")
    for entry in ratio_vs_reference(rows, favorable, REFERENCE_GROUP):
        if entry["is_reference"]:
            verdict = "reference"
        elif entry["too_small"]:
            verdict = f"n < {MIN_GROUP_N}: not interpreted"
        elif entry["interval_undefined"]:
            side = "below" if entry["below_four_fifths"] else "at or above"
            verdict = f"{side} 0.8, interval undefined (no or all favorable outcomes)"
        elif entry["clearly_below"]:
            verdict = "below 0.8, interval entirely below 0.8"
        elif entry["below_four_fifths"]:
            verdict = "below 0.8, interval reaches 0.8"
        else:
            verdict = "at or above 0.8"
        low, high = entry["ci_low"], entry["ci_high"]
        interval = "     n/a      " if low is None else f"{low:5.2f} to {high:5.2f}"
        print(f"    {entry['group']:18s} {entry['n']:5d} {entry['rate']:7.1%} {entry['ratio']:7.2f}   {interval}   {verdict}")


def natural_cuts(rows, badness):
    """The unflagged shares this system actually produces (one per score level)."""
    counts = Counter(badness(r) for r in rows)
    running, cuts = 0, []
    for value in sorted(counts):
        running += counts[value]
        cuts.append(running / len(rows))
    return cuts


def report_matched(rows) -> None:
    decile = lambda r: int(r["decile_score"])  # noqa: E731
    rule_cuts, compas_cuts = natural_cuts(rows, risk_factor_count), natural_cuts(rows, decile)
    mine_rate = sum(1 for r in rows if risk_factor_count(r) < 2) / len(rows)
    compas_rate = sum(1 for r in rows if r["score_text"] == "Low") / len(rows)
    print("\n  Ratio African-American / Caucasian when each system leaves the SAME share of")
    print("  people unflagged. A * marks a cut the system really produces; an unmarked value")
    print("  is a hypothetical: an expected value over a random split of the people exactly")
    print("  on the boundary, so the system is held to the same share.")
    print(f"    {'unflagged share':>16s} {'this rule':>11s} {'COMPAS':>9s}")
    for target in sorted({round(compas_rate, 4), round(mine_rate, 4), 0.65, 0.70, 0.90}):
        mine = matched_rate_ratio(rows, risk_factor_count, target, COMPARED[0], REFERENCE_GROUP)["ratio"]
        compas = matched_rate_ratio(rows, decile, target, COMPARED[0], REFERENCE_GROUP)["ratio"]
        mark_rule = "*" if any(abs(target - c) < 5e-4 for c in rule_cuts) else " "
        mark_compas = "*" if any(abs(target - c) < 5e-4 for c in compas_cuts) else " "
        print(f"    {target:16.1%} {mine:10.3f}{mark_rule} {compas:8.3f}{mark_compas}")
    print("  A ratio closer to 1.0 means a more even split. Compare down a row, not across rows.")


def main() -> None:
    raw = load_raw()
    if len(raw) != EXPECTED_RAW_ROWS:
        raise SystemExit(f"expected {EXPECTED_RAW_ROWS} raw rows, got {len(raw)}")
    rows = apply_propublica_filter(raw)
    if len(rows) != EXPECTED_FILTERED_ROWS:
        raise SystemExit(f"expected {EXPECTED_FILTERED_ROWS} filtered rows, got {len(rows)}")
    print(f"Loaded {len(raw)} raw rows; {len(rows)} after ProPublica's filter.")
    print("Group sizes:", {g: v["n"] for g, v in sorted(group_rates(rows, lambda r: True).items(), key=lambda kv: -kv[1]["n"])})

    report_error_rates(raw, rows)

    # --- run the pipeline -----------------------------------------------------
    lock_evaluator, decision_engine = build_pipeline()
    ledger = DecisionLedger()
    obligations = DecisionObligationTracker()
    horizon = MaturationRule(kind="recidivism_check", horizon_seconds=730 * 86400)
    obligations.register_maturation("flag_review", horizon)
    obligations.register_maturation("standard_monitoring", horizon)

    # Decision times are synthetic (one minute apart); screening dates are not used.
    t0 = datetime(2013, 1, 1)
    counts = Counter()
    race_by_subject, followup_by_subject, decision_by_fingerprint = {}, {}, {}
    local_calibration = []  # kept only to cross-check what the obligations give back
    mine_cohort, compas_cohort = [], []
    for idx, row in enumerate(rows):
        ts = t0 + timedelta(minutes=idx)
        decision = decide_row(row, ts, lock_evaluator, decision_engine)
        # The Lock/Decision path must agree with the plain rule used for the tables below.
        if decision.decision != expected_decision(row):
            raise SystemExit(f"defendant_{row['id']}: pipeline said {decision.decision}, rule says {expected_decision(row)}")
        counts[decision.decision] += 1
        ledger.append(decision)

        subject = f"defendant_{row['id']}"
        race_by_subject[subject] = row["race"]
        followup_by_subject[subject] = row["full_followup"]
        decision_by_fingerprint[decision.decision_fingerprint] = decision.decision
        not_recharged = row["two_year_recid"] == "0"
        obligation = obligations.open_for_decision(decision, domain="pretrial_risk", opened_at=ts.timestamp())
        # delta asks for a provenance class on every resolution (verified, attested or
        # estimated). This example stamps PROVENANCE_VERIFIED because the value comes
        # from the dataset's recorded two_year_recid column. That is a choice made
        # here; nothing else about the outcome is checked.
        obligations.resolve_obligation(
            obligation.obligation_id,
            resolved_at=(ts + timedelta(days=730)).timestamp(),
            resolved_value={"two_year_recid": row["two_year_recid"]},
            provenance=PROVENANCE_VERIFIED,
            favorable=not_recharged,
        )
        local_calibration.append((decision.decision, row["race"], not_recharged, row["full_followup"]))
        mine_cohort.append(CohortDecision(subject, decision.decision == "STANDARD_MONITORING", {row["race"]: 1.0}))
        compas_cohort.append(CohortDecision(subject, row["score_text"] == "Low", {row["race"]: 1.0}))

    if not ledger.verify_chain_integrity():
        raise SystemExit("ledger hash chain failed to verify")
    print(f"\nPipeline: {len(ledger)} decisions in the ledger, hash chain verifies. {dict(counts)}")

    calibration = calibration_from_obligations(obligations, race_by_subject, decision_by_fingerprint, followup_by_subject)
    if Counter(calibration) != Counter(local_calibration):
        raise SystemExit("outcomes read back from delta's obligations differ from the ones recorded")
    print(f"Obligations: {len(calibration)} resolved, and read back identical to what was recorded.")

    # --- Test 1: decision disparate impact -----------------------------------
    section("1. DECISION DISPARATE IMPACT (favorable = not flagged / scored Low)")
    print("\n1a. delta's screen exactly as shipped:")
    report_delta_screen("this rule", mine_cohort)
    report_delta_screen("COMPAS", compas_cohort)
    print("\n  Note: the reference is whichever group has the highest rate, so it can change")
    print("  between systems and can be a very small group. Compare 1b, where it is fixed.")

    print("\n1b. Against an explicit reference group, with uncertainty:")
    report_reference_table("this rule", rows, lambda r: risk_factor_count(r) < 2)
    report_reference_table("COMPAS", rows, lambda r: r["score_text"] == "Low")

    print("\n1c. The two systems at matched rates:")
    report_matched(rows)

    # --- Test 2: calibration --------------------------------------------------
    section("2. OUTCOME CALIBRATION: same decision, did the new-charge rate differ by race?")
    print("Read back from delta's resolved obligations (outcome = not re-charged within two")
    print("years, as recorded in two_year_recid). Shown twice: on the complete-follow-up rows")
    print("(the clean comparison) and on every row (biased upward, see section 0).")
    report_calibration([c for c in calibration if c[3] == "1"], "COMPLETE two-year follow-up only")
    report_calibration(calibration, "ALL rows (includes truncated follow-up)")

    section("CAVEATS")
    print(f"- The four-fifths rule is a screening signal, not a legal finding. Groups under {MIN_GROUP_N} are not interpreted.")
    print("- The rule's thresholds are this example's own judgment calls, unvalidated.")
    print("- Priors, charge degree and the re-charge outcome are all arrest-based records. They")
    print("  can reflect differences in policing and charging, so a gap here is not by itself")
    print("  evidence about behaviour or about intent.")
    print("- Re-charge rates are biased upward on the full file: the 875 rows screened from")
    print("  2014-04-01 on are almost all re-charged people. Use the complete-follow-up rows.")
    print("- With different base rates and an imperfect classifier, equal calibration and equal error")
    print("  rates cannot both hold. That does not by itself explain the gaps reported here.")
    print("- COMPAS and pretrial risk are a public benchmark here, not a target domain.")


if __name__ == "__main__":
    main()
