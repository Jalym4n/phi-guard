"""Generate the labelled synthetic benchmark (PHI detection + prompt injection).

Every document and every value is synthetic.  Names, streets and cities come
from Faker (locale ``en_CA``); SINs and OHIP numbers are random digits with a
valid Luhn check digit, so they look real to a checksum but belong to no one.

Gold labels (``spans``) cover identifiers of the *patient and their
relatives*: names, date of birth, health card (OHIP), SIN, payment card,
email, phone, postal code, street address, MRN, IP address.  This mirrors the
"individual or relatives" scope of HIPAA Safe Harbor.

Clinician names are marked ``ignore`` (a system may remove them or not
without penalty).  The clinic's own phone, fax, and address are *not*
labelled: they are deliberate hard negatives, alongside lab values,
dosages, admission dates, order numbers, firmware versions, and drug names
that look like surnames.

Two splits with different seeds:  ``dev`` (for development) and ``test``
(reported).  Rules were never adjusted while looking at ``test``.  The test
split also contains *held-out* templates (20% of PHI documents, ~30% of
injection snippets) that never appear in ``dev``: they measure how well the
rules generalize beyond the phrasing they were developed on.

Usage::

    python -m eval.generate            # dev=200, test=500 documents
    python -m eval.generate --quick    # dev=20,  test=60 (smoke run)
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from faker import Faker

from phi_guard.detectors import luhn_valid

from .injection_data import generate_injection_split

DATA_DIR = Path(__file__).parent / "data"

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]  # fmt: skip
COMMON_TYPES = ["Street", "St", "Avenue", "Ave", "Road", "Rd", "Boulevard", "Blvd", "Drive", "Dr", "Court",
                "Crescent", "Cres", "Lane", "Way", "Place", "Trail", "Parkway"]  # fmt: skip
RARE_TYPES = ["Circle", "Terrace", "Gate", "Heights", "Grove", "Line", "Sideroad", "Close"]
STREET_WORDS = ["Maple", "Oak", "King", "Queen", "Main", "Bloor", "Elm", "Cedar", "Lakeshore", "Wellington",
                "Victoria", "Church", "Mill", "Pine", "Birchwood", "Highland", "Ridgeview", "Concession",
                "Mount Pleasant", "Sandy Hill", "Bay"]  # fmt: skip
DIRECTIONS = ["N", "S", "E", "W", "North", "South", "East", "West"]
PROVINCES = ["ON", "ON", "ON", "ON", "QC", "BC", "AB", "MB", "NS"]
DRUGS = ["Haldol", "Ativan", "Keflex", "Tylenol", "Dilaudid", "Lasix", "Coumadin", "Xarelto", "Eliquis", "Seroquel"]
EPONYMS = ["Bell's palsy", "Parkinson disease", "Crohn disease", "Graves disease", "a Foley catheter",
           "Hodgkin lymphoma", "Addison disease", "a Holter monitor"]  # fmt: skip
LABS = ["WBC 7.2 x10^9/L", "Hgb 132 g/L", "Plt 245 x10^9/L", "Na 139 mmol/L", "K 4.1 mmol/L",
        "Creatinine 88 umol/L", "eGFR 74 mL/min", "HbA1c 7.2%", "INR 2.4", "TSH 3.12 mIU/L",
        "LDL 2.81 mmol/L", "ALT 31 U/L", "CRP 12.4 mg/L", "Ferritin 45 ug/L"]  # fmt: skip
MEDS = ["metformin 500 mg PO BID", "atorvastatin 20 mg PO daily", "ramipril 5 mg PO daily",
        "insulin glargine 18 units SC qHS", "apixaban 5 mg PO BID", "levothyroxine 88 mcg PO daily",
        "salbutamol 100 mcg 2 puffs q4h PRN", "furosemide 40 mg PO daily", "amlodipine 10 mg PO daily"]  # fmt: skip
COMPLAINTS = ["productive cough", "chest pain on exertion", "worsening shortness of breath", "lower back pain",
              "intermittent palpitations", "fatigue and weight gain", "right knee swelling", "recurrent headaches"]  # fmt: skip
RELATIONS = ["daughter", "son", "husband", "wife", "sister", "brother", "partner"]


@dataclass
class Clinic:
    name: str
    address: str
    city: str
    postal: str
    phone: str
    fax: str


@dataclass
class Doc:
    """Builds text while recording the exact character span of each labelled value."""

    parts: list[str] = field(default_factory=list)
    spans: list[dict[str, Any]] = field(default_factory=list)
    length: int = 0

    def t(self, s: str) -> Doc:
        self.parts.append(s)
        self.length += len(s)
        return self

    def p(self, kind: str, value: str, ignore: bool = False) -> Doc:
        span: dict[str, Any] = {"start": self.length, "end": self.length + len(value), "kind": kind, "text": value}
        if ignore:
            span["ignore"] = True
        self.spans.append(span)
        return self.t(value)

    def text(self) -> str:
        return "".join(self.parts)


class Generator:
    def __init__(self, seed: int, held_out: bool = False) -> None:
        self.held_out = held_out
        self.rng = random.Random(seed)
        self.fake = Faker("en_CA")
        self.fake.seed_instance(seed)
        self.clinics = [self._clinic() for _ in range(5)]

    # -- value generators -------------------------------------------------
    def choice(self, seq: list[str]) -> str:
        return self.rng.choice(seq)

    def digits(self, n: int, first_nonzero: bool = True) -> str:
        first = str(self.rng.randint(1, 9)) if first_nonzero else str(self.rng.randint(0, 9))
        return first + "".join(str(self.rng.randint(0, 9)) for _ in range(n - 1))

    def luhn_complete(self, prefix: str) -> str:
        for c in "0123456789":
            if luhn_valid(prefix + c):
                return prefix + c
        raise AssertionError("unreachable")

    def sin(self) -> str:
        d = self.luhn_complete(self.choice(list("1234567")) + self.digits(7, first_nonzero=False))
        fmt = self.rng.random()
        if fmt < 0.5:
            return f"{d[:3]} {d[3:6]} {d[6:]}"
        if fmt < 0.8:
            return f"{d[:3]}-{d[3:6]}-{d[6:]}"
        return d

    def ohip(self) -> str:
        d = self.luhn_complete(self.digits(9))
        fmt = self.rng.random()
        body = f"{d[:4]}-{d[4:7]}-{d[7:]}" if fmt < 0.45 else f"{d[:4]} {d[4:7]} {d[7:]}" if fmt < 0.8 else d
        r = self.rng.random()
        if r < 0.35:
            vc = "".join(self.rng.choice("ABCDEFGHJKLMNPRSTVWXYZ") for _ in range(2))
            body += self.choice([" ", "-"]) + vc
        return body

    def card(self) -> str:
        kind = self.rng.random()
        if kind < 0.45:
            d = self.luhn_complete("4" + self.digits(14, first_nonzero=False))
        elif kind < 0.85:
            d = self.luhn_complete("5" + str(self.rng.randint(1, 5)) + self.digits(13, first_nonzero=False))
        else:  # Amex, 15 digits, grouped 4-6-5
            d = self.luhn_complete("3" + self.choice(["4", "7"]) + self.digits(12, first_nonzero=False))
            return f"{d[:4]} {d[4:10]} {d[10:]}"
        sep = self.choice([" ", "-", ""])
        return sep.join(d[i : i + 4] for i in range(0, 16, 4))

    def phone(self) -> str:
        area = self.choice(["416", "647", "905", "289", "613", "519", "705", "807", "604", "403"])
        ex, line = self.digits(3), self.digits(4, first_nonzero=False)
        fmt = self.rng.randrange(8)
        return [
            f"({area}) {ex}-{line}",
            f"{area}-{ex}-{line}",
            f"{area}.{ex}.{line}",
            f"{area} {ex} {line}",
            f"+1 {area} {ex} {line}",
            f"1-{area}-{ex}-{line}",
            f"({area}) {ex}-{line}",
            f"{area}{ex}{line}",  # no separators
        ][fmt]

    def postal(self) -> str:
        pc = self.fake.postcode().replace(" ", "")
        r = self.rng.random()
        if r < 0.7:
            return f"{pc[:3]} {pc[3:]}"
        if r < 0.92:
            return pc
        return f"{pc[:3]} {pc[3:]}".lower()

    def street(self, rare_ok: bool = True) -> str:
        civic = str(self.rng.randint(1, 9999))
        if self.rng.random() < 0.08:
            civic += self.choice(["A", "B"])
        word = self.choice(STREET_WORDS) if self.rng.random() < 0.6 else self.fake.last_name()
        stype = self.choice(RARE_TYPES) if rare_ok and self.rng.random() < 0.15 else self.choice(COMMON_TYPES)
        addr = f"{civic} {word} {stype}"
        if self.rng.random() < 0.2:
            addr += " " + self.choice(DIRECTIONS)
        u = self.rng.random()
        unit = str(self.rng.randint(1, 1200))
        if u < 0.1:
            addr = f"Unit {unit}, {addr}"
        elif u < 0.18:
            addr = f"{unit}-{addr}"
        elif u < 0.26:
            addr = f"{addr}, Suite {unit}"
        elif u < 0.32:
            addr = f"{addr} #{unit}"
        elif u < 0.36:
            addr = f"{addr}, Apt {unit}"
        return addr

    def dob_date(self) -> date:
        return date(1930, 1, 1) + timedelta(days=self.rng.randint(0, 31000))

    def fmt_date(self, d: date) -> str:
        f = self.rng.randrange(6)
        return [
            d.isoformat(),
            f"{d.day:02d}/{d.month:02d}/{d.year}",
            f"{MONTHS[d.month - 1]} {d.day}, {d.year}",
            f"{MONTHS[d.month - 1][:3]} {d.day} {d.year}",
            f"{d.day} {MONTHS[d.month - 1]} {d.year}",
            f"{d.year}/{d.month:02d}/{d.day:02d}",
        ][f]

    def recent_date(self) -> str:
        return self.fmt_date(date(2023, 1, 1) + timedelta(days=self.rng.randint(0, 900)))

    def mrn_line(self, doc: Doc) -> None:
        f = self.rng.randrange(6)
        if f == 0:
            doc.t("MRN: ").p("MRN", self.digits(8, first_nonzero=False))
        elif f == 1:
            doc.t("MRN ").p("MRN", self.digits(7))
        elif f == 2:
            doc.t("Medical Record No. ").p("MRN", self.digits(7))
        elif f == 3:
            doc.t("Chart #: ").p("MRN", "H-" + self.digits(6))
        elif f == 4:
            doc.t("Patient ID: ").p("MRN", self.choice(["ABC", "HHS", "SJH"]) + "-" + self.digits(6))
        else:
            doc.t("Hospital #: ").p("MRN", self.digits(7))  # cue phi-guard does not know
        doc.t("\n")

    def email(self, first: str, last: str) -> str:
        user = self.choice([f"{first}.{last}", f"{first[0]}{last}", f"{first}{self.rng.randint(1, 99)}"]).lower()
        user = "".join(ch for ch in user if ch.isalnum() or ch == ".")
        return f"{user}@{self.choice(['example.com', 'example.ca', 'mail.example.org', 'example.net'])}"

    def person(self) -> tuple[str, str]:
        return self.fake.first_name(), self.fake.last_name()

    def _clinic(self) -> Clinic:
        word = self.fake.last_name()
        return Clinic(
            name=f"{word} {self.rng.choice(['Family Health Team', 'Medical Clinic', 'Community Health Centre'])}",
            address=f"{self.rng.randint(10, 999)} {self.rng.choice(STREET_WORDS)} {self.rng.choice(COMMON_TYPES)}",
            city=self.fake.city(),
            postal=self.postal().upper(),
            phone=f"({self.rng.choice(['905', '416'])}) {self.digits(3)}-{self.digits(4, False)}",
            fax=f"({self.rng.choice(['905', '416'])}) {self.digits(3)}-{self.digits(4, False)}",
        )

    def doctor(self) -> str:
        return f"{self.fake.first_name()} {self.fake.last_name()}"

    # -- hard negatives ---------------------------------------------------
    def noise_line(self) -> str:
        """A line with no gold PHI that may still fool a detector."""
        r = self.rng.randrange(10)
        if r == 0:
            return f"Order #: {self.digits(10)}"  # ~10% are Luhn-valid 10-digit numbers
        if r == 1:
            return f"Requisition #: {self.digits(9)}"  # ~10% are Luhn-valid 9-digit numbers
        if r == 2:
            return f"Specimen barcode {self.digits(3)}-{self.digits(3)}-{self.digits(4, False)}"  # phone-shaped
        if r == 3:
            return f"Analyzer firmware {self.rng.randint(1, 9)}.{self.rng.randint(0, 20)}.{self.rng.randint(0, 99)}.{self.rng.randint(0, 250)}"
        if r == 4:
            return f"Accession {self.rng.randint(23, 25)}-{self.digits(3)}-{self.digits(5, False)}"
        if r == 5:
            return f"Admitted {self.recent_date()}; discharged {self.recent_date()}."
        if r == 6:
            return f"Started {self.choice(DRUGS)} 2 mg; history of {self.choice(EPONYMS)}."
        if r == 7:
            return f"Labs: {', '.join(self.rng.sample(LABS, 4))}."
        if r == 8:
            return f"Lot {self.choice(['A', 'B', 'K'])}{self.digits(5)}, expiry {self.recent_date()}."
        return f"Medications: {'; '.join(self.rng.sample(MEDS, 3))}."

    def clinic_header(self, doc: Doc, c: Clinic) -> None:
        doc.t(f"{c.name}\n{c.address}, {c.city} ON {c.postal}\nTel {c.phone}  Fax {c.fax}\n\n")

    # -- patient block ----------------------------------------------------
    def patient_header(self, doc: Doc, first: str, last: str, dob: date) -> None:
        style = self.rng.randrange(4)
        if style == 0:
            doc.t("Patient: ").p("NAME", f"{first} {last}").t("\n")
        elif style == 1:
            doc.t("Patient Name: ").p("NAME", f"{last}, {first}").t("\n")
        elif style == 2:
            doc.t("Name: ").p("NAME", f"{first} {last}").t("\n")
        else:
            doc.t("Re: ").p("NAME", f"{first} {last}").t("\n")  # cue phi-guard does not know
        cue = self.choice(["DOB: ", "Date of Birth: ", "D.O.B. ", "Born ", "DOB "])
        doc.t(cue).p("DATE_OF_BIRTH", self.fmt_date(dob)).t("\n")
        if self.rng.random() < 0.85:
            doc.t(self.choice(["OHIP: ", "Health Card: ", "HCN: ", "Health card number "])).p(
                "OHIP_NUMBER", self.ohip()
            ).t("\n")
        if self.rng.random() < 0.7:
            self.mrn_line(doc)

    def contact_block(self, doc: Doc, first: str, last: str) -> None:
        doc.t("Address: ").p("ADDRESS", self.street()).t(f", {self.fake.city()} {self.choice(PROVINCES)} ")
        doc.p("POSTAL_CODE", self.postal()).t("\n")
        doc.t(self.choice(["Phone: ", "Tel: ", "Home phone: ", "Cell: "])).p("PHONE", self.phone()).t("\n")
        if self.rng.random() < 0.5:
            doc.t("Email: ").p("EMAIL", self.email(first, last)).t("\n")
        if self.rng.random() < 0.4:
            rf, rl = self.fake.first_name(), self.rng.choice([last, self.fake.last_name()])
            doc.t("Emergency contact: ").p("NAME", f"{rf} {rl}").t(f" ({self.choice(RELATIONS)}), ")
            doc.p("PHONE", self.phone()).t("\n")

    def narrative(self, doc: Doc, first: str, last: str, sex: str) -> None:
        hon = "Mr." if sex == "M" else self.choice(["Mrs.", "Ms."])
        pron = "He" if sex == "M" else "She"
        age = self.rng.randint(19, 94)
        opener = self.rng.randrange(3)
        if opener == 0:
            doc.t(f"{hon} ").p("NAME", last).t(f" is a {age}-year-old who presents with {self.choice(COMPLAINTS)}. ")
        elif opener == 1:
            doc.p("NAME", first).t(f" is a {age}-year-old seen today for {self.choice(COMPLAINTS)}. ")
        else:
            doc.t("This ").t(f"{age}-year-old presents with {self.choice(COMPLAINTS)}. ")
        doc.t(f"{pron} reports taking {self.choice(MEDS)}. ")
        if self.rng.random() < 0.35:
            doc.t(f"{pron} was accompanied by {'his' if sex == 'M' else 'her'} {self.choice(RELATIONS)}, ")
            doc.p("NAME", f"{self.fake.first_name()} {self.rng.choice([last, self.fake.last_name()])}").t(". ")
        if self.rng.random() < 0.3:
            doc.t(f"{self.choice(DRUGS)} was discontinued. ")
        doc.t(f"Exam unremarkable apart from {self.choice(['mild edema', 'wheeze', 'tenderness', 'tachycardia'])}.\n")

    # -- document templates -----------------------------------------------
    def _sex_name(self) -> tuple[str, str, str]:
        sex = self.choice(["M", "F"])
        first = self.fake.first_name_male() if sex == "M" else self.fake.first_name_female()
        return sex, first, self.fake.last_name()

    def discharge_summary(self) -> Doc:
        doc, c = Doc(), self.choice_clinic()
        sex, first, last = self._sex_name()
        doc.t("DISCHARGE SUMMARY (synthetic)\n")
        self.clinic_header(doc, c)
        self.patient_header(doc, first, last, self.dob_date())
        self.contact_block(doc, first, last)
        doc.t(f"\nAdmitted: {self.recent_date()}   Discharged: {self.recent_date()}\n")
        doc.t("Attending: Dr. ").p("PROVIDER", self.doctor(), ignore=True).t("\n\nHospital course:\n")
        self.narrative(doc, first, last, sex)
        for _ in range(self.rng.randint(1, 3)):
            doc.t(self.noise_line() + "\n")
        doc.t(f"Discharge medications: {'; '.join(self.rng.sample(MEDS, 2))}.\n")
        doc.t(f"Follow up with family physician on {self.recent_date()}.\n")
        return doc

    def referral_letter(self) -> Doc:
        doc, c = Doc(), self.choice_clinic()
        sex, first, last = self._sex_name()
        doc.t("REFERRAL LETTER (synthetic)\n")
        self.clinic_header(doc, c)
        doc.t(f"{self.recent_date()}\n\nDear Dr. ").p("PROVIDER", self.doctor(), ignore=True).t(",\n\n")
        doc.t("Thank you for seeing ")
        doc.p("NAME", f"{first} {last}").t(" (DOB ").p("DATE_OF_BIRTH", self.fmt_date(self.dob_date())).t("), ")
        doc.t("health card ").p("OHIP_NUMBER", self.ohip()).t(". ")
        self.narrative(doc, first, last, sex)
        doc.t("Contact: ").p("PHONE", self.phone())
        if self.rng.random() < 0.5:
            doc.t(" or ").p("EMAIL", self.email(first, last))
        doc.t(".\nHome address: ").p("ADDRESS", self.street()).t(", ").p("POSTAL_CODE", self.postal()).t(".\n")
        if self.rng.random() < 0.6:
            doc.t(self.noise_line() + "\n")
        doc.t(f"\nPlease call our office at {c.phone} with any questions.\n\nSincerely,\nDr. ")
        doc.p("PROVIDER", self.doctor(), ignore=True).t("\n")
        if self.rng.random() < 0.3:
            doc.t("cc: Dr. ").p("PROVIDER", self.doctor(), ignore=True).t("\n")
        return doc

    def lab_report(self) -> Doc:
        doc, c = Doc(), self.choice_clinic()
        sex, first, last = self._sex_name()
        doc.t("LABORATORY REPORT (synthetic)\n")
        self.clinic_header(doc, c)
        self.patient_header(doc, first, last, self.dob_date())
        doc.t(f"Sex: {sex}\nCollected: {self.recent_date()} 08:{self.rng.randint(10, 59)}\n")
        doc.t("Ordering provider: Dr. ").p("PROVIDER", self.doctor(), ignore=True).t("\n\n")
        for lab in self.rng.sample(LABS, self.rng.randint(4, 7)):
            doc.t(f"  {lab}\n")
        for _ in range(self.rng.randint(1, 3)):
            doc.t(self.noise_line() + "\n")
        if self.rng.random() < 0.5:
            ip = f"{self.choice(['10', '172', '192'])}.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}"
            doc.t("Results viewed via patient portal from ").p("IP_ADDRESS", ip).t(".\n")
        if self.rng.random() < 0.3:
            doc.t("Copy sent to patient at ").p("EMAIL", self.email(first, last)).t(".\n")
        return doc

    def progress_note(self) -> Doc:
        doc, c = Doc(), self.choice_clinic()
        sex, first, last = self._sex_name()
        doc.t(f"PROGRESS NOTE (synthetic) - {c.name}\n")
        self.patient_header(doc, first, last, self.dob_date())
        if self.rng.random() < 0.5:
            self.contact_block(doc, first, last)
        doc.t(f"Visit date: {self.recent_date()}\n\nS: ")
        self.narrative(doc, first, last, sex)
        doc.t(f"O: BP {self.rng.randint(100, 160)}/{self.rng.randint(60, 99)}, HR {self.rng.randint(55, 110)}.\n")
        for _ in range(self.rng.randint(0, 2)):
            doc.t(self.noise_line() + "\n")
        if self.rng.random() < 0.15:
            doc.t("SIN on file for disability form: ").p("SIN", self.sin()).t(".\n")
        if self.rng.random() < 0.1:
            doc.t("Paid uninsured service fee by card ").p("CREDIT_CARD", self.card()).t(".\n")
        doc.t(f"P: Return in {self.rng.randint(1, 8)} weeks. Seen with Dr. ")
        doc.p("PROVIDER", self.doctor(), ignore=True).t(".\n")
        return doc

    def nursing_handover(self) -> Doc:
        """HELD-OUT template (test split only).  Written before any test results were seen,
        with cues and formats the rules were never developed against."""
        doc, c = Doc(), self.choice_clinic()
        sex, first, last = self._sex_name()
        d = self.dob_date()
        rel, rel_first = self.choice(RELATIONS), self.fake.first_name()
        rel_last = self.rng.choice([last, self.fake.last_name()])
        doc.t(
            f"NURSING HANDOVER (synthetic) - Ward {self.rng.randint(2, 9)}{self.choice(['A', 'B'])}, bed {self.rng.randint(1, 30)}\n"
        )
        doc.t("Pt ").p("NAME", f"{first} {last}").t(f", {self.rng.randint(19, 94)}{sex}.\n")
        doc.t("dob ").p("DATE_OF_BIRTH", f"{d.day:02d}-{MONTHS[d.month - 1][:3]}-{d.year}").t("   hcn ").p(
            "OHIP_NUMBER", self.ohip()
        ).t("\n")
        doc.t("NOK ").p("NAME", f"{rel_first} {rel_last}").t(f" ({rel}) cell ").p("PHONE", self.phone()).t("\n")
        street = self.street(rare_ok=False)
        doc.t("Home: ").p("ADDRESS", street.lower() if self.rng.random() < 0.5 else street).t(f", {self.fake.city()}  ")
        doc.p("POSTAL_CODE", self.postal()).t("\n\n")
        doc.p("NAME", first).t(" settled overnight, pain 3/10. ")
        doc.t(f"{rel.capitalize()} ").p("NAME", rel_first).t(" called at 0600 asking about discharge. ")
        doc.t("Spoke w/ ").p("NAME", f"{rel_first} {rel_last}").t(" re: transport.\n")
        if self.rng.random() < 0.5:
            doc.t("Email updates to family: ").p("EMAIL", self.email(rel_first, rel_last)).t("\n")
        doc.t(f"Pharmacy {c.phone}. {self.noise_line()}\n")
        doc.t("Charted by RN ").p("PROVIDER", self.doctor(), ignore=True).t("\n")
        return doc

    def choice_clinic(self) -> Clinic:
        return self.rng.choice(self.clinics)

    def document(self, i: int) -> dict[str, Any]:
        builders = [self.discharge_summary, self.referral_letter, self.lab_report, self.progress_note]
        if self.held_out and i % 5 == 4:
            builder = self.nursing_handover  # 20% of the test split
        else:
            builder = builders[i % len(builders)]
        doc = builder()
        return {
            "id": i,
            "type": builder.__name__,
            "held_out": builder == self.nursing_handover,
            "text": doc.text(),
            "spans": doc.spans,
        }

    def clinic_terms(self) -> list[str]:
        """What a clinic would put on its "never remove" list: its own public contact details."""
        terms: list[str] = []
        for c in self.clinics:
            terms += [c.phone, c.fax, c.address, c.postal]
        return terms


def generate_split(seed: int, n: int, held_out: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    gen = Generator(seed, held_out=held_out)
    docs = [gen.document(i) for i in range(n)]
    for d in docs:
        for s in d["spans"]:
            assert d["text"][s["start"] : s["end"]] == s["text"], "span bookkeeping error"
    return docs, gen.clinic_terms()


SPLITS = {"dev": (101, 200), "test": (202, 500)}
QUICK = {"dev": (101, 20), "test": (202, 60)}
INJECTION_SPLITS = {"dev": (303, 100), "test": (404, 160)}  # per class (benign, malicious)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", type=Path, default=DATA_DIR)
    args = ap.parse_args(argv)
    for split, (seed, n) in (QUICK if args.quick else SPLITS).items():
        docs, terms = generate_split(seed, n, held_out=(split == "test"))
        write_jsonl(args.out / f"phi_{split}.jsonl", docs)
        (args.out / f"clinic_never_remove_{split}.txt").write_text("\n".join(terms) + "\n", encoding="utf-8")
        n_spans = sum(len([s for s in d["spans"] if not s.get("ignore")]) for d in docs)
        print(f"phi_{split}: {len(docs)} documents, {n_spans} labelled identifiers")
    for split, (seed, n) in INJECTION_SPLITS.items():
        rows = generate_injection_split(seed, n if not args.quick else max(30, n // 4), held_out=(split == "test"))
        write_jsonl(args.out / f"injection_{split}.jsonl", rows)
        print(
            f"injection_{split}: {sum(r['label'] == 0 for r in rows)} benign, {sum(r['label'] == 1 for r in rows)} malicious"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
