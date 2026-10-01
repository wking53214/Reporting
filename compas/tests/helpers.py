"""Shared test helpers: put the example's modules on the path and build rows."""

import sys
from pathlib import Path

COMPAS_DIR = Path(__file__).resolve().parent.parent
if str(COMPAS_DIR) not in sys.path:
    sys.path.insert(0, str(COMPAS_DIR))


def row(**overrides):
    """A defendant row with every column the audit reads (all values strings)."""
    base = {
        "id": "1", "age_cat": "25 - 45", "race": "Caucasian",
        "juv_fel_count": "0", "juv_misd_count": "0", "juv_other_count": "0",
        "priors_count": "0", "days_b_screening_arrest": "0", "c_charge_degree": "M",
        "is_recid": "0", "two_year_recid": "0", "decile_score": "1", "score_text": "Low",
        "full_followup": "1",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return base


def cohort(group, n, favorable_count, start=0):
    """n rows of one race; the first ``favorable_count`` have decile 1 (favorable), the rest 9."""
    return [
        row(race=group, id=f"{group}{start + i}", decile_score=1 if i < favorable_count else 9)
        for i in range(n)
    ]
