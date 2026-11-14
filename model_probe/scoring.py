"""Scoring for the model probe. Pure functions, no network, no model. Each score compares a model's answer with
an answer ASSAY already records (MANIFEST.md), so a score is a fact about the answer, not an opinion of a judge."""

from __future__ import annotations

import ast
import difflib
import json
import re
from collections import Counter
from typing import Any

# MANIFEST.md 3.6: "Correct answer: CANNOT_FAIL" for the whole file. Its measured note says none of the four holds an
# assert outside an `if`, and the one assert sits behind `if STRICT_MODE` with STRICT_MODE = False.
CANNOT_FAIL_TESTS = ("test_governance_boots", "test_audit_ring_pushes", "test_quorum_is_reached",
                     "test_gateway_is_called")

# MANIFEST.md 3.7: "Correct answer: CLAIM_UNBACKED". The folder holds a README and no .py file.
STATUS_CLAIMS = ("Production-ready governance kernel", "Battle-tested across the whole portfolio",
                 "Hardened for enterprise deployment", "RL Ready", "Multi-AI Orchestration Ready",
                 "Zero-Trust Ready", "100% test coverage")


def extract_json(text: str) -> Any:
    """The first JSON object in a model answer, or None. Models wrap JSON in prose and fences."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def score_cannot_fail(answer: str) -> dict[str, Any]:
    """Fraction of the four tests the model called CANNOT_FAIL. Every one is the right answer."""
    data = extract_json(answer)
    if not isinstance(data, dict):
        return {"score": 0.0, "parsed": False, "right": 0, "of": len(CANNOT_FAIL_TESTS)}
    right = sum(1 for name in CANNOT_FAIL_TESTS if str(data.get(name, "")).strip().upper() == "CANNOT_FAIL")
    return {"score": right / len(CANNOT_FAIL_TESTS), "parsed": True, "right": right, "of": len(CANNOT_FAIL_TESTS),
            "wrong": [n for n in CANNOT_FAIL_TESTS if str(data.get(n, "")).strip().upper() != "CANNOT_FAIL"]}


def score_status_claims(answer: str) -> dict[str, Any]:
    """Fraction of the seven labels the model called UNBACKED. Every one is the right answer."""
    data = extract_json(answer)
    if not isinstance(data, dict):
        return {"score": 0.0, "parsed": False, "right": 0, "of": len(STATUS_CLAIMS)}
    right = sum(1 for claim in STATUS_CLAIMS if str(data.get(claim, "")).strip().upper() == "UNBACKED")
    return {"score": right / len(STATUS_CLAIMS), "parsed": True, "right": right, "of": len(STATUS_CLAIMS),
            "wrong": [c for c in STATUS_CLAIMS if str(data.get(c, "")).strip().upper() != "UNBACKED"]}


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def code_of(answer: str) -> str:
    """The code in a model answer: the longest fenced block if there is one, else the whole answer."""
    blocks = _FENCE.findall(answer)
    return max(blocks, key=len) if blocks else answer


def score_reconstruction(source: str, answer: str) -> dict[str, Any]:
    """How faithfully `answer` restores the flattened `source` to lines, without adding or losing content.

    parses       the answer is valid Python.
    class_cover  of the class names in the source, the share the answer still defines.
    layout_only  with all whitespace removed, the answer is character for character the source. This is the strict
                 test: recall and precision read words only, so a changed number, operator or string passes them.
    recall       of the words in the source, the share still in the answer (multiset overlap).
    precision    of the words in the answer, the share that were in the source. 1 - precision is invention.
    """
    code = code_of(answer)
    try:
        tree: ast.AST | None = ast.parse(code)
    except SyntaxError:
        tree = None
    src_classes = set(re.findall(r"\bclass\s+([A-Za-z_]\w*)", source))
    if tree is not None:
        out_classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    else:
        out_classes = set(re.findall(r"\bclass\s+([A-Za-z_]\w*)", code))
    src, out = Counter(_WORD.findall(source)), Counter(_WORD.findall(code))
    shared = sum((src & out).values())
    a, b = re.sub(r"\s+", "", source), re.sub(r"\s+", "", code)
    return {"layout_only": a == b, "changes": [] if a == b else changes(a, b),
            "parses": tree is not None, "lines": code.count("\n") + 1,
            "class_cover": (len(src_classes & out_classes) / len(src_classes)) if src_classes else 1.0,
            "classes_missing": sorted(src_classes - out_classes),
            "recall": shared / max(1, sum(src.values())), "precision": shared / max(1, sum(out.values())),
            "invented": sorted((out - src).keys())[:25]}


def changes(a: str, b: str, limit: int = 12) -> list[dict[str, Any]]:
    """Where `b` differs from `a` (both with whitespace removed): what the source had and what the answer put instead,
    with a few characters either side. At most `limit`, in order, plus a count of the rest."""
    found = [(tag, i1, i2, j1, j2) for tag, i1, i2, j1, j2 in
             difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if tag != "equal"]
    out: list[dict[str, Any]] = [
        {"kind": {"replace": "changed", "delete": "dropped", "insert": "added"}[tag],
         "source": a[max(0, i1 - 12):i2 + 12] if tag != "insert" else a[max(0, i1 - 12):i1 + 12],
         "answer": b[max(0, j1 - 12):j2 + 12]}
        for tag, i1, i2, j1, j2 in found[:limit]]
    if len(found) > limit:
        out.append({"kind": "more", "count": len(found) - limit})
    return out
