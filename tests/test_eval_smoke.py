"""Keeps the benchmark code working.  Uses tiny generated splits; the real run is `make eval`."""

import pytest

pytest.importorskip("faker")

from eval.generate import generate_split
from eval.injection_data import generate_injection_split
from eval.run import LABELS, injection_eval, phi_guard_system, score_system

from phi_guard.detectors import ALL_KINDS


def test_generator_is_seeded_and_spans_are_exact():
    a, terms = generate_split(7, 12, held_out=True)
    b, _ = generate_split(7, 12, held_out=True)
    assert a == b and terms
    assert any(d["held_out"] for d in a)
    for d in a:
        for s in d["spans"]:
            assert d["text"][s["start"] : s["end"]] == s["text"]
            assert s["kind"] in (*LABELS, "PROVIDER")


def test_scoring_and_injection_eval_run():
    docs, _ = generate_split(8, 8)
    res = score_system("phi-guard", phi_guard_system(list(ALL_KINDS)), docs)
    total = res.total("overlap")
    assert total.n_gold > 0 and 0 <= total.f1() <= 1 and 0 <= res.leakage() <= 1
    inj = injection_eval(generate_injection_split(9, 20, held_out=True))
    assert inj["n_mal"] == inj["n_ben"] == 20 and len(inj["curve"]) == 19
