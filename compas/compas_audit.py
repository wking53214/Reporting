"""Plain-Python helpers for the COMPAS audit: no delta, zeta or beta needed.

These cover the three things the first version of this audit got wrong or
overstated:

  - ``ratio_vs_reference``: compare each group to an EXPLICIT reference group
    and say how uncertain the ratio is, instead of comparing to whichever group
    happens to have the highest rate (which can be a group of 31 people).
  - ``matched_rate_ratio``: compare two systems at the SAME overall favorable
    rate. Two systems that flag different shares of people are not comparable
    on a ratio, because the ratio moves with where the cut is placed.
  - ``confusion_rates``: false positive / false negative rates on any subset,
    so the published figures can be checked on the subset they were computed on.
"""

import math
from typing import Callable, Dict, List, Optional, Sequence

Row = Dict[str, str]

FOUR_FIFTHS = 0.8
Z_95 = 1.959963984540054

# Groups smaller than this are reported but not ranked or called significant.
# This is a choice made by this example, not a legal standard: the EEOC
# guideline itself says differences based on small numbers may not be
# statistically significant, and does not set a number.
MIN_GROUP_N = 100

# ProPublica's published figures, as whole percents (their article rounds).
# False positive rate: not re-charged within two years but scored Medium/High.
# False negative rate: re-charged within two years but scored Low.
# ("Re-charged" is what the dataset's two_year_recid column records: a new
# charge, not a proven offence. See the README limits.)
PUBLISHED_FPR_PERCENT = {"African-American": 45, "Caucasian": 23}
PUBLISHED_FNR_PERCENT = {"African-American": 28, "Caucasian": 48}


# ---------------------------------------------------------------------------
# The decision rule under test (one definition, used by the pipeline and here)
# ---------------------------------------------------------------------------

def risk_factors(row: Row) -> Dict[str, bool]:
    """The four recorded criminal-history factors. No race, no COMPAS score.

    "Recorded" matters: priors, juvenile records and charge degree are all
    products of arrests and charging, which can themselves differ by group.
    These thresholds are this example's own judgment calls (4 or more priors,
    any juvenile record, a felony charge, under 25). They are not validated
    against the pretrial-risk literature.
    """
    juvenile = (
        int(row["juv_fel_count"]) + int(row["juv_misd_count"]) + int(row["juv_other_count"])
    )
    return {
        "high_priors": int(row["priors_count"]) >= 4,
        "juvenile_history": juvenile > 0,
        "felony_charge": row["c_charge_degree"] == "F",
        "young_age": row["age_cat"] == "Less than 25",
    }


def risk_factor_count(row: Row) -> int:
    return sum(risk_factors(row).values())


# ---------------------------------------------------------------------------
# Error rates
# ---------------------------------------------------------------------------

def confusion_rates(rows: Sequence[Row], race: str) -> Dict[str, Optional[float]]:
    """FPR and FNR for one race, treating score_text Medium/High as "flagged".

    "Recharged" means two_year_recid == 1: a new charge within two years, as
    the dataset records it (not a proven offence).
    """
    group = [r for r in rows if r["race"] == race]
    not_recharged = [r for r in group if r["two_year_recid"] == "0"]
    recharged = [r for r in group if r["two_year_recid"] == "1"]
    false_pos = sum(1 for r in not_recharged if r["score_text"] in ("Medium", "High"))
    false_neg = sum(1 for r in recharged if r["score_text"] == "Low")
    return {
        "n": len(group),
        "not_recharged": len(not_recharged),
        "recharged": len(recharged),
        "false_positives": false_pos,
        "false_negatives": false_neg,
        "fpr": false_pos / len(not_recharged) if not_recharged else None,
        "fnr": false_neg / len(recharged) if recharged else None,
    }


# ---------------------------------------------------------------------------
# Disparate impact against an explicit reference group
# ---------------------------------------------------------------------------

def group_rates(rows: Sequence[Row], favorable: Callable[[Row], bool]) -> Dict[str, Dict[str, float]]:
    """Per group: n, favorable count, favorable rate."""
    tally: Dict[str, List[int]] = {}
    for row in rows:
        entry = tally.setdefault(row["race"], [0, 0])
        entry[0] += 1
        entry[1] += 1 if favorable(row) else 0
    return {
        group: {"n": n, "favorable": fav, "rate": fav / n}
        for group, (n, fav) in tally.items()
    }


def _log_ratio_interval(fav_a: int, n_a: int, fav_b: int, n_b: int):
    """95% interval for rate_a / rate_b (log method), or None when it does not apply.

    The log method needs every rate strictly between 0 and 1. With no favorable
    outcomes the ratio is 0 and the log is undefined; with all favorable the
    variance term is 0 and the interval would come out too narrow. In both
    cases the interval is reported as None rather than made up.
    """
    if not (0 < fav_a < n_a and 0 < fav_b < n_b):
        return None
    rate_a, rate_b = fav_a / n_a, fav_b / n_b
    variance = (1 - rate_a) / (n_a * rate_a) + (1 - rate_b) / (n_b * rate_b)
    centre = math.log(rate_a / rate_b)
    spread = Z_95 * math.sqrt(variance)
    return math.exp(centre - spread), math.exp(centre + spread)


def ratio_vs_reference(
    rows: Sequence[Row],
    favorable: Callable[[Row], bool],
    reference: str,
    min_n: int = MIN_GROUP_N,
) -> List[Dict[str, object]]:
    """Each group's favorable rate as a ratio of the reference group's.

    ``below_four_fifths`` is the plain point estimate. ``clearly_below`` also
    requires the whole 95% interval to sit under 0.8, so it is only true when
    the shortfall is unlikely to be sampling noise. Groups smaller than
    ``min_n`` are reported with ``too_small=True`` and get neither verdict.

    The reference row has no interval (its ratio to itself is exactly 1).
    When the interval does not apply (a group with no, or only, favorable
    outcomes) ``interval_undefined`` is True and ``clearly_below`` is None:
    the ratio is still reported, but nothing is claimed about its uncertainty.
    """
    rates = group_rates(rows, favorable)
    if reference not in rates:
        raise ValueError(f"reference group {reference!r} is not in the data")
    ref = rates[reference]
    if ref["rate"] == 0:
        raise ValueError("the reference group has no favorable outcomes; ratios are undefined")
    if ref["n"] < min_n:
        raise ValueError(f"the reference group has only {ref['n']} members (minimum {min_n})")
    table = []
    for group in sorted(rates, key=lambda g: -rates[g]["n"]):
        info = rates[group]
        ratio = info["rate"] / ref["rate"]
        is_reference = group == reference
        interval = (
            None
            if is_reference
            else _log_ratio_interval(info["favorable"], info["n"], ref["favorable"], ref["n"])
        )
        too_small = info["n"] < min_n
        table.append({
            "group": group,
            "n": info["n"],
            "rate": info["rate"],
            "ratio": ratio,
            "ci_low": None if interval is None else interval[0],
            "ci_high": None if interval is None else interval[1],
            "is_reference": is_reference,
            "too_small": too_small,
            "interval_undefined": (not is_reference) and interval is None,
            "below_four_fifths": None if (too_small or is_reference) else ratio < FOUR_FIFTHS,
            "clearly_below": (
                None
                if (too_small or is_reference or interval is None)
                else interval[1] < FOUR_FIFTHS
            ),
        })
    return table


# ---------------------------------------------------------------------------
# Comparing two systems at the same overall favorable rate
# ---------------------------------------------------------------------------

def matched_rate_ratio(
    rows: Sequence[Row],
    badness: Callable[[Row], float],
    target_rate: float,
    group: str,
    reference: str,
) -> Dict[str, float]:
    """Ratio of two groups' favorable rates when exactly ``target_rate`` of
    ALL rows are favorable.

    ``badness`` is higher for people the system would flag. Everyone below the
    cut is favorable, everyone above it is not, and the people sitting exactly
    on the cut are split by a fixed share so the overall rate lands on
    ``target_rate``. This is an expected value (no random draw), so it is
    deterministic. It answers: if this system flagged exactly this share of
    people, how unevenly would the favorable outcome fall between the groups?
    """
    if not 0.0 <= target_rate <= 1.0:
        raise ValueError("target_rate must be between 0 and 1")
    total = len(rows)
    if total == 0:
        raise ValueError("no rows")
    target = target_rate * total
    counts: Dict[float, int] = {}
    for row in rows:
        value = badness(row)
        counts[value] = counts.get(value, 0) + 1

    below = 0
    boundary = None
    share = 0.0
    for value in sorted(counts):
        at_value = counts[value]
        if below + at_value >= target - 1e-9:
            boundary = value
            share = min(1.0, max(0.0, (target - below) / at_value))
            break
        below += at_value
    if boundary is None:  # only reachable through rounding at target_rate == 1
        boundary, share = max(counts), 1.0

    def weight(row: Row) -> float:
        value = badness(row)
        if value < boundary:
            return 1.0
        if value == boundary:
            return share
        return 0.0

    def rate_of(name: str) -> float:
        members = [r for r in rows if r["race"] == name]
        if not members:
            raise ValueError(f"group {name!r} is not in the data")
        return sum(weight(r) for r in members) / len(members)

    group_rate, reference_rate = rate_of(group), rate_of(reference)
    if reference_rate == 0:
        raise ValueError("the reference group has no favorable outcomes at this cut")
    return {
        "target_rate": target_rate,
        "group_rate": group_rate,
        "reference_rate": reference_rate,
        "ratio": group_rate / reference_rate,
    }
