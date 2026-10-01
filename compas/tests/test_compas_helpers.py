"""Tests for the data loader and the statistics helpers.

These need only the standard library and pytest: no delta, zeta or beta, and
no network. The one test at the end that checks the real dataset runs only if
the dataset has already been cached (run the example once first); it is
reported as skipped otherwise.
"""

import csv
import io
import re
import statistics
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import cohort, row  # noqa: E402

import compas_audit as audit  # noqa: E402
import compas_data as data  # noqa: E402


def synthetic_raw(extra_rows=0):
    """A small raw-format CSV: CRLF line endings, personal columns, quoted fields."""
    columns = ["id", "name", "first", "last", "dob", "compas_screening_date", "c_case_number"] + list(data.COPIED[1:])
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(columns)
    for i in range(2 + extra_rows):
        record = {c: "x" for c in columns}
        record.update({
            "id": str(i + 1), "name": f"zzperson{i} \"the, third\"\nline2", "first": f"zzfirst{i}", "last": f"zzlast{i}",
            "dob": "1980-01-0" + str(i + 1), "compas_screening_date": "2013-02-02", "c_case_number": f"13CASE{i}",
            "race": "Caucasian", "priors_count": "3", "score_text": "Low", "age_cat": "25 - 45",
        })
        writer.writerow([record[c] for c in columns])
    return out.getvalue().encode("utf-8")


# --- the filter ---------------------------------------------------------------

def test_filter_keeps_a_normal_row():
    assert data.apply_propublica_filter([row()]) == [row()]


@pytest.mark.parametrize(
    "bad",
    [
        {"days_b_screening_arrest": 31},
        {"days_b_screening_arrest": -31},
        {"days_b_screening_arrest": ""},
        {"is_recid": -1},
        {"c_charge_degree": "O"},
        {"score_text": "N/A"},
        {"score_text": ""},
    ],
)
def test_filter_drops_each_excluded_case(bad):
    assert data.apply_propublica_filter([row(**bad)]) == []


def test_filter_keeps_the_boundaries():
    rows = [row(days_b_screening_arrest=30), row(days_b_screening_arrest=-30)]
    assert len(data.apply_propublica_filter(rows)) == 2


# --- minimizing and caching: no personal data on disk ---------------------------

def test_sha256_known_vector():
    assert data.sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_minimize_keeps_only_the_audit_columns_and_values():
    out = data.minimize(synthetic_raw())
    parsed = list(csv.reader(io.StringIO(out.decode("utf-8"), newline="")))
    assert tuple(parsed[0]) == data.KEEP
    assert len(parsed) == 3
    first = dict(zip(parsed[0], parsed[1]))
    assert (first["id"], first["race"], first["priors_count"], first["score_text"]) == ("1", "Caucasian", "3", "Low")
    assert first["full_followup"] == "1"  # screened 2013-02-02
    for personal in (b"zzperson", b"zzfirst", b"zzlast", b"1980-01", b"13CASE", b"2013-02-02"):
        assert personal not in out
    assert not re.search(rb"\d{4}-\d{2}-\d{2}", out)  # no date of any kind survives


@pytest.mark.parametrize(
    "date, flag",
    [("2013-01-01", "1"), ("2014-03-31", "1"), ("2014-04-01", "0"), ("2014-12-31", "0")],
)
def test_full_followup_boundary(date, flag):
    assert data.full_followup(date) == flag


@pytest.mark.parametrize("bad", ["", "2014-4-1", "04/01/2014", "2014-04-01T00:00", None])
def test_full_followup_rejects_anything_that_is_not_a_date(bad):
    with pytest.raises(ValueError, match="screening date"):
        data.full_followup(bad)


def test_minimize_flags_a_late_screening_and_needs_the_date_column():
    raw = synthetic_raw().replace(b"2013-02-02", b"2014-06-15")
    parsed = list(csv.DictReader(io.StringIO(data.minimize(raw).decode("utf-8"), newline="")))
    assert {r["full_followup"] for r in parsed} == {"0"}
    no_date = raw.replace(b"compas_screening_date", b"renamed_column")
    with pytest.raises(ValueError, match="layout has changed"):
        data.minimize(no_date)


def test_minimize_rejects_a_changed_layout():
    broken = b"id,name,race\r\n1,x,Caucasian\r\n"
    with pytest.raises(ValueError, match="layout has changed"):
        data.minimize(broken)


def test_download_caches_only_the_minimized_copy_with_owner_only_permissions(tmp_path):
    raw = synthetic_raw()
    destination = tmp_path / "cache" / "min.csv"
    out = data.download(
        destination, fetch=lambda: raw,
        raw_sha256=data.sha256_bytes(raw), min_sha256=data.sha256_bytes(data.minimize(raw)),
    )
    assert out == destination
    saved = destination.read_bytes()
    assert saved == data.minimize(raw)
    assert b"zzperson" not in saved and b"1980-01" not in saved
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert [p.name for p in destination.parent.iterdir()] == ["min.csv"]  # no temp files left


def test_download_refuses_and_saves_nothing_when_the_raw_hash_differs(tmp_path):
    raw = synthetic_raw()
    destination = tmp_path / "min.csv"
    with pytest.raises(ValueError, match="does not match the pinned one"):
        data.download(destination, fetch=lambda: raw, raw_sha256="0" * 64, min_sha256=data.sha256_bytes(data.minimize(raw)))
    assert list(tmp_path.iterdir()) == []


def test_download_refuses_and_saves_nothing_when_the_minimized_hash_differs(tmp_path):
    raw = synthetic_raw()
    destination = tmp_path / "min.csv"
    with pytest.raises(ValueError, match="minimized dataset does not match"):
        data.download(destination, fetch=lambda: raw, raw_sha256=data.sha256_bytes(raw), min_sha256="0" * 64)
    assert list(tmp_path.iterdir()) == []


def test_a_failed_write_leaves_no_temporary_file_and_no_destination(tmp_path, monkeypatch):
    destination = tmp_path / "cache" / "min.csv"

    def boom(*_args, **_kwargs):
        raise OSError("disk went away")

    monkeypatch.setattr(data.os, "replace", boom)
    with pytest.raises(OSError, match="disk went away"):
        data._write_private(destination, b"payload")
    assert not destination.exists()
    assert list(destination.parent.iterdir()) == []


def test_the_cache_lives_in_the_ignored_data_folder():
    assert data.CACHE_FILE.parent == data.CACHE_DIR
    assert data.CACHE_DIR.name == "data"
    ignore = (data.CACHE_DIR / ".gitignore").read_text().splitlines()
    assert "*" in ignore and "!.gitignore" in ignore


def test_load_raw_returns_only_the_keep_columns(tmp_path):
    cached = tmp_path / "min.csv"
    cached.write_bytes(data.minimize(synthetic_raw()))
    rows = data.load_raw(cached, expected_sha256=data.sha256_bytes(cached.read_bytes()))
    assert len(rows) == 2
    assert all(tuple(r) == data.KEEP for r in rows)
    for personal in ("name", "first", "last", "dob"):
        assert personal not in rows[0]


def test_load_raw_refuses_a_file_with_the_wrong_hash(tmp_path):
    cached = tmp_path / "min.csv"
    cached.write_bytes(data.minimize(synthetic_raw()))
    with pytest.raises(ValueError, match="does not match the pinned dataset"):
        data.load_raw(cached)  # default expected hash is the real dataset's


# --- risk rule ----------------------------------------------------------------

def test_risk_factors_use_no_race_and_no_score():
    a = row(race="Caucasian", decile_score=1, score_text="Low", priors_count=5, c_charge_degree="F")
    b = row(race="African-American", decile_score=10, score_text="High", priors_count=5, c_charge_degree="F")
    assert audit.risk_factors(a) == audit.risk_factors(b)
    assert audit.risk_factor_count(a) == 2


def test_risk_factor_boundaries():
    assert audit.risk_factors(row(juv_fel_count=1))["juvenile_history"] is True
    assert audit.risk_factors(row(juv_misd_count=1))["juvenile_history"] is True
    assert audit.risk_factors(row(priors_count=3))["high_priors"] is False
    assert audit.risk_factors(row(priors_count=4))["high_priors"] is True
    assert audit.risk_factors(row(juv_other_count=1))["juvenile_history"] is True
    assert audit.risk_factors(row(age_cat="Less than 25"))["young_age"] is True
    assert audit.risk_factor_count(row()) == 0


# --- error rates --------------------------------------------------------------

def test_confusion_rates_by_hand():
    rows = (
        [row(two_year_recid=0, score_text="High")] * 1      # false positive
        + [row(two_year_recid=0, score_text="Medium")] * 1  # false positive (Medium counts as flagged)
        + [row(two_year_recid=0, score_text="Low")] * 6     # true negatives
        + [row(two_year_recid=1, score_text="Low")] * 1     # false negative
        + [row(two_year_recid=1, score_text="Medium")] * 3  # true positives
        + [row(race="Hispanic", two_year_recid=0, score_text="High")] * 9  # ignored
    )
    c = audit.confusion_rates(rows, "Caucasian")
    assert (c["n"], c["not_recharged"], c["recharged"]) == (12, 8, 4)
    assert c["fpr"] == pytest.approx(2 / 8)
    assert c["fnr"] == pytest.approx(1 / 4)


def test_confusion_rates_empty_denominator_is_none():
    c = audit.confusion_rates([row(two_year_recid=0)], "Caucasian")
    assert c["fnr"] is None


# --- ratio against an explicit reference group --------------------------------

FAVORABLE = lambda r: int(r["decile_score"]) == 1  # noqa: E731


def table_for(rows, reference="Ref", **kwargs):
    return {e["group"]: e for e in audit.ratio_vs_reference(rows, FAVORABLE, reference, **kwargs)}


def test_ratio_vs_reference_by_hand_and_sizes():
    rows = cohort("Ref", 1000, 800) + cohort("Big", 1000, 560) + cohort("Tiny", 10, 10)
    table = table_for(rows)
    assert table["Big"]["ratio"] == pytest.approx(0.70)
    assert table["Big"]["below_four_fifths"] is True
    assert table["Big"]["clearly_below"] is True
    assert table["Tiny"]["too_small"] is True
    assert table["Tiny"]["below_four_fifths"] is None
    assert table["Tiny"]["clearly_below"] is None
    assert table["Ref"]["is_reference"] is True
    assert table["Ref"]["below_four_fifths"] is None


def test_reference_row_has_no_interval():
    rows = cohort("Ref", 1000, 800) + cohort("Big", 1000, 560)
    ref = table_for(rows)["Ref"]
    assert ref["ratio"] == 1.0
    assert ref["ci_low"] is None and ref["ci_high"] is None
    assert ref["interval_undefined"] is False  # it is the reference, not a failure of the method


def test_interval_matches_an_independent_hand_computation():
    # 560/1000 vs 800/1000, computed outside this code: ratio 0.7, interval (0.6572, 0.7456).
    low, high = audit._log_ratio_interval(560, 1000, 800, 1000)
    assert low == pytest.approx(0.6572, abs=5e-4)
    assert high == pytest.approx(0.7456, abs=5e-4)


def test_z_value_is_the_95_percent_normal_quantile():
    assert audit.Z_95 == pytest.approx(statistics.NormalDist().inv_cdf(0.975), abs=1e-12)
    assert audit.Z_95 == pytest.approx(1.96, abs=1e-3)


def test_small_samples_are_not_called_clearly_below():
    # 0.70 point estimate, but only 120 people each: the interval reaches 0.8.
    rows = cohort("Ref", 120, 96) + cohort("Small", 120, 67)
    entry = table_for(rows)["Small"]
    assert entry["below_four_fifths"] is True
    assert entry["clearly_below"] is False


def test_a_ratio_of_exactly_four_fifths_is_not_below():
    rows = cohort("Ref", 1000, 500) + cohort("Even", 1000, 400)
    entry = table_for(rows)["Even"]
    assert entry["ratio"] == 0.8
    assert entry["below_four_fifths"] is False


def test_four_fifths_is_checked_from_both_sides():
    rows = cohort("Ref", 1000, 500) + cohort("Under", 1000, 395) + cohort("Over", 1000, 405)
    table = table_for(rows)
    assert table["Under"]["ratio"] == pytest.approx(0.79) and table["Under"]["below_four_fifths"] is True
    assert table["Over"]["ratio"] == pytest.approx(0.81) and table["Over"]["below_four_fifths"] is False
    assert audit.FOUR_FIFTHS == 0.8


def test_the_default_minimum_group_size_is_one_hundred():
    rows = cohort("Ref", 1000, 500) + cohort("AtHundred", 100, 20) + cohort("NinetyNine", 99, 20)
    table = {e["group"]: e for e in audit.ratio_vs_reference(rows, FAVORABLE, "Ref")}  # no min_n given
    assert audit.MIN_GROUP_N == 100
    assert table["AtHundred"]["too_small"] is False and table["NinetyNine"]["too_small"] is True


def test_the_minimum_group_size_boundary():
    rows = cohort("Ref", 1000, 500) + cohort("AtMin", 100, 20) + cohort("JustUnder", 99, 20)
    table = table_for(rows, min_n=100)
    assert table["AtMin"]["too_small"] is False
    assert table["JustUnder"]["too_small"] is True


def test_a_group_with_no_favorable_outcomes_has_no_interval_but_is_flagged_below():
    rows = cohort("Ref", 200, 100) + cohort("Zero", 200, 0)
    entry = table_for(rows)["Zero"]
    assert entry["ratio"] == 0.0
    assert entry["below_four_fifths"] is True
    assert entry["interval_undefined"] is True
    assert entry["clearly_below"] is None


def test_a_group_with_only_favorable_outcomes_has_no_interval():
    rows = cohort("Ref", 200, 100) + cohort("All", 200, 200)
    entry = table_for(rows)["All"]
    assert entry["ratio"] == 2.0
    assert entry["interval_undefined"] is True
    assert entry["ci_low"] is None


def test_interval_undefined_with_zero_favorable():
    assert audit._log_ratio_interval(0, 100, 50, 100) is None
    assert audit._log_ratio_interval(100, 100, 50, 100) is None


def test_reference_group_must_exist_be_nonempty_and_large_enough():
    with pytest.raises(ValueError, match="not in the data"):
        audit.ratio_vs_reference(cohort("A", 200, 100), FAVORABLE, "Missing")
    with pytest.raises(ValueError, match="no favorable"):
        audit.ratio_vs_reference(cohort("A", 200, 0), FAVORABLE, "A")
    with pytest.raises(ValueError, match="only 5 members"):
        audit.ratio_vs_reference(cohort("A", 5, 3), FAVORABLE, "A")


# --- matched-rate comparison ---------------------------------------------------

def badness_rows():
    # group A: 0,1,1,2   group B: 1,1,2,2   (badness = decile_score here)
    rows = [row(race="A", decile_score=v) for v in (0, 1, 1, 2)]
    rows += [row(race="B", decile_score=v) for v in (1, 1, 2, 2)]
    return rows


BADNESS = lambda r: int(r["decile_score"])  # noqa: E731


def test_matched_rate_split_by_hand():
    out = audit.matched_rate_ratio(badness_rows(), BADNESS, 0.5, group="B", reference="A")
    # 4 of 8 favorable: the lone 0 (1), then 3 of the four 1s -> share 0.75.
    assert out["reference_rate"] == pytest.approx((1 + 0.75 + 0.75) / 4)
    assert out["group_rate"] == pytest.approx((0.75 + 0.75) / 4)
    assert out["ratio"] == pytest.approx(0.6)


def test_matched_rate_overall_rate_is_exact():
    rows = badness_rows()
    for target in (0.125, 0.25, 0.5, 0.625, 0.75, 1.0):
        out = audit.matched_rate_ratio(rows, BADNESS, target, group="B", reference="A")
        overall = (out["group_rate"] * 4 + out["reference_rate"] * 4) / 8
        assert overall == pytest.approx(target)


def test_matched_rate_edges():
    rows = badness_rows()
    everyone = audit.matched_rate_ratio(rows, BADNESS, 1.0, group="B", reference="A")
    assert everyone["ratio"] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="no favorable"):
        audit.matched_rate_ratio(rows, BADNESS, 0.0, group="B", reference="A")
    with pytest.raises(ValueError):
        audit.matched_rate_ratio(rows, BADNESS, 1.5, group="B", reference="A")
    with pytest.raises(ValueError, match="not in the data"):
        audit.matched_rate_ratio(rows, BADNESS, 0.5, group="Z", reference="A")


def test_matched_rate_on_a_clean_cut():
    # Target 1/8: only the lone 0 is favorable, no split needed.
    out = audit.matched_rate_ratio(badness_rows(), BADNESS, 0.125, group="B", reference="A")
    assert out["reference_rate"] == pytest.approx(0.25)
    assert out["group_rate"] == pytest.approx(0.0)


# --- the real dataset (only if it is already cached) ---------------------------

@pytest.mark.skipif(not data.CACHE_FILE.exists(), reason="dataset not cached yet; run compas/run_compas_audit.py once")
def test_real_dataset_counts_columns_and_published_rates():
    raw = data.load_raw()
    assert len(raw) == data.EXPECTED_RAW_ROWS
    assert set(raw[0]) == set(data.KEEP)
    for personal in ("name", "first", "last", "dob", "compas_screening_date"):
        assert personal not in raw[0]
    filtered = data.apply_propublica_filter(raw)
    assert len(filtered) == data.EXPECTED_FILTERED_ROWS
    # The follow-up selection effect that the report warns about, pinned to the real file.
    early = [r for r in filtered if r["full_followup"] == "1"]
    late = [r for r in filtered if r["full_followup"] == "0"]
    assert (len(early), len(late)) == (5297, 875)
    assert sum(r["two_year_recid"] == "1" for r in early) / len(early) == pytest.approx(0.366, abs=5e-4)
    assert sum(r["two_year_recid"] == "1" for r in late) / len(late) == pytest.approx(0.997, abs=5e-4)
    for race in ("African-American", "Caucasian"):
        c = audit.confusion_rates(raw, race)
        assert round(c["fpr"] * 100) == audit.PUBLISHED_FPR_PERCENT[race]
        assert round(c["fnr"] * 100) == audit.PUBLISHED_FNR_PERCENT[race]
