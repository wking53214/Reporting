"""Load ProPublica's COMPAS two-year recidivism data and apply their filter.

The raw file lists real defendants, including names, dates of birth, case
numbers and jail dates. This module is built so that none of that is ever
written to disk by this code:

  - the raw file is downloaded into memory from ProPublica's public
    repository and checked against a pinned SHA-256 (RAW_SHA256), so a
    changed upstream file cannot silently change the results;
  - only the columns the audit reads (KEEP) are kept, and only that
    minimized copy is cached, under compas/data/ (git-ignored, owner-only
    permissions). The cache is checked against its own pinned hash
    (MIN_SHA256) every time it is read;
  - the raw bytes themselves are never saved.

The filter is ProPublica's published one ("How We Analyzed the COMPAS
Recidivism Algorithm", 2016). It takes the 7,214 raw rows to 6,172.
"""

import csv
import hashlib
import io
import os
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

SOURCE_URL = (
    "https://raw.githubusercontent.com/propublica/compas-analysis/"
    "master/compas-scores-two-years.csv"
)
RAW_SHA256 = "c451db85908b2f7fef1d83203bedf6b71ecda0d5af468d82ae62178f91d0cc7d"
MIN_SHA256 = "7a0724c3f71d23e0cf3e327bee56d61b5310b775f1645224690ddef207586dbc"
EXPECTED_RAW_ROWS = 7214
EXPECTED_FILTERED_ROWS = 6172

CACHE_DIR = Path(__file__).resolve().parent / "data"
CACHE_FILE = CACHE_DIR / "compas-scores-two-years.min.csv"

# Raw columns copied through unchanged. Deliberately excludes name, first,
# last, dob and case numbers.
COPIED = (
    "id",
    "age_cat",
    "race",
    "juv_fel_count",
    "juv_misd_count",
    "juv_other_count",
    "priors_count",
    "days_b_screening_arrest",
    "c_charge_degree",
    "is_recid",
    "two_year_recid",
    "decile_score",
    "score_text",
)

# One column is derived rather than copied: whether the person could have been
# followed for the full two years. The screening date itself is read to work it
# out and is not kept. See FOLLOWUP_CUTOFF.
FOLLOWUP_COLUMN = "full_followup"
SCREENING_DATE_COLUMN = "compas_screening_date"

# Exactly the columns the audit reads (and so exactly what the cache holds).
KEEP = COPIED + (FOLLOWUP_COLUMN,)

# The file holds screenings from 2013-01-01 to 2014-12-31, but recidivism was
# only followed until about April 2016. A person screened after about
# 2014-04-01 therefore could not have been followed for two full years, and in
# this file nearly all of them (872 of 875 rows, 99.7%) are people who WERE
# re-charged: the rows are selected on the outcome. Their re-charge rate is
# 99.7% against 36.6% for earlier screenings. Anything that reads two_year_recid
# as a rate is biased upward unless it is restricted to full_followup == "1".
FOLLOWUP_CUTOFF = "2014-04-01"

Row = Dict[str, str]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def full_followup(screening_date: str) -> str:
    """"1" if a person screened on this date (YYYY-MM-DD) could have been followed
    for two full years, "0" if not. Raises ValueError for anything else."""
    if not _DATE.fullmatch(screening_date or ""):
        raise ValueError(f"not a YYYY-MM-DD screening date: {screening_date!r}")
    return "1" if screening_date < FOLLOWUP_CUTOFF else "0"


def minimize(raw: bytes) -> bytes:
    """The raw CSV reduced to the KEEP columns, as UTF-8 CSV bytes.

    Pure function: no files, no network. The screening date is read to derive
    ``full_followup`` and is then dropped. Raises ValueError if a needed column
    is missing, so a changed upstream layout fails loudly.
    """
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    needed = COPIED + (SCREENING_DATE_COLUMN,)
    missing = [name for name in needed if name not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"the dataset has no column(s) {missing}; its layout has changed")
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(KEEP)
    for row in reader:
        writer.writerow([row[name] for name in COPIED] + [full_followup(row[SCREENING_DATE_COLUMN])])
    return out.getvalue().encode("utf-8")


def _fetch_raw() -> bytes:
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:  # noqa: S310 - fixed https URL
        return response.read()


def _write_private(destination: Path, data: bytes) -> None:
    """Write ``data`` to ``destination`` atomically, readable by the owner only."""
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".tmp-")  # created 0600
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def download(
    destination: Path = CACHE_FILE,
    fetch: Callable[[], bytes] = _fetch_raw,
    raw_sha256: str = RAW_SHA256,
    min_sha256: str = MIN_SHA256,
) -> Path:
    """Fetch the raw file, verify it, and cache ONLY the minimized copy.

    Nothing is written unless both the raw bytes and the minimized bytes match
    their pinned hashes.
    """
    raw = fetch()
    actual = sha256_bytes(raw)
    if actual != raw_sha256:
        raise ValueError(
            f"the downloaded dataset does not match the pinned one: expected sha256 "
            f"{raw_sha256}, got {actual}. Nothing was saved; the results would not be comparable."
        )
    minimized = minimize(raw)
    actual_min = sha256_bytes(minimized)
    if actual_min != min_sha256:
        raise ValueError(
            f"the minimized dataset does not match its pinned hash: expected {min_sha256}, "
            f"got {actual_min}. Nothing was saved."
        )
    _write_private(destination, minimized)
    return destination


def load_raw(path: Optional[Path] = None, expected_sha256: str = MIN_SHA256) -> List[Row]:
    """Read the minimized dataset (downloading it first if needed).

    The file is read once; the bytes that are hashed are the bytes that are
    parsed. Despite the name, the rows hold only the KEEP columns.
    """
    if path is None:
        path = CACHE_FILE if CACHE_FILE.exists() else download()
    data = Path(path).read_bytes()
    actual = sha256_bytes(data)
    if actual != expected_sha256:
        raise ValueError(
            f"{path} does not match the pinned dataset: expected sha256 {expected_sha256}, "
            f"got {actual}. Refusing to use it; the results would not be comparable."
        )
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    return [{name: row[name] for name in KEEP} for row in reader]


def _int_or_none(value: Optional[str]) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def apply_propublica_filter(rows: List[Row]) -> List[Row]:
    """ProPublica's published exclusions, in their order.

    - the screening must be within 30 days of the arrest (otherwise the
      charge may not be the right one);
    - recidivism data must not be missing (is_recid == -1);
    - ordinary traffic offences (charge degree "O") are dropped;
    - rows with no score text ("N/A") are dropped.
    """
    kept = []
    for row in rows:
        days = _int_or_none(row.get("days_b_screening_arrest"))
        if days is None or not -30 <= days <= 30:
            continue
        if _int_or_none(row.get("is_recid")) == -1:
            continue
        if row.get("c_charge_degree") == "O":
            continue
        if row.get("score_text") in (None, "", "N/A"):
            continue
        kept.append(row)
    return kept
