"""Modèle de données du générateur de fiches RCP fictives.

Un dossier (`FakeCase`) est d'abord généré de façon neutre, puis chaque centre le
met en page sous forme de blocs (`Block`) que les moteurs Word et PDF savent rendre.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

FICTITIOUS_BANNER = (
    "DOCUMENT FICTIF — généré automatiquement pour les tests d'Oncoflow. "
    "Aucune donnée réelle : toute ressemblance avec une personne existante serait fortuite."
)


@dataclass
class Person:
    first_name: str
    last_name: str
    title: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.title} {self.first_name} {self.last_name}".strip()


@dataclass
class Patient(Person):
    sex: str = "F"
    birth_date: date = date(1950, 1, 1)
    address: str = ""
    postcode: str = ""
    city: str = ""
    ipp: str = ""
    weight_kg: float = 70.0
    height_cm: int = 170
    weight_loss_pct: int = 0
    ecog: int = 0
    comorbidities: list[str] = field(default_factory=list)
    treatments: list[str] = field(default_factory=list)

    def age_at(self, when: date) -> int:
        before_birthday = (when.month, when.day) < (
            self.birth_date.month,
            self.birth_date.day,
        )
        return when.year - self.birth_date.year - before_birthday


@dataclass
class Item:
    """Élément du dossier (examen, résultat, évaluation) attendu pour la pathologie."""

    id: str
    label: str
    result: str
    days_before: int = 0  # ancienneté par rapport à la date de réunion
    required: bool = True
    max_age_days: int | None = None
    external: bool = False  # réalisé hors centre (relecture éventuelle)

    def exam_date(self, meeting: date) -> date:
        return meeting - timedelta(days=self.days_before)

    @property
    def outdated(self) -> bool:
        return self.max_age_days is not None and self.days_before > self.max_age_days


@dataclass
class Request:
    """Demande préalable attendue avant la discussion (vérité terrain)."""

    kind: str
    reason: str


@dataclass
class FakeCase:
    case_id: str
    center_id: str
    pathology_id: str
    meeting_type: str
    meeting_date: date
    stage: str  # "pre" (fiche de demande) ou "post" (compte rendu avec décision)
    patient: Patient
    gp: Person
    requester: Person
    presenter: Person
    icd10: str
    diagnosis: str
    tnm: str
    history: str
    question: str
    items: list[Item]
    missing: list[Item]
    participants: list[tuple[str, Person]]
    required_specialties: list[str]
    decision: str = ""
    requests: list[Request] = field(default_factory=list)

    @property
    def age(self) -> int:
        return self.patient.age_at(self.meeting_date)

    @property
    def bmi(self) -> float:
        return round(self.patient.weight_kg / (self.patient.height_cm / 100) ** 2, 1)

    @property
    def missing_specialties(self) -> list[str]:
        present = {specialty for specialty, _ in self.participants}
        return [s for s in self.required_specialties if s not in present]

    def ground_truth(self) -> dict:
        return {
            "case_id": self.case_id,
            "center": self.center_id,
            "pathology": self.pathology_id,
            "meeting_type": self.meeting_type,
            "meeting_date": self.meeting_date.isoformat(),
            "stage": self.stage,
            "patient": {
                "full_name": f"{self.patient.first_name} {self.patient.last_name}",
                "sex": self.patient.sex,
                "birth_date": self.patient.birth_date.isoformat(),
                "age": self.age,
                "ecog": self.patient.ecog,
                "weight_loss_pct": self.patient.weight_loss_pct,
            },
            "icd10": self.icd10,
            "diagnosis": self.diagnosis,
            "tnm": self.tnm,
            "present_items": [i.id for i in self.items],
            "missing_items": [
                {"id": i.id, "label": i.label, "required": i.required}
                for i in self.missing
            ],
            "outdated_items": [i.id for i in self.items if i.outdated],
            "complete": not any(i.required for i in self.missing)
            and not any(i.outdated for i in self.items),
            "expected_requests": [
                {"kind": r.kind, "reason": r.reason} for r in self.requests
            ],
            "required_specialties": self.required_specialties,
            "participants": [s for s, _ in self.participants],
            "missing_specialties": self.missing_specialties
            if self.stage == "post"
            else [],
        }


# --- Blocs de mise en page -------------------------------------------------------


@dataclass
class Block:
    pass


@dataclass
class Banner(Block):
    text: str


@dataclass
class Title(Block):
    text: str
    subtitle: str = ""


@dataclass
class Heading(Block):
    text: str


@dataclass
class Paragraph(Block):
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Fields(Block):
    """Paires libellé / valeur, sur une ou deux colonnes."""

    pairs: list[tuple[str, str]]
    columns: int = 1


@dataclass
class Table(Block):
    header: list[str]
    rows: list[list[str]]


@dataclass
class Checklist(Block):
    entries: list[tuple[str, bool]]


@dataclass
class Style:
    font: str  # "sans", "serif" ou "mono"
    accent: str  # couleur hexadécimale sans '#'
    uppercase_headings: bool = False


@dataclass
class Document:
    case: FakeCase
    style: Style
    header: str
    footer: str
    blocks: list[Block]
