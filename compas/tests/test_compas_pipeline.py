"""Tests for the pipeline side of the example (Keys, Locks, Decisions, delta).

These import run_compas_audit, which needs delta, zeta and beta. Install them
first (see compas/requirements.txt); without them this file fails to import
rather than skipping, so a missing install is never mistaken for a pass.
No dataset and no network are needed.
"""

import itertools
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import cohort, row  # noqa: E402

import compas_data as data  # noqa: E402
import run_compas_audit as run  # noqa: E402
from delta import (  # noqa: E402
    PROVENANCE_VERIFIED,
    CohortDecision,
    DecisionObligationTracker,
    MaturationRule,
)

T0 = datetime(2013, 1, 1)


def combination_rows():
    """One row for each of the 16 ways the four factors can be on or off."""
    rows, truth = [], []
    for i, (priors, juvenile, felony, young) in enumerate(itertools.product([0, 1], repeat=4)):
        rows.append(row(
            id=f"c{i}",
            priors_count=4 if priors else 0,
            juv_misd_count=1 if juvenile else 0,
            c_charge_degree="F" if felony else "M",
            age_cat="Less than 25" if young else "25 - 45",
        ))
        truth.append(priors + juvenile + felony + young)
    return rows, truth


def test_detect_keys_reports_each_factor():
    keys = run.detect_keys(row(priors_count=4, c_charge_degree="F"))
    assert keys.is_present("high_priors") and keys.is_present("felony_charge")
    assert not keys.is_present("juvenile_history") and not keys.is_present("young_age")


def test_pipeline_flags_exactly_when_two_or_more_factors_are_present():
    """The Key -> Lock -> Decision path against the rule written out by hand, for all 16 cases."""
    rows, truth = combination_rows()
    lock_evaluator, engine = run.build_pipeline()
    for i, (r, factors_on) in enumerate(zip(rows, truth)):
        decision = run.decide_row(r, T0 + timedelta(minutes=i), lock_evaluator, engine)
        expected = "FLAG_FOR_REVIEW" if factors_on >= 2 else "STANDARD_MONITORING"
        assert decision.decision == expected, f"{r['id']} with {factors_on} factors on"
        assert run.expected_decision(r) == expected
    assert {sum(1 for t in truth if t >= 2), sum(1 for t in truth if t < 2)} == {11, 5}  # sanity: 11 flag, 5 do not


def test_pipeline_ignores_race_and_compas_score():
    lock_evaluator, engine = run.build_pipeline()
    low = row(id="a", race="Caucasian", decile_score=1, score_text="Low", priors_count=5, c_charge_degree="F")
    high = row(id="b", race="African-American", decile_score=10, score_text="High", priors_count=5, c_charge_degree="F")
    assert run.decide_row(low, T0, lock_evaluator, engine).decision == run.decide_row(high, T0, lock_evaluator, engine).decision


def test_calibration_is_read_back_from_resolved_obligations():
    lock_evaluator, engine = run.build_pipeline()
    obligations = DecisionObligationTracker()
    rule = MaturationRule(kind="recidivism_check", horizon_seconds=730 * 86400)
    obligations.register_maturation("flag_review", rule)
    obligations.register_maturation("standard_monitoring", rule)

    rows = [
        row(id="1", race="Caucasian", two_year_recid=0),                                    # standard, not re-charged
        row(id="2", race="African-American", two_year_recid=1),                             # standard, re-charged
        row(id="3", race="African-American", two_year_recid=0, priors_count=9, c_charge_degree="F"),  # flag, not re-charged
    ]
    race_by_subject, decision_by_fp, expected = {}, {}, []
    for i, r in enumerate(rows):
        ts = T0 + timedelta(minutes=i)
        decision = run.decide_row(r, ts, lock_evaluator, engine)
        race_by_subject[f"defendant_{r['id']}"] = r["race"]
        decision_by_fp[decision.decision_fingerprint] = decision.decision
        ob = obligations.open_for_decision(decision, domain="pretrial_risk", opened_at=ts.timestamp())
        obligations.resolve_obligation(
            ob.obligation_id, resolved_at=(ts + timedelta(days=730)).timestamp(),
            resolved_value={"two_year_recid": r["two_year_recid"]}, provenance=PROVENANCE_VERIFIED,
            favorable=r["two_year_recid"] == "0",
        )
        expected.append((decision.decision, r["race"], r["two_year_recid"] == "0", r["full_followup"]))

    followup_by_subject = {f"defendant_{r['id']}": r["full_followup"] for r in rows}
    got = run.calibration_from_obligations(obligations, race_by_subject, decision_by_fp, followup_by_subject)
    assert sorted(got) == sorted(expected)
    assert ("FLAG_FOR_REVIEW", "African-American", True, "1") in got


def test_calibration_refuses_an_unresolved_obligation():
    lock_evaluator, engine = run.build_pipeline()
    obligations = DecisionObligationTracker()
    obligations.register_maturation("standard_monitoring", MaturationRule(kind="recidivism_check", horizon_seconds=1))
    decision = run.decide_row(row(id="9"), T0, lock_evaluator, engine)
    obligations.open_for_decision(decision, domain="pretrial_risk", opened_at=T0.timestamp())
    with pytest.raises(SystemExit, match="not RESOLVED"):
        run.calibration_from_obligations(
            obligations, {"defendant_9": "Caucasian"}, {decision.decision_fingerprint: decision.decision}, {"defendant_9": "1"}
        )


def test_calibration_refuses_an_ambiguous_outcome():
    lock_evaluator, engine = run.build_pipeline()
    obligations = DecisionObligationTracker()
    obligations.register_maturation("standard_monitoring", MaturationRule(kind="recidivism_check", horizon_seconds=1))
    decision = run.decide_row(row(id="8"), T0, lock_evaluator, engine)
    ob = obligations.open_for_decision(decision, domain="pretrial_risk", opened_at=T0.timestamp())
    obligations.resolve_obligation(
        ob.obligation_id, resolved_at=T0.timestamp() + 5, resolved_value={"two_year_recid": "?"},
        provenance=PROVENANCE_VERIFIED, favorable=None,
    )
    with pytest.raises(SystemExit, match="no favorable/unfavorable call"):
        run.calibration_from_obligations(
            obligations, {"defendant_8": "Caucasian"}, {decision.decision_fingerprint: decision.decision}, {"defendant_8": "1"}
        )


def test_matched_table_stars_only_cuts_the_system_really_produces(capsys):
    # Ten people, five per group. decile 1,1,2,2,3 in each, "Low" for decile <= 2:
    # COMPAS's real cuts are 40%, 80% and 100%. No risk factors anywhere: the rule's only cut is 100%.
    rows = []
    for group in ("Caucasian", "African-American"):
        for i, decile in enumerate((1, 1, 2, 2, 3)):
            rows.append(row(id=f"{group}{i}", race=group, decile_score=decile, score_text="Low" if decile <= 2 else "High"))
    run.report_matched(rows)
    out = capsys.readouterr().out
    by_target = {l.split()[0]: l for l in out.splitlines() if re.match(r"\s+\d+\.\d%", l)}
    assert set(by_target) == {"65.0%", "70.0%", "80.0%", "90.0%", "100.0%"}
    assert by_target["80.0%"].rstrip().endswith("*")        # COMPAS's own cut, last column
    assert by_target["100.0%"].count("*") == 2               # both systems' top cut
    for target in ("65.0%", "70.0%", "90.0%"):
        assert "*" not in by_target[target]                  # hypothetical splits are not starred


@pytest.mark.skipif(not data.CACHE_FILE.exists(), reason="dataset not cached yet; run compas/run_compas_audit.py once")
def test_the_report_prints_the_numbers_the_readme_quotes(capsys):
    run.main()
    out = capsys.readouterr().out
    quoted = [
        "0.6147", "0.5326",                                   # 1a: delta's screen as shipped
        "Asian (n=31)", "Other (n=343)",                      # ... and which group set the bar
        "0.69", "0.63",                                       # 1b: against Caucasian defendants
        "0.684", "0.695", "0.634", "0.663", "0.910", "0.900", # 1c: matched rates
        "5297", "36.6%", "99.7%",                             # follow-up completeness
        "30.3%", "24.3%", "57.9%", "45.8%",                   # 2: complete follow-up
        "5.9 points", "12.1 points",
    ]
    missing = [text for text in quoted if text not in out]
    assert not missing, missing


def test_natural_cuts_are_the_cumulative_shares_at_each_level():
    rows = [row(decile_score=v) for v in (1, 1, 2, 3)]
    assert run.natural_cuts(rows, lambda r: int(r["decile_score"])) == [0.5, 0.75, 1.0]


def make_cohort(spec):
    """spec: {group: (members, favorable)} -> CohortDecision list."""
    out = []
    for group, (n, favorable) in spec.items():
        out += [CohortDecision(f"{group}{i}", i < favorable, {group: 1.0}) for i in range(n)]
    return out


def test_delta_screen_report_names_the_reference_group_and_its_size(capsys):
    run.report_delta_screen("t", make_cohort({"Top": (40, 40), "Low": (40, 20)}))
    printed = capsys.readouterr().out
    assert "Top (n=40)" in printed
    assert "Low (n=40)" in printed and "four_fifths_adverse_impact" in printed


def test_delta_screen_report_survives_an_indeterminate_finding(capsys):
    run.report_delta_screen("tiny", make_cohort({"A": (3, 3), "B": (2, 0)}))  # far below the cohort floor
    printed = capsys.readouterr().out
    assert "indeterminate_insufficient_cohort" in printed
    assert "Traceback" not in printed


def test_delta_screen_report_says_when_nothing_is_flagged(capsys):
    run.report_delta_screen("even", make_cohort({"A": (40, 30), "B": (40, 30)}))
    assert "no four-fifths violations" in capsys.readouterr().out


def test_reference_table_prints_an_undefined_interval_clearly(capsys):
    rows = cohort("Caucasian", 200, 100) + cohort("Hispanic", 200, 0)
    run.report_reference_table("t", rows, lambda r: int(r["decile_score"]) == 1)
    printed = capsys.readouterr().out
    assert "interval undefined" in printed
    assert "reaches 0.8" not in printed
