import pytest

from phi_guard.redactor import TOKEN_RE, Redactor

NOTE = "Patient: Eleanor Whitfield, SIN 123 456 782, email e.w@example.com"


def test_pseudonymize_is_deterministic_per_key():
    a = Redactor(key="k1").redact(NOTE).text
    b = Redactor(key="k1").redact(NOTE).text
    c = Redactor(key="k2").redact(NOTE).text
    assert a == b and a != c
    assert "123 456 782" not in a and "Whitfield" not in a


def test_token_format():
    out = Redactor(key="k").redact("SIN 123 456 782").text
    m = TOKEN_RE.search(out)
    assert m and m.group("kind") == "SIN"


def test_mask_mode():
    out = Redactor(mode="mask").redact(NOTE).text
    assert "[PATIENT_NAME]" in out and "[SIN]" in out and "[EMAIL]" in out


def test_restore_and_forget():
    r = Redactor(key="k")
    red = r.redact(NOTE).text
    assert r.restore(red) == NOTE
    r.forget()
    assert r.restore(red) == red


def test_env_key(monkeypatch):
    monkeypatch.setenv("PHI_GUARD_KEY", "from-env")
    assert Redactor().redact(NOTE).text == Redactor(key="from-env").redact(NOTE).text


def test_invalid_mode():
    with pytest.raises(ValueError):
        Redactor(mode="shred")
