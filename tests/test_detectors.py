"""Detector tests. All values are synthetic."""

import pytest

from phi_guard.detectors import Finding, luhn_valid, resolve_overlaps, scan


def kinds(text):
    return [f.kind for f in scan(text)]


def test_luhn_known_values():
    assert luhn_valid("123456782")
    assert not luhn_valid("123456789")
    assert not luhn_valid("abc")


def test_sin_formats():
    for sin in ["123 456 782", "123-456-782", "123456782"]:
        assert kinds(f"SIN {sin} on file") == ["SIN"]


def test_sin_bad_checksum_ignored():
    assert "SIN" not in kinds("SIN 123 456 789")


def test_ohip_with_version_code():
    found = scan("Health card 5271-938-465 AB today")
    assert [(f.kind, f.text) for f in found] == [("OHIP_NUMBER", "5271-938-465 AB")]


def test_credit_card():
    assert kinds("Card 4512 0133 1234 5677 exp 09/27") == ["CREDIT_CARD"]


def test_email_and_phone():
    assert kinds("Reach me at a.b@example.com or (905) 555-0199.") == ["EMAIL", "PHONE"]


def test_postal_code():
    assert kinds("Hamilton ON L8S 4K1") == ["POSTAL_CODE"]


def test_dob_requires_context():
    assert kinds("DOB: 1957-04-23") == ["DATE_OF_BIRTH"]
    assert kinds("Seen on 2024-02-11") == []


def test_mrn_only_value_is_redacted():
    (f,) = scan("MRN: 00482913")
    assert f.kind == "MRN" and f.text == "00482913"


def test_patient_name_label_and_honorific():
    found = scan("Patient: Eleanor Whitfield\nMrs. Whitfield is well.")
    assert [f.text for f in found] == ["Eleanor Whitfield", "Whitfield"]


def test_ip_address_validation():
    assert kinds("from 10.24.8.101.") == ["IP_ADDRESS"]
    assert kinds("version 999.1.1.1") == []


def test_kinds_filter_and_unknown():
    assert kinds("a.b@example.com") == ["EMAIL"]
    assert scan("a.b@example.com", kinds=["PHONE"]) == []
    with pytest.raises(ValueError):
        scan("x", kinds=["NOPE"])


def test_overlap_resolution_prefers_priority():
    a = Finding("PHONE", 0, 12, "x" * 12)
    b = Finding("OHIP_NUMBER", 0, 12, "x" * 12)
    assert resolve_overlaps([a, b]) == [b]


def test_label_cue_does_not_cross_lines():
    # Regression: "Patient:" with an empty value must not swallow the next line's label.
    assert [f.kind for f in scan("Patient:   \nDOB: 1957-04-23")] == ["DATE_OF_BIRTH"]
