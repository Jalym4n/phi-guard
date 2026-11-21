import pytest

from phi_guard import detectors, ner
from phi_guard.finding import Finding


def test_scan_merges_ner_findings(monkeypatch):
    text = "Eleanor Whitfield came in. Patient: Eleanor Whitfield"

    def fake(t):
        return [
            Finding("PERSON_NAME_NER", 0, 17, t[0:17], 0.7, "ner"),
            Finding("PERSON_NAME_NER", 36, 53, t[36:53], 0.7, "ner"),
        ]

    monkeypatch.setattr(ner, "find_person_names", fake)
    found = detectors.scan(text, ner=True)
    # The regex PATIENT_NAME (priority 50) beats NER (40) where they overlap.
    assert [(f.kind, f.text) for f in found] == [
        ("PERSON_NAME_NER", "Eleanor Whitfield"),
        ("PATIENT_NAME", "Eleanor Whitfield"),
    ]


def test_real_spacy_if_installed():
    if not ner.is_available():
        pytest.skip("spaCy model not installed")
    found = ner.find_person_names("Yesterday Margaret Okafor visited the clinic with her son.")
    assert any("Okafor" in f.text for f in found)
    assert all(f.confidence == 0.7 for f in found)
