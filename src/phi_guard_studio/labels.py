"""Plain-language names and explanations shown to Studio users.

Written for busy, non-technical clinic staff: "patient details", not "PHI
entities".  The frontend uses these strings directly.
"""

from __future__ import annotations

__all__ = ["DETECTOR_INFO", "KIND_LABELS", "RULE_EXPLANATIONS", "VERDICT_TEXT"]

KIND_LABELS: dict[str, str] = {
    "PATIENT_NAME": "Name",
    "PERSON_NAME_NER": "Possible name",
    "DATE_OF_BIRTH": "Date of birth",
    "OHIP_NUMBER": "Health card number",
    "SIN": "Social insurance number",
    "CREDIT_CARD": "Payment card",
    "EMAIL": "Email address",
    "PHONE": "Phone number",
    "POSTAL_CODE": "Postal code",
    "ADDRESS": "Street address",
    "MRN": "Medical record number",
    "IP_ADDRESS": "Computer address (IP)",
    "CUSTOM": "Your word list",
    "ID_NUMBER": "ID number",
    "OTHER": "Other",
    "UNKNOWN_TOKEN": "Unknown code",
}

#: Settings toggles: (kind, label, example).  All examples are synthetic.
DETECTOR_INFO: list[tuple[str, str, str]] = [
    ("PATIENT_NAME", "Names", "e.g. Patient: Jane Doe, Mrs. Doe"),
    ("DATE_OF_BIRTH", "Dates of birth", "e.g. DOB: 1957-04-23"),
    ("OHIP_NUMBER", "Health card numbers (OHIP)", "e.g. 1234-567-890 AB"),
    ("SIN", "Social insurance numbers", "e.g. 123 456 782"),
    ("CREDIT_CARD", "Payment card numbers", "e.g. 4512 0133 1234 5677"),
    ("EMAIL", "Email addresses", "e.g. jane.doe@example.com"),
    ("PHONE", "Phone numbers", "e.g. (416) 555-0142"),
    ("POSTAL_CODE", "Postal codes", "e.g. L8S 4K1"),
    ("ADDRESS", "Street addresses", "e.g. 48 Maple Grove Crescent"),
    ("MRN", "Medical record numbers", "e.g. MRN: 00482913"),
    ("IP_ADDRESS", "Computer (IP) addresses", "e.g. 10.24.8.101"),
]

RULE_EXPLANATIONS: dict[str, str] = {
    "instruction_override": "Contains text that tries to make the AI ignore its rules.",
    "role_hijack": "Tries to make the AI pretend to be someone else.",
    "system_prompt_probe": "Tries to make the AI reveal its hidden instructions.",
    "fake_delimiter": "Contains fake system markers to confuse the AI.",
    "data_exfiltration": "Asks the AI to send data somewhere.",
    "markdown_image_exfil": "Contains an image link that could secretly send data to an outside website.",
    "tool_abuse": "Tries to make the AI run commands or tools.",
    "safety_bypass": "Tries to switch off the AI's safety rules.",
    "task_replacement": "Tries to replace the AI's real task with a different one.",
    "hidden_characters": "Contains invisible characters, a common way to hide attacks.",
    "lookalike_characters": "Uses look-alike letters from other alphabets to disguise words.",
    "base64": "Contains hidden encoded text with instructions inside.",
}

VERDICT_TEXT: dict[str, dict[str, str]] = {
    "allow": {"title": "Looks safe", "detail": "We didn't find signs that this document tries to manipulate an AI."},
    "review": {
        "title": "Needs a human to review",
        "detail": "Parts of this document look like instructions aimed at an AI. Ask someone to read the highlighted "
        "parts before using it.",
    },
    "block": {
        "title": "Do not use this document",
        "detail": "This document contains several signs of an attempt to manipulate an AI. Do not add it to an AI "
        "tool or knowledge base. Tell your IT contact.",
    },
}
