"""Centres fictifs : chacun met en page un dossier avec son propre gabarit.

Les gabarits imitent la diversité des fiches réelles (export de dossier communicant,
courrier, formulaire à cocher, fiche compacte, export texte) sans reprendre aucun
document existant. Les établissements et réseaux sont inventés.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .model import (
    FICTITIOUS_BANNER,
    Banner,
    Block,
    Checklist,
    Document,
    FakeCase,
    Fields,
    Heading,
    Paragraph,
    Style,
    Table,
    Title,
)
from .pathologies import PATHOLOGIES

MONTHS = (
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre"
).split()


def d_num(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def d_long(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def d_iso(d: date) -> str:
    return d.isoformat()


@dataclass(frozen=True)
class Center:
    id: str
    name: str
    network: str
    address: str
    style: Style
    layout: Callable[["Center", FakeCase], list[Block]]

    def render(self, case: FakeCase) -> Document:
        return Document(
            case=case,
            style=self.style,
            header=f"{self.name} | {self.network}",
            footer=f"Document fictif | {case.case_id}",
            blocks=[Banner(FICTITIOUS_BANNER), *self.layout(self, case)],
        )


def _item_table(case: FakeCase, date_fmt: Callable[[date], str]) -> Table:
    rows = [
        [
            date_fmt(i.exam_date(case.meeting_date)),
            i.label + (" (externe)" if i.external else ""),
            i.result,
        ]
        for i in sorted(case.items, key=lambda i: i.days_before, reverse=True)
    ]
    return Table(["Date", "Examen", "Résultat"], rows)


def _antecedents(case: FakeCase) -> str:
    return ", ".join(case.patient.comorbidities) or "Aucun antécédent notable"


def _treatments(case: FakeCase) -> str:
    return ", ".join(case.patient.treatments) or "Aucun traitement au long cours"


def _participants(case: FakeCase) -> Table:
    return Table(
        ["Spécialité", "Nom"], [[s, p.full_name] for s, p in case.participants]
    )


# --- Gabarits -----------------------------------------------------------------------


def layout_dcc(center: Center, case: FakeCase) -> list[Block]:
    """Export de type dossier communicant de cancérologie, très structuré en tableaux."""
    p = case.patient
    blocks: list[Block] = [
        Title("FICHE RCP", f"{case.meeting_type} du {d_num(case.meeting_date)}"),
        Heading("Identification du patient"),
        Fields(
            [
                ("Nom de naissance", p.last_name),
                ("Prénom", p.first_name),
                ("Sexe", "Féminin" if p.sex == "F" else "Masculin"),
                ("Date de naissance", f"{d_num(p.birth_date)} ({case.age} ans)"),
                ("Adresse", f"{p.address}, {p.postcode} {p.city}"),
                ("IPP", p.ipp),
            ],
            columns=2,
        ),
        Heading("Médecins"),
        Fields(
            [
                ("Médecin traitant", case.gp.full_name),
                ("Médecin demandeur", case.requester.full_name),
                ("Médecin présentateur", case.presenter.full_name),
            ]
        ),
        Heading("Diagnostic"),
        Fields(
            [
                ("Localisation (CIM-10)", f"{case.icd10} — {case.diagnosis}"),
                ("Classification", case.tnm),
                (
                    "Motif de présentation",
                    "Décision thérapeutique" if case.stage == "pre" else "Avis rendu",
                ),
            ]
        ),
        Heading("Histoire de la maladie"),
        Paragraph(case.history),
        Heading("Antécédents et traitements"),
        Fields(
            [("Antécédents", _antecedents(case)), ("Traitements", _treatments(case))]
        ),
        Heading("Examens"),
        _item_table(case, d_num),
        Heading("Question posée à la RCP"),
        Paragraph(case.question, bold=True),
    ]
    if case.stage == "post":
        blocks += [
            Heading("Proposition de la RCP"),
            Paragraph(case.decision),
            Heading("Participants"),
            _participants(case),
        ]
    return blocks


def layout_letter(center: Center, case: FakeCase) -> list[Block]:
    """Courrier narratif, typique d'un compte rendu adressé au médecin traitant."""
    p = case.patient
    born, presented = ("née", "présentée") if p.sex == "F" else ("né", "présenté")
    intro = (
        f"{p.title} {p.first_name} {p.last_name}, {born} le {d_long(p.birth_date)}, demeurant "
        f"{p.address} à {p.city}, est {presented} en {case.meeting_type} le {d_long(case.meeting_date)} "
        f"par le {case.presenter.full_name}."
    )
    exams = " ".join(
        f"{i.label} du {d_long(i.exam_date(case.meeting_date))} : {i.result}"
        for i in case.items
    )
    blocks: list[Block] = [
        Paragraph(f"{center.address}\nLe {d_long(case.meeting_date)}"),
        Paragraph(f"À l'attention du {case.gp.full_name}, médecin traitant"),
        Title(
            "Compte rendu de réunion de concertation pluridisciplinaire"
            if case.stage == "post"
            else "Demande d'inscription en réunion de concertation pluridisciplinaire"
        ),
        Paragraph("Cher confrère,"),
        Paragraph(intro),
        Paragraph(
            f"Antécédents : {_antecedents(case)}. Traitement habituel : {_treatments(case)}."
        ),
        Paragraph(f"Histoire : {case.history}"),
        Paragraph(f"Bilan : {exams}" if exams else "Bilan : aucun examen transmis."),
        Paragraph(f"Au total : {case.diagnosis}, {case.tnm} (CIM-10 {case.icd10})."),
        Paragraph(f"Question : {case.question}", italic=True),
    ]
    if case.stage == "post":
        names = ", ".join(f"{p.full_name} ({s})" for s, p in case.participants)
        blocks += [
            Paragraph(f"Proposition retenue : {case.decision}", bold=True),
            Paragraph(f"Médecins présents : {names}."),
        ]
    blocks.append(Paragraph(f"Bien confraternellement,\n{case.requester.full_name}"))
    return blocks


def layout_checklist(center: Center, case: FakeCase) -> list[Block]:
    """Formulaire de centre de lutte contre le cancer, avec liste de pièces à cocher."""
    p = case.patient
    spec = PATHOLOGIES[case.pathology_id]
    present = {i.id for i in case.items}
    blocks: list[Block] = [
        Title(f"{case.meeting_type}", "Formulaire de présentation de dossier"),
        Fields(
            [
                ("Patient(e)", f"{p.last_name} {p.first_name}"),
                ("Né(e) le", d_num(p.birth_date)),
                ("N° dossier", p.ipp),
                ("Date de la réunion", d_num(case.meeting_date)),
                ("Médecin référent", case.requester.full_name),
                ("Médecin traitant", case.gp.full_name),
            ],
            columns=2,
        ),
        Heading("Pièces du dossier"),
        Checklist([(s.label, s.id in present) for s in spec.items]),
        Heading("Données cliniques"),
        Fields(
            [
                ("Diagnostic", case.diagnosis),
                ("Stade", case.tnm),
                ("Comorbidités", _antecedents(case)),
                ("Traitements en cours", _treatments(case)),
                ("Contexte", case.history),
            ]
        ),
        Heading("Résultats"),
        Fields(
            [
                (i.label, f"{i.result} ({d_num(i.exam_date(case.meeting_date))})")
                for i in case.items
            ]
        ),
        Heading("Question"),
        Paragraph(case.question),
    ]
    if case.stage == "post":
        blocks += [
            Heading("Avis de la RCP"),
            Paragraph(case.decision, bold=True),
            Heading("Quorum"),
            _participants(case),
        ]
    return blocks


def layout_compact(center: Center, case: FakeCase) -> list[Block]:
    """Fiche courte de clinique privée, sur deux colonnes."""
    p = case.patient
    blocks: list[Block] = [
        Title(f"RCP — {d_long(case.meeting_date)}"),
        Fields(
            [
                ("Patient", p.full_name),
                ("Âge", f"{case.age} ans"),
                ("DDN", d_num(p.birth_date)),
                ("Ville", f"{p.postcode} {p.city}"),
                ("Adressé par", case.requester.full_name),
                ("MT", case.gp.full_name),
                ("Pathologie", case.diagnosis),
                ("TNM", case.tnm),
            ],
            columns=2,
        ),
        Paragraph(f"ATCD : {_antecedents(case)}. TTT : {_treatments(case)}."),
        Paragraph(f"HDM : {case.history}"),
        _item_table(case, d_num),
        Paragraph(f"Question : {case.question}", bold=True),
    ]
    if case.stage == "post":
        names = " ; ".join(f"{s} : {p.full_name}" for s, p in case.participants)
        blocks += [
            Paragraph(f"Décision : {case.decision}", bold=True),
            Paragraph(f"Présents — {names}"),
        ]
    return blocks


def layout_export(center: Center, case: FakeCase) -> list[Block]:
    """Export texte brut d'un logiciel métier : libellés en capitales, dates ISO."""
    p = case.patient
    lines = [
        f"PATIENT: {p.last_name}, {p.first_name}",
        f"SEXE: {p.sex}    DDN: {d_iso(p.birth_date)}    IPP: {p.ipp}",
        f"ADRESSE: {p.address} {p.postcode} {p.city}",
        f"MEDECIN_TRAITANT: {case.gp.full_name}",
        f"DEMANDEUR: {case.requester.full_name}",
        f"REUNION: {case.meeting_type.upper()}    DATE: {d_iso(case.meeting_date)}",
        f"CIM10: {case.icd10}    DIAGNOSTIC: {case.diagnosis}    TNM: {case.tnm}",
        f"ANTECEDENTS: {_antecedents(case)}",
        f"TRAITEMENTS: {_treatments(case)}",
        f"HISTOIRE: {case.history}",
    ]
    for i in case.items:
        lines.append(
            f"EXAMEN[{d_iso(i.exam_date(case.meeting_date))}] {i.label.upper()}: {i.result}"
        )
    lines.append(f"QUESTION: {case.question}")
    if case.stage == "post":
        lines.append(f"PROPOSITION: {case.decision}")
        lines += [f"PARTICIPANT: {s} | {p.full_name}" for s, p in case.participants]
    return [
        Title(f"EXPORT RCP {case.case_id.upper()}"),
        *[Paragraph(line) for line in lines],
    ]


CENTERS: dict[str, Center] = {
    c.id: c
    for c in (
        Center(
            "chu_valcourt",
            "CHU de Valcourt",
            "Réseau régional de cancérologie Val-de-Brume",
            "1 place de l'Hôtel-Dieu, 99100 Valcourt",
            Style("sans", "1F4E79"),
            layout_dcc,
        ),
        Center(
            "ch_saint_aubin",
            "Centre hospitalier de Saint-Aubin-des-Landes",
            "3C Landes-et-Marais",
            "12 rue des Écluses, 99200 Saint-Aubin-des-Landes",
            Style("serif", "5B2C6F"),
            layout_letter,
        ),
        Center(
            "institut_tilleuls",
            "Institut de cancérologie des Tilleuls",
            "Réseau Onco-Ouest fictif",
            "40 avenue des Tilleuls, 99300 Bellerive",
            Style("sans", "117864", uppercase_headings=True),
            layout_checklist,
        ),
        Center(
            "clinique_belvedere",
            "Clinique du Belvédère",
            "3C Coteaux-du-Sud",
            "8 chemin du Belvédère, 99400 Montclar",
            Style("sans", "B9770E"),
            layout_compact,
        ),
        Center(
            "hopital_ardoise",
            "Hôpital Nord de l'Ardoise",
            "Réseau Ardoise Santé",
            "3 boulevard de l'Ardoise, 99500 Pierrefonte",
            Style("mono", "444444"),
            layout_export,
        ),
    )
}
