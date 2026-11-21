from phi_guard.detectors import scan
from phi_guard.finding import Finding, from_utf16, to_utf16, utf16_index_map


def test_confidence_values():
    found = {f.kind: f.confidence for f in scan("SIN 123 456 782, Mrs. Whitfield, a@b.example.com")}
    assert found["SIN"] == 0.99
    assert found["PATIENT_NAME"] == 0.8  # honorific cue -> "Please check"
    assert found["EMAIL"] >= 0.85


def test_utf16_offsets_with_emoji():
    text = "🩺 Note 😀 Patient: Ann Lee"
    (f,) = scan(text)
    assert text[f.start : f.end] == "Ann Lee"
    s16, e16 = to_utf16(text, f.start), to_utf16(text, f.end)
    assert text.encode("utf-16-le")[s16 * 2 : e16 * 2].decode("utf-16-le") == "Ann Lee"
    assert from_utf16(text, s16) == f.start and from_utf16(text, e16) == f.end
    m = utf16_index_map(text)
    assert m[f.start] == s16 and m[len(text)] == len(text.encode("utf-16-le")) // 2


def test_from_utf16_rounds_inside_surrogate_and_clamps():
    text = "a😀b"
    assert from_utf16(text, 2) == 1  # middle of the emoji
    assert from_utf16(text, 99) == len(text)


def test_finding_to_dict():
    f = Finding("SIN", 0, 3, "abc", 0.99)
    assert f.to_dict() == {"kind": "SIN", "start": 0, "end": 3, "confidence": 0.99, "source": "regex", "text": "abc"}
    assert "text" not in f.to_dict(include_text=False)
    assert f.span == (0, 3)
