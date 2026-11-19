from phi_guard.output_scan import scan_output
from phi_guard.redactor import Redactor


def test_known_tokens_are_ignored_and_leaks_found():
    r = Redactor(key="k")
    red = r.redact("Patient: Eleanor Whitfield, SIN 123 456 782").text
    answer = f"Summary for {red.split()[1]}. Call her at 416-555-0142."
    found = scan_output(answer, r.known_tokens)
    assert [f.kind for f in found] == ["PHONE"]
    assert answer[found[0].start : found[0].end] == "416-555-0142"


def test_unknown_tokens_flagged():
    found = scan_output("See [PATIENT_NAME_0badc0de].", known_tokens=set())
    assert [f.kind for f in found] == ["UNKNOWN_TOKEN"]


def test_token_digits_never_trigger_detectors():
    # The digest 12345678 alone must not look like anything.
    assert scan_output("[MRN_12345678] [PHONE_41655501]") == []
