"""Entités identifiantes et fusion des détections."""

from dataclasses import asdict, dataclass

# Étiquettes d'eds-pseudo, plus AUTRE pour tout identifiant hors catégorie.
LABELS: dict[str, str] = {
    "NOM": "Nom de famille",
    "PRENOM": "Prénom",
    "DATE_NAISSANCE": "Date de naissance",
    "DATE": "Date",
    "ADRESSE": "Adresse",
    "ZIP": "Code postal",
    "VILLE": "Ville",
    "TEL": "Téléphone",
    "MAIL": "Courriel",
    "IPP": "Identifiant patient",
    "NDA": "Identifiant de séjour",
    "SECU": "N° de sécurité sociale",
    "HOPITAL": "Établissement",
    "AUTRE": "Autre identifiant",
}

# Niveau de confiance des sources : en cas de chevauchement, le niveau le plus haut
# l'emporte, puis la détection la plus longue, puis l'étiquette la plus précise.
SOURCE_TIER = {
    "manuel": 3,
    "lexique": 2,
    "repere": 2,
    "eds-pseudo-ml": 1,
    "eds-pseudo": 1,
    "regle": 1,
    "propagation": 1,
}

SOURCE_NAMES = {
    "manuel": "Annotation manuelle",
    "lexique": "Lexique appris",
    "repere": "Repère de champ (ex. « Nom : »)",
    "eds-pseudo-ml": "Modèle eds-pseudo",
    "eds-pseudo": "Règles eds-pseudo",
    "regle": "Règle complémentaire",
    "propagation": "Autre occurrence d'un identifiant détecté",
}

# Étiquette la plus précise à rang égal (ex. DATE_NAISSANCE plutôt que DATE).
LABEL_PRIORITY = {"DATE_NAISSANCE": 2, "ADRESSE": 1}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str
    source: str
    text: str = ""

    def key(self) -> tuple[int, int]:
        return (self.start, self.end)

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end

    def rank(self) -> tuple[int, int, int]:
        return (
            SOURCE_TIER.get(self.source, 0),
            self.end - self.start,
            LABEL_PRIORITY.get(self.label, 0),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Span":
        return cls(**{k: data[k] for k in ("start", "end", "label", "source", "text") if k in data})


def resolve(spans: list[Span], text: str) -> list[Span]:
    """Supprime les chevauchements en gardant la détection de meilleur rang."""
    kept: list[Span] = []
    for span in sorted(spans, key=lambda s: s.rank(), reverse=True):
        if span.end <= span.start or not text[span.start : span.end].strip():
            continue
        if not any(span.overlaps(k) for k in kept):
            kept.append(Span(span.start, span.end, span.label, span.source, text[span.start : span.end]))
    return sorted(kept, key=lambda s: s.start)
