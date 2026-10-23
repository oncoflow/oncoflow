"""Remplacement des entités détectées.

- ``placeholder`` : chaque entité devient « [NOM] », « [DATE_NAISSANCE] »...
- ``surrogate`` : remplacement par des valeurs fictives cohérentes dans le document
  (une même valeur reçoit toujours le même substitut) et décalage de toutes les dates
  d'un même nombre de jours, pour préserver les intervalles cliniques (délais, âge).

La table de correspondance renvoyée permet de ré-identifier : elle est aussi sensible
que le document d'origine.
"""

import hashlib
import random
import re
from datetime import date, timedelta

from faker import Faker

from .entities import Span

MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
_MONTH_INDEX = {m: i + 1 for i, m in enumerate(MONTHS)} | {"fevrier": 2, "aout": 8, "decembre": 12}


def _shift_date(text: str, days: int) -> str | None:
    """Décale une date en conservant son format ; None si le format n'est pas reconnu."""
    try:
        return _shift_known_formats(text, days)
    except ValueError:  # date impossible, ex. 31/02/2026
        return None


def _shift_known_formats(text: str, days: int) -> str | None:
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text):
        d = date(int(m[1]), int(m[2]), int(m[3])) + timedelta(days=days)
        return d.isoformat()
    if m := re.fullmatch(r"(\d{1,2})([/.-])(\d{1,2})\2(\d{4})", text):
        d = date(int(m[4]), int(m[3]), int(m[1])) + timedelta(days=days)
        return f"{d.day:02d}{m[2]}{d.month:02d}{m[2]}{d.year}"
    if m := re.fullmatch(r"(\d{1,2})(?:er)?\s+(\w+)\s+(\d{4})", text, re.IGNORECASE):
        month = _MONTH_INDEX.get(m[2].casefold())
        if month:
            d = date(int(m[3]), month, int(m[1])) + timedelta(days=days)
            return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return None


class Surrogates:
    """Valeurs de remplacement reproductibles pour un document."""

    def __init__(self, seed: str):
        digest = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        self.rng = random.Random(digest)
        self.fake = Faker("fr_FR")
        self.fake.seed_instance(digest % 2**32)
        self.date_shift = self.rng.choice([-1, 1]) * self.rng.randint(30, 365)
        self.cache: dict[tuple[str, str], str] = {}

    def _new(self, label: str, original: str) -> str:
        f = self.fake
        match label:
            case "NOM":
                value = f.last_name()
                return value.upper() if original.isupper() else value
            case "PRENOM":
                value = f.first_name()
                return value.upper() if original.isupper() else value
            case "DATE" | "DATE_NAISSANCE":
                return _shift_date(original.strip(), self.date_shift) or f"[{label}]"
            case "ADRESSE":
                return f.street_address()
            case "ZIP":
                return f.postcode()
            case "VILLE":
                return f.city()
            case "TEL":
                return f.phone_number()
            case "MAIL":
                return f.email()
            case "HOPITAL":
                return f"Hôpital {f.city()}"
            case "IPP" | "NDA" | "SECU":
                return "".join(str(self.rng.randint(0, 9)) if c.isdigit() else c for c in original)
            case _:
                return f"[{label}]"

    def get(self, label: str, original: str) -> str:
        key = (label, original.casefold())
        if key not in self.cache:
            self.cache[key] = self._new(label, original)
        return self.cache[key]


def pseudonymize(text: str, spans: list[Span], strategy: str = "placeholder", seed: str = "") -> tuple[str, list[dict]]:
    """Renvoie le texte pseudonymisé et la table de correspondance."""
    surrogates = Surrogates(seed or text) if strategy == "surrogate" else None
    out, mapping, cursor = [], [], 0
    for span in sorted(spans, key=lambda s: s.start):
        original = text[span.start : span.end]
        replacement = surrogates.get(span.label, original) if surrogates else f"[{span.label}]"
        out += [text[cursor : span.start], replacement]
        mapping.append({"label": span.label, "original": original, "replacement": replacement, "start": span.start})
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out), mapping
