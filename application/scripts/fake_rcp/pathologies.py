"""Catalogue de pathologies fictives (contenu plausible, non validé cliniquement).

Chaque pathologie décrit les éléments attendus dans un dossier complet, quelques
scénarios (stade, question posée, décisions possibles) et les spécialités requises.
Ces données servent uniquement à produire des documents de test.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ItemSpec:
    id: str
    label: str
    results: tuple[str, ...]
    required: bool = True
    max_age_days: int | None = None
    days: tuple[int, int] = (5, 40)
    may_be_external: bool = False


@dataclass(frozen=True)
class Scenario:
    tnm: str
    question: str
    decisions: tuple[str, ...]
    results: dict[str, tuple[str, ...]] = field(default_factory=dict)
    surgical: bool = False


@dataclass(frozen=True)
class PathologySpec:
    id: str
    meeting_type: str
    icd10: str
    diagnosis: str
    sexes: str
    age_range: tuple[int, int]
    history: tuple[str, ...]
    items: tuple[ItemSpec, ...]
    scenarios: tuple[Scenario, ...]
    required_specialties: tuple[str, ...]
    optional_specialties: tuple[str, ...] = ()


_PS = ItemSpec(
    "performance_status", "Indice de performance (OMS)", ("{ecog}",), days=(0, 10)
)
_WEIGHT = ItemSpec(
    "nutrition",
    "Poids / IMC / perte de poids",
    ("Poids {weight} kg, IMC {bmi}, perte de poids de {weight_loss} % en 6 mois",),
    days=(0, 15),
)

PATHOLOGIES: dict[str, PathologySpec] = {
    p.id: p
    for p in (
        PathologySpec(
            id="pancreas",
            meeting_type="RCP Cancérologie digestive",
            icd10="C25.0",
            diagnosis="Adénocarcinome de la tête du pancréas",
            sexes="FM",
            age_range=(52, 86),
            history=(
                (
                    "Ictère cutanéo-muqueux sans douleur révélateur, apparu il y a {weeks} semaines. "
                    "Drainage biliaire par prothèse endoscopique réalisé."
                ),
                (
                    "Douleurs épigastriques transfixiantes et amaigrissement depuis {weeks} semaines, "
                    "découverte d'un diabète récent."
                ),
            ),
            items=(
                ItemSpec(
                    "ct_tap",
                    "TDM thoraco-abdomino-pelvienne",
                    (
                        "Masse céphalique pancréatique de {size} mm, sans lésion secondaire visible.",
                    ),
                    max_age_days=28,
                    may_be_external=True,
                ),
                ItemSpec(
                    "eus_biopsy",
                    "Écho-endoscopie avec biopsie",
                    (
                        "Lésion hypoéchogène de {size} mm, ponction à l'aiguille fine réalisée.",
                    ),
                ),
                ItemSpec(
                    "histology",
                    "Anatomopathologie",
                    ("Adénocarcinome canalaire moyennement différencié.",),
                ),
                ItemSpec(
                    "ca19_9",
                    "CA 19-9",
                    ("{marker} UI/mL",),
                    required=False,
                    days=(2, 20),
                ),
                ItemSpec(
                    "liver_mri",
                    "IRM hépatique",
                    ("Absence de métastase hépatique.",),
                    required=False,
                    max_age_days=28,
                ),
                _PS,
                _WEIGHT,
            ),
            scenarios=(
                Scenario(
                    "cT2N0M0",
                    "Tumeur résécable : chirurgie d'emblée ou traitement néoadjuvant ?",
                    (
                        "Duodénopancréatectomie céphalique, puis chimiothérapie adjuvante par mFOLFIRINOX.",
                        "Chimiothérapie néoadjuvante par mFOLFIRINOX puis réévaluation en RCP.",
                    ),
                    surgical=True,
                ),
                Scenario(
                    "cT3N1M0 (borderline)",
                    "Tumeur borderline : stratégie néoadjuvante ?",
                    (
                        "Chimiothérapie néoadjuvante par mFOLFIRINOX 4 mois puis réévaluation.",
                    ),
                    results={
                        "ct_tap": (
                            "Contact veineux mésentérico-portal sur 180°, sans métastase.",
                        ),
                    },
                ),
                Scenario(
                    "cT4N1M1 (hépatique)",
                    "Maladie métastatique : quelle chimiothérapie de première ligne ?",
                    (
                        "Chimiothérapie palliative par FOLFIRINOX si état général conservé.",
                        "Gemcitabine et nab-paclitaxel, soins de support associés.",
                    ),
                    results={
                        "ct_tap": (
                            "Masse céphalique de {size} mm, multiples lésions hépatiques secondaires.",
                        ),
                    },
                ),
            ),
            required_specialties=(
                "Chirurgien digestif",
                "Oncologue médical",
                "Radiologue",
            ),
            optional_specialties=(
                "Gastro-entérologue",
                "Anatomopathologiste",
                "Radiothérapeute",
            ),
        ),
        PathologySpec(
            id="colon",
            meeting_type="RCP Cancérologie digestive",
            icd10="C18.7",
            diagnosis="Adénocarcinome du côlon sigmoïde",
            sexes="FM",
            age_range=(45, 90),
            history=(
                "Rectorragies et troubles du transit depuis {weeks} semaines. Coloscopie diagnostique.",
                "Anémie ferriprive découverte par le médecin traitant, coloscopie réalisée.",
            ),
            items=(
                ItemSpec(
                    "colonoscopy",
                    "Coloscopie complète",
                    ("Tumeur bourgeonnante sigmoïdienne à 25 cm.",),
                ),
                ItemSpec(
                    "histology",
                    "Anatomopathologie",
                    ("Adénocarcinome lieberkühnien bien différencié.",),
                ),
                ItemSpec(
                    "ct_tap",
                    "TDM thoraco-abdomino-pelvienne",
                    ("Épaississement pariétal sigmoïdien, pas de lésion à distance.",),
                    max_age_days=42,
                    may_be_external=True,
                ),
                ItemSpec(
                    "cea", "ACE", ("{marker_low} ng/mL",), required=False, days=(2, 20)
                ),
                ItemSpec(
                    "mmr",
                    "Statut MMR / MSI",
                    ("pMMR (MSS)", "dMMR (MSI)"),
                    required=False,
                ),
                ItemSpec(
                    "ras_braf",
                    "Statut RAS / BRAF",
                    ("RAS et BRAF sauvages", "KRAS muté (G12D)"),
                    required=False,
                ),
                _PS,
            ),
            scenarios=(
                Scenario(
                    "pT3N1aM0 (stade III)",
                    "Après colectomie : indication d'une chimiothérapie adjuvante ?",
                    (
                        "Chimiothérapie adjuvante par CAPOX 3 mois.",
                        "FOLFOX 6 mois si contre-indication à la capécitabine.",
                    ),
                ),
                Scenario(
                    "cT3N0M0",
                    "Colectomie d'emblée ?",
                    ("Sigmoïdectomie par cœlioscopie avec curage ganglionnaire.",),
                    surgical=True,
                ),
                Scenario(
                    "cT3N1M1a (hépatique)",
                    "Métastases hépatiques potentiellement résécables : stratégie ?",
                    (
                        "Chimiothérapie d'induction puis réévaluation de la résécabilité hépatique.",
                    ),
                    results={
                        "ct_tap": (
                            "Tumeur sigmoïdienne, 3 nodules hépatiques du foie droit.",
                        )
                    },
                ),
            ),
            required_specialties=(
                "Chirurgien digestif",
                "Oncologue médical",
                "Radiologue",
            ),
            optional_specialties=("Gastro-entérologue", "Anatomopathologiste"),
        ),
        PathologySpec(
            id="rectum",
            meeting_type="RCP Cancérologie digestive",
            icd10="C20",
            diagnosis="Adénocarcinome du moyen rectum",
            sexes="FM",
            age_range=(40, 85),
            history=("Rectorragies et ténesme depuis {weeks} semaines.",),
            items=(
                ItemSpec(
                    "pelvic_mri",
                    "IRM pelvienne",
                    (
                        "Tumeur à 7 cm de la marge anale, marge circonférentielle à 2 mm.",
                    ),
                    max_age_days=28,
                    may_be_external=True,
                ),
                ItemSpec(
                    "histology",
                    "Anatomopathologie",
                    ("Adénocarcinome lieberkühnien moyennement différencié.",),
                ),
                ItemSpec(
                    "ct_tap",
                    "TDM thoraco-abdomino-pelvienne",
                    ("Pas de lésion secondaire.",),
                    max_age_days=42,
                ),
                ItemSpec("cea", "ACE", ("{marker_low} ng/mL",), required=False),
                ItemSpec("mmr", "Statut MMR / MSI", ("pMMR (MSS)",), required=False),
                _PS,
            ),
            scenarios=(
                Scenario(
                    "cT3cN1M0",
                    "Traitement néoadjuvant total ?",
                    (
                        "Traitement néoadjuvant total (FOLFIRINOX puis radiochimiothérapie) puis chirurgie.",
                    ),
                ),
                Scenario(
                    "cT2N0M0",
                    "Exérèse totale du mésorectum d'emblée ?",
                    ("Proctectomie avec exérèse totale du mésorectum.",),
                    surgical=True,
                ),
            ),
            required_specialties=(
                "Chirurgien digestif",
                "Oncologue médical",
                "Radiothérapeute",
                "Radiologue",
            ),
            optional_specialties=("Gastro-entérologue",),
        ),
        PathologySpec(
            id="oesophagus",
            meeting_type="RCP Cancérologie digestive",
            icd10="C15.4",
            diagnosis="Carcinome épidermoïde du tiers moyen de l'œsophage",
            sexes="FM",
            age_range=(50, 84),
            history=(
                "Dysphagie aux solides d'aggravation progressive depuis {weeks} semaines.",
            ),
            items=(
                ItemSpec(
                    "endoscopy",
                    "Fibroscopie œso-gastro-duodénale",
                    ("Lésion ulcéro-bourgeonnante de 28 à 33 cm.",),
                ),
                ItemSpec(
                    "histology",
                    "Anatomopathologie",
                    ("Carcinome épidermoïde moyennement différencié.",),
                ),
                ItemSpec(
                    "pet_ct",
                    "TEP-TDM au 18F-FDG",
                    ("Hypermétabolisme œsophagien, pas de fixation à distance.",),
                    max_age_days=35,
                ),
                ItemSpec(
                    "eus",
                    "Écho-endoscopie",
                    ("Atteinte de l'adventice, 2 adénopathies.",),
                    required=False,
                ),
                ItemSpec(
                    "ent_exam",
                    "Examen ORL",
                    ("Pas de second cancer des voies aérodigestives.",),
                ),
                _PS,
                _WEIGHT,
            ),
            scenarios=(
                Scenario(
                    "cT3N1M0",
                    "Radiochimiothérapie préopératoire puis chirurgie ?",
                    (
                        "Radiochimiothérapie selon le schéma CROSS puis œsophagectomie.",
                        "Radiochimiothérapie exclusive en raison des comorbidités.",
                    ),
                    surgical=True,
                ),
            ),
            required_specialties=(
                "Chirurgien digestif",
                "Oncologue médical",
                "Radiothérapeute",
            ),
            optional_specialties=(
                "Gastro-entérologue",
                "Diététicien",
                "Médecin nucléaire",
            ),
        ),
        PathologySpec(
            id="hcc",
            meeting_type="RCP Tumeurs du foie",
            icd10="C22.0",
            diagnosis="Carcinome hépatocellulaire sur cirrhose",
            sexes="FM",
            age_range=(48, 82),
            history=(
                "Nodule hépatique découvert lors de l'échographie de surveillance d'une cirrhose.",
            ),
            items=(
                ItemSpec(
                    "liver_mri",
                    "IRM hépatique",
                    (
                        "Nodule de {size} mm du segment VI, hypervascularisé avec lavage portal.",
                    ),
                    max_age_days=28,
                    may_be_external=True,
                ),
                ItemSpec("afp", "Alpha-fœtoprotéine", ("{marker_low} ng/mL",)),
                ItemSpec("child_pugh", "Score de Child-Pugh", ("A5", "A6", "B7")),
                ItemSpec("meld", "Score MELD", ("9", "11", "14"), required=False),
                ItemSpec(
                    "endoscopy",
                    "Recherche de varices œsophagiennes",
                    ("Varices de grade 1.",),
                    required=False,
                ),
                _PS,
            ),
            scenarios=(
                Scenario(
                    "BCLC A",
                    "Traitement curatif : radiofréquence ou résection ?",
                    (
                        "Destruction percutanée par radiofréquence.",
                        "Résection hépatique (segmentectomie VI).",
                    ),
                    surgical=True,
                ),
                Scenario(
                    "BCLC B",
                    "Chimio-embolisation intra-artérielle ?",
                    ("Chimio-embolisation lipiodolée puis évaluation à 6 semaines.",),
                ),
            ),
            required_specialties=(
                "Hépatologue",
                "Radiologue interventionnel",
                "Chirurgien hépatobiliaire",
            ),
            optional_specialties=("Oncologue médical",),
        ),
        PathologySpec(
            id="lung",
            meeting_type="RCP Oncologie thoracique",
            icd10="C34.1",
            diagnosis="Adénocarcinome bronchique du lobe supérieur droit",
            sexes="FM",
            age_range=(45, 85),
            history=(
                "Toux persistante et hémoptysie, tabagisme sevré estimé à {pack_years} paquets-années.",
                "Nodule découvert sur un scanner réalisé pour bilan de dyspnée.",
            ),
            items=(
                ItemSpec(
                    "ct_tap",
                    "TDM thoraco-abdominale",
                    ("Masse du lobe supérieur droit de {size} mm.",),
                    max_age_days=42,
                    may_be_external=True,
                ),
                ItemSpec(
                    "pet_ct",
                    "TEP-TDM au 18F-FDG",
                    ("Fixation tumorale, pas de fixation ganglionnaire médiastinale.",),
                    max_age_days=42,
                ),
                ItemSpec(
                    "brain_mri",
                    "IRM cérébrale",
                    ("Pas de lésion secondaire.",),
                    required=False,
                ),
                ItemSpec(
                    "histology",
                    "Anatomopathologie (biopsie)",
                    ("Adénocarcinome TTF1 positif.",),
                ),
                ItemSpec(
                    "molecular",
                    "Biologie moléculaire (EGFR, ALK, ROS1) et PD-L1",
                    (
                        "EGFR, ALK et ROS1 négatifs, PD-L1 à 60 %.",
                        "Mutation EGFR exon 19, PD-L1 à 5 %.",
                    ),
                ),
                ItemSpec(
                    "pft",
                    "Explorations fonctionnelles respiratoires",
                    ("VEMS 72 % de la théorique, DLCO 65 %.",),
                ),
                _PS,
            ),
            scenarios=(
                Scenario(
                    "cT2aN0M0 (stade IB)",
                    "Lobectomie supérieure droite ?",
                    (
                        "Lobectomie supérieure droite avec curage médiastinal.",
                        "Radiothérapie stéréotaxique si inopérable.",
                    ),
                    surgical=True,
                ),
                Scenario(
                    "cT3N2M0 (stade IIIB)",
                    "Stratégie pour une maladie localement avancée ?",
                    (
                        "Radiochimiothérapie concomitante puis immunothérapie de consolidation par durvalumab.",
                    ),
                    results={
                        "pet_ct": (
                            "Fixations ganglionnaires médiastinales homolatérales.",
                        )
                    },
                ),
            ),
            required_specialties=(
                "Pneumologue",
                "Chirurgien thoracique",
                "Oncologue médical",
                "Radiothérapeute",
            ),
            optional_specialties=("Radiologue", "Anatomopathologiste"),
        ),
        PathologySpec(
            id="breast",
            meeting_type="RCP Sénologie",
            icd10="C50.4",
            diagnosis="Carcinome infiltrant de type non spécifique du sein gauche",
            sexes="F",
            age_range=(35, 88),
            history=(
                "Nodule palpé à l'autopalpation il y a {weeks} semaines.",
                "Anomalie au dépistage organisé.",
            ),
            items=(
                ItemSpec(
                    "imaging",
                    "Mammographie et échographie",
                    ("Masse de {size} mm du quadrant supéro-externe gauche, ACR 5.",),
                    may_be_external=True,
                ),
                ItemSpec(
                    "histology",
                    "Microbiopsie",
                    ("Carcinome infiltrant de type non spécifique, grade II.",),
                ),
                ItemSpec(
                    "receptors",
                    "Récepteurs hormonaux, HER2, Ki67",
                    (
                        "RE 90 %, RP 60 %, HER2 négatif, Ki67 15 %.",
                        "RE 0 %, RP 0 %, HER2 3+, Ki67 40 %.",
                    ),
                ),
                ItemSpec(
                    "axilla",
                    "Échographie axillaire",
                    ("Pas d'adénopathie suspecte.",),
                    required=False,
                ),
                ItemSpec(
                    "breast_mri", "IRM mammaire", ("Lésion unifocale.",), required=False
                ),
                _PS,
            ),
            scenarios=(
                Scenario(
                    "cT1cN0M0",
                    "Chirurgie conservatrice d'emblée ?",
                    (
                        "Tumorectomie et ganglion sentinelle, puis radiothérapie et hormonothérapie.",
                    ),
                    surgical=True,
                ),
                Scenario(
                    "cT2N1M0",
                    "Chimiothérapie néoadjuvante ?",
                    (
                        "Chimiothérapie néoadjuvante avec thérapie anti-HER2 puis chirurgie.",
                    ),
                ),
            ),
            required_specialties=(
                "Chirurgien sénologue",
                "Oncologue médical",
                "Radiothérapeute",
                "Radiologue",
            ),
            optional_specialties=("Anatomopathologiste", "Oncogénéticien"),
        ),
        PathologySpec(
            id="glioblastoma",
            meeting_type="RCP Neuro-oncologie",
            icd10="C71.1",
            diagnosis="Glioblastome frontal droit",
            sexes="FM",
            age_range=(40, 82),
            history=(
                "Crise comitiale inaugurale puis céphalées.",
                "Troubles du comportement depuis {weeks} semaines.",
            ),
            items=(
                ItemSpec(
                    "brain_mri",
                    "IRM cérébrale avec injection",
                    (
                        "Lésion frontale droite de {size} mm, prise de contraste annulaire, nécrose centrale.",
                    ),
                    max_age_days=21,
                    may_be_external=True,
                ),
                ItemSpec(
                    "histology",
                    "Anatomopathologie (exérèse ou biopsie)",
                    ("Glioblastome, IDH non muté, grade 4.",),
                ),
                ItemSpec(
                    "mgmt", "Méthylation du promoteur MGMT", ("Méthylé", "Non méthylé")
                ),
                ItemSpec(
                    "postop_mri",
                    "IRM post-opératoire (< 72 h)",
                    ("Exérèse subtotale.",),
                    required=False,
                    days=(10, 25),
                ),
                _PS,
            ),
            scenarios=(
                Scenario(
                    "OMS grade 4",
                    "Traitement adjuvant après exérèse ?",
                    (
                        "Radiochimiothérapie selon le protocole de Stupp.",
                        "Radiothérapie hypofractionnée seule.",
                    ),
                ),
            ),
            required_specialties=(
                "Neurochirurgien",
                "Neuro-oncologue",
                "Radiothérapeute",
                "Neuroradiologue",
            ),
            optional_specialties=("Anatomopathologiste",),
        ),
        PathologySpec(
            id="prostate",
            meeting_type="RCP Uro-oncologie",
            icd10="C61",
            diagnosis="Adénocarcinome prostatique",
            sexes="M",
            age_range=(55, 88),
            history=("Élévation du PSA à {psa} ng/mL au contrôle annuel.",),
            items=(
                ItemSpec(
                    "prostate_mri",
                    "IRM prostatique multiparamétrique",
                    ("Lésion PI-RADS 5 de la zone périphérique gauche.",),
                    may_be_external=True,
                ),
                ItemSpec(
                    "biopsy",
                    "Biopsies prostatiques",
                    ("Adénocarcinome Gleason 4+3 (ISUP 3), 5 biopsies sur 12.",),
                ),
                ItemSpec("psa", "PSA total", ("{psa} ng/mL",), days=(2, 30)),
                ItemSpec(
                    "staging",
                    "Bilan d'extension (TEP-PSMA ou TDM et scintigraphie)",
                    ("Pas de lésion secondaire.",),
                    required=False,
                ),
                _PS,
            ),
            scenarios=(
                Scenario(
                    "cT2bN0M0 (risque intermédiaire)",
                    "Prostatectomie ou radiothérapie ?",
                    (
                        "Prostatectomie totale robot-assistée.",
                        "Radiothérapie externe et hormonothérapie courte (6 mois).",
                    ),
                    surgical=True,
                ),
            ),
            required_specialties=("Urologue", "Radiothérapeute", "Oncologue médical"),
            optional_specialties=("Radiologue",),
        ),
    )
}

COMORBIDITIES = (
    "Hypertension artérielle",
    "Diabète de type 2",
    "Fibrillation atriale anticoagulée",
    "BPCO",
    "Insuffisance rénale chronique modérée",
    "Cardiopathie ischémique stentée",
    "Dyslipidémie",
    "Hypothyroïdie substituée",
    "Syndrome d'apnées du sommeil appareillé",
)

TREATMENTS = (
    "Bisoprolol 2,5 mg",
    "Metformine 1000 mg x2",
    "Apixaban 5 mg x2",
    "Atorvastatine 20 mg",
    "Lévothyroxine 75 µg",
    "Ramipril 5 mg",
    "Oméprazole 20 mg",
)
