import pytest

from phi_guard.redactor import Redactor, manual_finding

TEXT = "Patient: Eleanor Whitfield, phone (416) 555-0142, seen at Lakeview Clinic."


def test_keep_decision_is_honoured():
    r = Redactor(key="k")
    first = r.redact(TEXT)
    phone = next(f for f in first.findings if f.kind == "PHONE")
    second = r.redact(TEXT, keep=[phone.span])
    assert "(416) 555-0142" in second.text
    assert "Whitfield" not in second.text
    assert [f.kind for f in second.kept] == ["PHONE"]


def test_manual_addition_is_removed():
    start = TEXT.index("Lakeview Clinic")
    m = manual_finding(TEXT, start, start + len("Lakeview Clinic"), "OTHER")
    out = Redactor(mode="mask").redact(TEXT, manual=[m]).text
    assert "Lakeview" not in out and "[OTHER]" in out


def test_manual_wins_overlap_and_cannot_be_kept():
    start = TEXT.index("Eleanor")
    m = manual_finding(TEXT, start, start + len("Eleanor"), "PATIENT_NAME")
    res = Redactor(mode="mask").redact(TEXT, manual=[m], keep=[m.span])
    assert "Eleanor" not in res.text
    # The detected "Eleanor Whitfield" overlapped the manual span and lost.
    assert res.text.startswith("Patient: [PATIENT_NAME] Whitfield")


def test_manual_finding_validation():
    with pytest.raises(ValueError):
        manual_finding("abc", 2, 9)
    with pytest.raises(ValueError):
        manual_finding("abc", 0, 1, "bad kind")


def test_mode_override_and_restore_detailed():
    r = Redactor(key="k")
    masked = r.redact(TEXT, mode="mask").text
    assert "[PATIENT_NAME]" in masked and r.vault_size == 0
    coded = r.redact(TEXT).text
    restored, missing = r.restore_detailed(coded + " [SIN_deadbeef]")
    assert restored.startswith(TEXT) and missing == ["[SIN_deadbeef]"]
    assert len(r.known_tokens) == r.vault_size == 2


def test_apply_rejects_bad_mode_and_overlap():
    r = Redactor()
    with pytest.raises(ValueError):
        r.apply("x", [], mode="nope")
    a = manual_finding("abcdef", 0, 3)
    b = manual_finding("abcdef", 2, 5)
    with pytest.raises(ValueError):
        r.apply("abcdef", [a, b])
