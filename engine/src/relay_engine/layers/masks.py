"""Masks that keep the shape of personal data.

Each mask is stable: within one engine process, the same value always gets
the same mask, so keys and links between tables still match. The key of the
HMAC is born with the process and written nowhere.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta

KEY = secrets.token_bytes(32)

KINDS = (
    "pseudonym", "email", "phone", "first_name", "last_name", "full_name", "address", "city",
    "postal_code", "birth_date", "iban", "ssn", "blank",
)

FIRST_NAMES = (
    "Alice", "Bruno", "Camille", "David", "Emma", "Fabien", "Gaëlle", "Hugo", "Inès", "Jules",
    "Karim", "Léa", "Marc", "Nina", "Olivier", "Paula", "Quentin", "Rose", "Samuel", "Théa",
    "Ugo", "Violette", "William", "Yasmine", "Zoé", "Adrien", "Bérénice", "Clément", "Diane",
    "Étienne", "Flora", "Gabriel",
)
LAST_NAMES = (
    "Arnaud", "Bertin", "Carpentier", "Delorme", "Esnault", "Fabre", "Garnier", "Hamon",
    "Imbert", "Jacquet", "Klein", "Lemaire", "Marchand", "Noël", "Ollivier", "Perrin",
    "Quéré", "Renaud", "Sauvage", "Tessier", "Vasseur", "Weber", "Yvon", "Zimmer", "Aubry",
    "Besnard", "Collin", "Dumont", "Étienne", "Fleury", "Gilbert", "Hubert",
)
CITIES = (
    "Lyon", "Nantes", "Rennes", "Lille", "Dijon", "Tours", "Angers", "Brest", "Metz", "Nancy",
    "Reims", "Limoges", "Poitiers", "Grenoble", "Annecy", "Pau", "Caen", "Rouen", "Amiens",
    "Besançon", "Orléans", "Nîmes", "Toulon", "Bayonne",
)
STREETS = (
    "rue des Lilas", "avenue de la Gare", "boulevard Voltaire", "rue du Moulin", "place du Marché",
    "chemin des Vignes", "rue de la République", "allée des Tilleuls", "rue Pasteur",
    "impasse des Roses", "quai de la Loire", "route de Paris",
)


def digest(value: str) -> bytes:
    stream = b""
    counter = 0
    while len(stream) < max(32, len(value) * 2):
        stream += hmac.new(KEY, f"{counter}:{value}".encode(), hashlib.sha256).digest()
        counter += 1
    return stream


def shape(value: str, keep: int = 0) -> str:
    """Letters stay letters in their case, digits stay digits, the rest stays as it is."""
    noise = digest(value)
    out = []
    for i, char in enumerate(value):
        byte = noise[i]
        if i < keep or not char.isalnum():
            out.append(char)
        elif char.isdigit():
            out.append(str(byte % 10))
        elif char.isupper():
            out.append(chr(ord("A") + byte % 26))
        else:
            out.append(chr(ord("a") + byte % 26))
    return "".join(out)


def _pick(options: tuple[str, ...], value: str, salt: str) -> str:
    return options[digest(salt + value)[0] % len(options)]


def _phone(value: str) -> str:
    start = len(value) - len(value.lstrip("+ "))
    return shape(value, keep=start + 2)


def _iban(value: str) -> str:
    compact = value.replace(" ", "").upper()
    country = compact[:2] if compact[:2].isalpha() else "FR"
    bban = shape(compact[4:]).upper() or "0" * 23
    number = "".join(str(int(c, 36)) for c in bban + country + "00")
    iban = f"{country}{98 - int(number) % 97:02d}{bban}"
    if " " in value:
        return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))
    return iban


def _day(value: str) -> int:
    return int.from_bytes(digest(value)[:2]) % 365


def _birth(value: str) -> str:
    try:
        day = date.fromisoformat(value[:10])
    except ValueError:
        return shape(value)
    return (date(day.year, 1, 1) + timedelta(days=_day(value))).isoformat() + value[10:]


def mask_text(value: str, kind: str) -> str:
    if kind == "email":
        return f"user-{digest(value).hex()[:8]}@example.com"
    if kind == "phone":
        return _phone(value)
    if kind == "first_name":
        return _pick(FIRST_NAMES, value, "first")
    if kind == "last_name":
        return _pick(LAST_NAMES, value, "last")
    if kind == "full_name":
        return f"{_pick(FIRST_NAMES, value, 'first')} {_pick(LAST_NAMES, value, 'last')}"
    if kind == "address":
        return f"{digest(value)[0] % 120 + 1} {_pick(STREETS, value, 'street')}"
    if kind == "city":
        return _pick(CITIES, value, "city")
    if kind == "iban":
        return _iban(value)
    if kind == "birth_date":
        return _birth(value)
    return shape(value)


def mask_date(value: date) -> date:
    moved = date(value.year, 1, 1) + timedelta(days=_day(value.isoformat()))
    if isinstance(value, datetime):
        return datetime.combine(moved, value.time())
    return moved
