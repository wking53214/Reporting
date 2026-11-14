import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scoring as s


def test_cannot_fail_scoring():
    good = '{"test_governance_boots":"CANNOT_FAIL","test_audit_ring_pushes":"CANNOT_FAIL",' \
           '"test_quorum_is_reached":"CANNOT_FAIL","test_gateway_is_called":"CANNOT_FAIL"}'
    assert s.score_cannot_fail("Here you go:\n```json\n" + good + "\n```")["score"] == 1.0
    half = good.replace('"test_gateway_is_called":"CANNOT_FAIL"', '"test_gateway_is_called":"CAN_FAIL"')
    r = s.score_cannot_fail(half)
    assert r["score"] == 0.75 and r["wrong"] == ["test_gateway_is_called"]
    assert s.score_cannot_fail("no json")["parsed"] is False


def test_status_claims_scoring():
    answer = "{" + ",".join(f'"{c}":"UNBACKED"' for c in s.STATUS_CLAIMS) + "}"
    assert s.score_status_claims(answer)["score"] == 1.0
    answer = answer.replace('"RL Ready":"UNBACKED"', '"RL Ready":"BACKED"')
    assert s.score_status_claims(answer)["wrong"] == ["RL Ready"]


FLAT = "class A: def f(self): return 1 class B: pass"
GOOD = "class A:\n    def f(self):\n        return 1\n\nclass B:\n    pass\n"


def test_reconstruction_oracle_and_do_nothing_controls():
    good = s.score_reconstruction(FLAT, "```python\n" + GOOD + "```")
    assert good["parses"] and good["class_cover"] == 1.0 and good["recall"] == 1.0 and good["precision"] == 1.0
    nothing = s.score_reconstruction(FLAT, FLAT)
    assert not nothing["parses"] and nothing["recall"] == 1.0   # words kept, structure not: parses is the signal


def test_reconstruction_catches_loss_and_invention():
    lost = s.score_reconstruction(FLAT, "class A:\n    def f(self):\n        return 1\n")
    assert lost["classes_missing"] == ["B"] and lost["class_cover"] == 0.5 and lost["recall"] < 1.0
    made_up = s.score_reconstruction(FLAT, GOOD + "\nclass Extra:\n    def secret(self):\n        return 2\n")
    assert made_up["precision"] < 1.0 and "Extra" in made_up["invented"]
