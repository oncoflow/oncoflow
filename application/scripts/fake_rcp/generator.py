"""Génération de dossiers RCP fictifs, reproductibles à partir d'une graine."""

import random
from datetime import date, timedelta

from faker import Faker

from .model import FakeCase, Item, Patient, Person, Request
from .pathologies import COMORBIDITIES, PATHOLOGIES, TREATMENTS, PathologySpec

ECOG_LABELS = {
    0: "OMS 0 (activité normale)",
    1: "OMS 1 (symptomatique, ambulatoire)",
    2: "OMS 2 (alité moins de 50 % du temps)",
    3: "OMS 3 (alité plus de 50 % du temps)",
}


class CaseGenerator:
    def __init__(
        self, seed: int = 0, missing_rate: float = 0.2, outdated_rate: float = 0.1
    ):
        self.rng = random.Random(seed)
        self.fake = Faker("fr_FR")
        self.fake.seed_instance(seed)
        self.missing_rate = missing_rate
        self.outdated_rate = outdated_rate

    # --- personnes ------------------------------------------------------------

    def _doctor(self) -> Person:
        return Person(self.fake.first_name(), self.fake.last_name().upper(), "Dr")

    def _patient(self, spec: PathologySpec, meeting: date) -> Patient:
        sex = self.rng.choice(spec.sexes)
        first = (
            self.fake.first_name_female() if sex == "F" else self.fake.first_name_male()
        )
        age = self.rng.randint(*spec.age_range)
        birth = meeting - timedelta(days=age * 365 + self.rng.randint(0, 364))
        height = (
            self.rng.randint(152, 172) if sex == "F" else self.rng.randint(162, 188)
        )
        return Patient(
            first_name=first,
            last_name=self.fake.last_name().upper(),
            title="Mme" if sex == "F" else "M.",
            sex=sex,
            birth_date=birth,
            address=self.fake.street_address(),
            postcode=self.fake.postcode(),
            city=self.fake.city(),
            ipp=f"{self.rng.randint(10**8, 10**9 - 1)}",
            weight_kg=round(self.rng.uniform(45, 98), 1),
            height_cm=height,
            weight_loss_pct=self.rng.choice((0, 0, 3, 5, 8, 12, 15)),
            ecog=self.rng.choices((0, 1, 2, 3), weights=(4, 4, 2, 1))[0],
            comorbidities=self.rng.sample(COMORBIDITIES, self.rng.randint(0, 3)),
            treatments=self.rng.sample(TREATMENTS, self.rng.randint(0, 3)),
        )

    # --- dossier --------------------------------------------------------------

    def generate(
        self,
        case_id: str,
        center_id: str,
        pathology_id: str,
        stage: str | None = None,
        meeting_date: date | None = None,
    ) -> FakeCase:
        spec = PATHOLOGIES[pathology_id]
        meeting = meeting_date or date(2026, 1, 5) + timedelta(
            days=7 * self.rng.randint(0, 40)
        )
        stage = stage or self.rng.choice(("pre", "post"))
        patient = self._patient(spec, meeting)
        scenario = self.rng.choice(spec.scenarios)

        values = {
            "ecog": ECOG_LABELS[patient.ecog],
            "weight": patient.weight_kg,
            "weight_loss": patient.weight_loss_pct,
            "size": self.rng.randint(12, 48),
            "marker": self.rng.choice((18, 37, 145, 380, 1250)),
            "marker_low": self.rng.choice((2.1, 4.8, 12, 35, 210)),
            "psa": self.rng.choice((6.4, 8.9, 12.3, 18.0)),
            "weeks": self.rng.randint(3, 12),
            "pack_years": self.rng.choice((15, 30, 45)),
        }
        values["bmi"] = round(patient.weight_kg / (patient.height_cm / 100) ** 2, 1)

        items, missing = [], []
        for item_spec in spec.items:
            result = self.rng.choice(
                scenario.results.get(item_spec.id, item_spec.results)
            ).format(**values)
            days = self.rng.randint(*item_spec.days)
            if item_spec.max_age_days and self.rng.random() < self.outdated_rate:
                days = item_spec.max_age_days + self.rng.randint(10, 60)
            item = Item(
                id=item_spec.id,
                label=item_spec.label,
                result=result,
                days_before=days,
                required=item_spec.required,
                max_age_days=item_spec.max_age_days,
                external=item_spec.may_be_external and self.rng.random() < 0.3,
            )
            (missing if self.rng.random() < self.missing_rate else items).append(item)

        participants = []
        if stage == "post":
            specialties = list(spec.required_specialties)
            if self.rng.random() < 0.2:  # quorum incomplet
                specialties.remove(self.rng.choice(specialties))
            specialties += self.rng.sample(
                spec.optional_specialties, min(len(spec.optional_specialties), 2)
            )
            participants = [(s, self._doctor()) for s in specialties]

        case = FakeCase(
            case_id=case_id,
            center_id=center_id,
            pathology_id=pathology_id,
            meeting_type=spec.meeting_type,
            meeting_date=meeting,
            stage=stage,
            patient=patient,
            gp=self._doctor(),
            requester=self._doctor(),
            presenter=self._doctor(),
            icd10=spec.icd10,
            diagnosis=spec.diagnosis,
            tnm=scenario.tnm,
            history=self.rng.choice(spec.history).format(**values),
            question=scenario.question,
            items=items,
            missing=missing,
            participants=participants,
            required_specialties=list(spec.required_specialties),
            decision=self.rng.choice(scenario.decisions) if stage == "post" else "",
        )
        case.requests = expected_requests(case, surgical=scenario.surgical)
        return case


def expected_requests(case: FakeCase, surgical: bool) -> list[Request]:
    """Demandes préalables attendues, selon des règles simples et explicites.

    Les règles ne s'appuient que sur des informations visibles dans le document généré.
    """
    requests = []
    patient = case.patient
    if case.age >= 75:
        requests.append(
            Request(
                "oncogeriatrie",
                f"Âge {case.age} ans (≥ 75) : évaluation oncogériatrique",
            )
        )
    visible = {item.id for item in case.items}
    if "nutrition" in visible and (patient.weight_loss_pct >= 10 or case.bmi < 18.5):
        requests.append(
            Request(
                "nutrition",
                f"Perte de poids {patient.weight_loss_pct} %, IMC {case.bmi} : évaluation nutritionnelle",
            )
        )
    for item in case.items:
        if item.external:
            requests.append(
                Request(
                    "relecture_radiologique", f"{item.label} réalisé(e) hors centre"
                )
            )
        if item.outdated:
            requests.append(
                Request(
                    "actualisation_examen",
                    f"{item.label} datant de plus de {item.max_age_days} jours",
                )
            )
    for item in case.missing:
        if item.required:
            requests.append(
                Request("complement_bilan", f"{item.label} absent du dossier")
            )
    frail = (
        ("performance_status" in visible and patient.ecog >= 2)
        or case.age >= 75
        or any("Cardiopathie" in c for c in patient.comorbidities)
    )
    if surgical and frail:
        requests.append(
            Request(
                "consultation_anesthesie",
                "Indication chirurgicale chez un patient fragile",
            )
        )
    return requests
