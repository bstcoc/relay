from __future__ import annotations

import re
from datetime import date

from relay_engine.layers.masks import mask_date, mask_text


def test_a_mask_keeps_the_shape_and_never_the_value() -> None:
    email = mask_text("ana.martin@acme.fr", "email")
    phone = mask_text("06 12 34 56 78", "phone")
    ssn = mask_text("1 85 05 78 006 084 36", "ssn")
    code = mask_text("AB-1234", "pseudonym")

    assert re.fullmatch(r"user-[0-9a-f]{8}@example\.com", email)
    assert re.fullmatch(r"06 \d\d \d\d \d\d \d\d", phone) and phone != "06 12 34 56 78"
    assert re.fullmatch(r"\d \d\d \d\d \d\d \d{3} \d{3} \d\d", ssn)
    assert re.fullmatch(r"[A-Z]{2}-\d{4}", code)
    assert len(mask_text("Ana Martin", "full_name").split()) == 2


def test_the_same_value_always_gets_the_same_mask() -> None:
    assert mask_text("ana.martin@acme.fr", "email") == mask_text("ana.martin@acme.fr", "email")
    assert mask_text("ana.martin@acme.fr", "email") != mask_text("bo.lee@acme.fr", "email")


def test_a_masked_iban_is_still_a_valid_iban() -> None:
    iban = mask_text("FR76 3000 6000 0112 3456 7890 189", "iban")
    compact = iban.replace(" ", "")
    rearranged = compact[4:] + compact[:4]

    assert compact.startswith("FR") and len(compact) == 27
    assert int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def test_a_birth_date_stays_in_its_year() -> None:
    born = date(1985, 5, 17)

    assert mask_date(born).year == 1985
    assert mask_text("1985-05-17", "birth_date")[:4] == "1985"


def test_an_accented_letter_never_survives_a_mask() -> None:
    masked = mask_text("Hélène Ça", "pseudonym")

    assert len(masked) == len("Hélène Ça")
    assert not set("éèÇ") & set(masked)
    assert mask_text("69003", "postal_code").isdigit()
