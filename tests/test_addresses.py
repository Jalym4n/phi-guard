import pytest

from phi_guard.addresses import find_addresses
from phi_guard.detectors import scan


@pytest.mark.parametrize(
    "text,expected",
    [
        ("lives at 48 Maple Grove Crescent, Hamilton", "48 Maple Grove Crescent"),
        ("Unit 4, 120 King St W today", "Unit 4, 120 King St W"),
        ("#12 - 300 Lakeshore Blvd.", "#12 - 300 Lakeshore Blvd."),
        ("55 Queen Street East, Suite 200 Toronto", "55 Queen Street East, Suite 200"),
        ("at 7 Oak Ave", "7 Oak Ave"),
        ("4-120 Main Street", "4-120 Main Street"),
        ("1200 Bay Parkway", "1200 Bay Parkway"),
        ("15 1st Avenue", "15 1st Avenue"),
        ("22 Birchwood Court #5", "22 Birchwood Court #5"),
    ],
)
def test_address_formats(text, expected):
    found = find_addresses(text)
    assert [f.text for f in found] == [expected]
    assert found[0].kind == "ADDRESS" and found[0].confidence == 0.85


@pytest.mark.parametrize(
    "text",
    [
        "Take 2 tablets daily",
        "Seen by Dr. Patel at 3 pm",
        "Room 12 on the main floor",
        "BP 132/84, HR 72",
        "500 mg twice daily",
    ],
)
def test_address_negatives(text):
    assert find_addresses(text) == []


def test_address_kind_can_be_disabled():
    text = "Address: 48 Maple Grove Crescent"
    assert [f.kind for f in scan(text)] == ["ADDRESS"]
    assert scan(text, kinds=["PHONE"]) == []
