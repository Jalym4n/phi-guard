from phi_guard.detectors import scan
from phi_guard.dictionary import Dictionary, dump_terms, parse_terms


def test_always_remove_whole_word_case_insensitive():
    d = Dictionary(always=["Lakeview Clinic", "Okonkwo"])
    found = d.find("Seen at LAKEVIEW   clinic by Dr Okonkwo; not Okonkwos.")
    assert [f.text for f in found] == ["LAKEVIEW   clinic", "Okonkwo"]
    assert all(f.kind == "CUSTOM" and f.confidence == 1.0 for f in found)


def test_never_remove_suppresses_detector_findings():
    text = "Clinic line (905) 555-0100. Patient phone 905-555-0177."
    d = Dictionary(never=["905-555-0100"])
    assert [f.text for f in scan(text, dictionary=d)] == ["905-555-0177"]


def test_never_remove_name_lookalike():
    text = "Mr. Keflex was given."
    assert [f.kind for f in scan(text)] == ["PATIENT_NAME"]
    assert scan(text, dictionary=Dictionary(never=["keflex"])) == []


def test_custom_terms_beat_detectors():
    text = "Patient: Ada Lovelace"
    found = scan(text, dictionary=Dictionary(always=["Ada Lovelace"]))
    assert [(f.kind, f.text) for f in found] == [("CUSTOM", "Ada Lovelace")]


def test_parse_and_dump_terms():
    terms = parse_terms("# staff\nAda  Lovelace\n\nada lovelace\nGrace Hopper\n")
    assert terms == ["Ada Lovelace", "Grace Hopper"]
    assert dump_terms(terms) == "Ada Lovelace\nGrace Hopper\n"


def test_empty_dictionary_is_falsy():
    assert not Dictionary()
    assert Dictionary(always=["x"])
    assert Dictionary().find("anything") == []
    assert not Dictionary().allows("anything")
