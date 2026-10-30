import streamlit as st
from enum import Enum
from typing import Any

TRANSLATIONS = {
    # Model Docstrings / Class Titles
    "Patient administrative informations": "Informations administratives du patient",
    "Patient WHO performance status": "Statut de performance OMS du patient",
    "Location of the tumor": "Localisation de la tumeur",
    "Biology of the tumor": "Biologie de la tumeur",
    "List of radiological exams": "Liste des examens radiologiques",
    "Previous curative surgery": "Chirurgie curative antérieure",
    "Planned curative surgery": "Chirurgie curative prévue",
    "Chemotherapy treatments": "Traitements par chimiothérapie",
    "ExpertAnswer": "Réponse de l'expert",
    "MTDCompleted": "Dossier RCP complet",
    "Consensus on whether an intervention is required, its urgency, and description.": "Consensus sur la nécessité d'une intervention, son urgence et son type",
    "isInterventionRequiered": "Nécessité d'intervention",
    # SMA (Spinal Muscular Atrophy) Model Docstrings / Class Titles
    "GeneticDiagnosis": "Diagnostic génétique",
    "Genetic characteristics of Spinal Muscular Atrophy (SMN1 mutation and SMN2 copy number)": "Caractéristiques génétiques de l'amyotrophie spinale (mutation SMN1 et nombre de copies SMN2)",
    "MotorFunctionStatus": "Statut moteur",
    "SMA clinical classification and standardized motor scale scores": "Classification clinique de la SMA et scores de l'échelle motrice standardisée",
    "RespiratoryFunction": "Fonction respiratoire",
    "Respiratory status and mechanical ventilation requirements": "Statut respiratoire et besoins en ventilation mécanique",
    "OrthopedicAndSpineStatus": "Statut orthopédique et rachidien",
    "Spine deformities and joint contractures assessment": "Évaluation des déformations de la colonne vertébrale et des rétractions articulaires",
    "BulbarAndNutritionalStatus": "Statut bulbaire et nutritionnel",
    "Swallowing abilities, feeding methods, and growth/weight monitoring": "Capacités de déglutition, modes d'alimentation et suivi pondéral/croissance",
    # Field Descriptions
    "First name of the patient": "Prénom du patient",
    "Last name of the patient": "Nom de famille du patient",
    "Maiden or birth name of the patient if different from last name": "Nom de naissance du patient (si différent du nom d'usage)",
    "Age of the patient": "Âge du patient",
    "Date of birth of the patient (Format: YYYY-MM-DD)": "Date de naissance du patient (Format : AAAA-MM-JJ)",
    "Date of the MTD (Format: YYYY-MM-DD)": "Date de la RCP (Format : AAAA-MM-JJ)",
    "Gender of the patient": "Genre du patient",
    "WHO/OMS performance status of the patient, score from 0 to 4": "Statut de performance OMS du patient, score de 0 à 4",
    "Organ where the primary tumor is present": "Organe où la tumeur primitive est présente",
    "Is the tumor MSI or MSS": "La tumeur est-elle MSI ou MSS ?",
    "The name of the radiological exam": "Nom de l'examen radiologique",
    "The date when the radiological examination was performed.": "Date à laquelle l'examen radiologique a été réalisé",
    "The type of radiological examination performed (e.g., CT, MRI, X-ray, EUS).": "Type d'examen radiologique réalisé (ex : TDM, IRM, TEP, Échographie endoscopique)",
    "Summary of key findings from the radiological report": "Résumé des conclusions principales du rapport radiologique",
    "If a curative surgery has already been done": "Si une chirurgie curative a déjà été réalisée",
    "Date of the surgery": "Date de l'intervention chirurgicale",
    "If a curative surgery has been planned": "Si une chirurgie curative a été planifiée",
    "If a chemotherapy has already been done": "Si une chimiothérapie a déjà été réalisée",
    "List of chemotherapies that have been done": "Liste des chimiothérapies qui ont été réalisées",
    "Name of the chemotherapy drug or regimen (e.g., FOLFIRINOX)": "Nom du médicament ou protocole de chimiothérapie (ex : FOLFIRINOX)",
    "Start date of this specific chemotherapy line": "Date de début de cette ligne spécifique",
    "End date of this specific chemotherapy line": "Date de fin de cette ligne spécifique",
    "Patient's tolerance to the treatment": "Tolérance du patient face au traitement",
    "Is your expertise relevant for this patient's case?": "Votre expertise est-elle pertinente pour le cas de ce patient ?",
    "Urgency of the patient's treatment": "Urgence du traitement du patient",
    "Explain why your expertise is relevant (or not) for this patient and justify the priority given.": "Expliquez pourquoi votre expertise est pertinente (ou non) pour ce patient et justifiez la priorité",
    "Give the sources of your relevant answer": "Indiquez les sources de votre réponse pertinente",
    "List of suggestions. Empty if expert is not relevant.": "Liste des suggestions (vide si l'expertise n'est pas pertinente)",
    "Expert suggestion for the patient": "Suggestion de l'expert pour le patient",
    "Explanation of the reasoning behind the suggestion": "Explication du raisonnement derrière la suggestion",
    "list of suggestion references, including TNCD references": "Liste des références de la suggestion, incluant le TNCD",
    "Name of the reference": "Nom du référentiel",
    "Page of the document": "Page du document",
    "Position of the reference": "Position de la référence dans le document",
    "Summarize relevant excerpt from the document, no more than 3 lines": "Résumé de l'extrait du document (max. 3 lignes)",
    "Is the MDT file complete?": "Le dossier RCP est-il complet ?",
    "Based on your specialty and provided documents, is the MDT file complete?": "En vous basant sur votre spécialité et les documents fournis, le dossier RCP est-il complet ?",
    "List of missing elements required for a decision": "Liste des éléments manquants requis pour une prise de décision",
    "list of references for missing items, including TNCD references": "Liste des références pour les éléments manquants, incluant le TNCD",
    "Detailed reflection, reasoning, or synthesis of the collaborative team discussion": "Synthèse détaillée de la discussion et du raisonnement de l'équipe",
    "Is a medical, surgical, or radiologic intervention required for this patient?": "Une intervention médicale, chirurgicale ou radiologique est-elle requise pour ce patient ?",
    "How urgently the intervention should be performed. None if no intervention is required.": "Degré d'urgence de l'intervention. Aucun si aucune intervention n'est requise.",
    "Type of intervention required (e.g., surgery, chemotherapy, biliary drainage, endoscopy, etc.). None if no intervention is required.": "Type d'intervention requise (ex : chirurgie, chimiothérapie, drainage biliaire, endoscopie, etc.). Aucun si aucune intervention n'est requise.",
    "Clinical justification for the consensus decision.": "Justification clinique de la décision de consensus.",
    # SMA (Spinal Muscular Atrophy) Field Descriptions
    "Is the homozygous deletion or mutation of SMN1 confirmed?": "La délétion homozygote ou la mutation de SMN1 est-elle confirmée ?",
    "Number of SMN2 backup gene copies (crucial for prognosis and treatment eligibility)": "Nombre de copies du gène de secours SMN2 (crucial pour le pronostic et l'éligibilité au traitement)",
    "Other genetic modifiers or variations found, if any": "Autres modificateurs ou variantes génétiques trouvés, le cas échéant",
    "Clinical type of SMA: Type 1 (Werdnig-Hoffmann), Type 2, Type 3 (Kugelberg-Welander), or Type 4": "Type clinique de SMA : Type 1 (Werdnig-Hoffmann), Type 2, Type 3 (Kugelberg-Welander) ou Type 4",
    "Achieved motor milestones (e.g. head control, sitting unsupported, standing, independent walking)": "Acquisitions motrices (ex : tenue de tête, position assise sans soutien, station debout, marche autonome)",
    "Hammersmith Functional Motor Scale Expanded (HFMSE) score (0-66)": "Score HFMSE (Hammersmith Functional Motor Scale Expanded) (0-66)",
    "CHOP INTEND score (usually for Type 1 infants, 0-64)": "Score CHOP INTEND (généralement pour les nourrissons de type 1, 0-64)",
    "Revised Upper Limb Module (RULM) score (0-37)": "Score RULM (Revised Upper Limb Module) (0-37)",
    "Does the patient require respiratory assistance?": "Le patient nécessite-t-il une assistance respiratoire ?",
    "Type of support: Non-invasive ventilation (NIV/BiPAP), Tracheostomy, or None": "Type d'assistance : Ventilation non invasive (VNI/BiPAP), Trachéotomie ou Aucun",
    "Number of hours of ventilation per day": "Nombre d'heures de ventilation par jour",
    "Does the patient use a mechanical insufflator-exsufflator (cough assist)?": "Le patient utilise-t-il un assistant mécanique à la toux (cough assist) ?",
    "Forced Vital Capacity (FVC / CVF) in % of predicted value": "Capacité vitale forcée (CVF) en % de la valeur théorique",
    "Presence of scoliosis": "Présence d'une scoliose",
    "Scoliosis Cobb angle in degrees if measured": "Angle de Cobb de la scoliose en degrés si mesuré",
    "Has the patient undergone spinal fusion / arthrodesis?": "Le patient a-t-il subi une fusion vertébrale / arthrodèse ?",
    "Affected joints with contractures (e.g. hips, knees, ankles)": "Articulations touchées par des rétractions (ex : hanches, genoux, chevilles)",
    "Does the patient require a wheelchair (manual or electric)?": "Le patient nécessite-t-il un fauteuil roulant (manuel ou électrique) ?",
    "Does the patient have swallowing difficulties?": "Le patient présente-t-il des troubles de la déglutition (dysphagie) ?",
    "Primary feeding mode: Oral, Oral with thickening, Gastrostomy tube (G-tube / GPE), or Nasogastric tube": "Mode d'alimentation principal : Oral, Oral avec épaississant, Gastrostomie (GPE), ou Sonde nasogastrique",
    "History of aspiration pneumonia (fausses routes)": "Antécédents de pneumopathie d'inhalation (fausses routes)",
    "Nutritional status: Normal, Failure to thrive / Underweight, Overweight": "Statut nutritionnel : Normal, Retard de croissance / Dénutrition, Surcharge pondérale",
    # Field Name translations
    "first_name": "Prénom",
    "last_name": "Nom",
    "born_name": "Nom de naissance",
    "age": "Âge",
    "date_birth": "Date de naissance",
    "date_rcp": "Date de la RCP",
    "gender": "Genre",
    "performance_status": "Statut de performance (OMS)",
    "tumor_location": "Localisation tumorale",
    "msi_state": "Statut MSI / MSS",
    "exams_list": "Liste des examens",
    "exam_name": "Nom de l'examen",
    "exam_date": "Date de l'examen",
    "exam_type": "Type d'examen",
    "exam_result": "Résultat de l'examen",
    "previous_curative_surgery": "Chirurgie curative antérieure",
    "previous_curative_surgery_date": "Date de la chirurgie",
    "planned_curative_surgery": "Chirurgie curative prévue",
    "chemotherapy": "Chimiothérapie",
    "chemotherapy_list": "Liste des chimiothérapies",
    "chemotherapy_name": "Nom du protocole",
    "chemotherapy_start_date": "Date de début",
    "chemotherapy_end_date": "Date de fin",
    "chemotherapy_tolerance": "Tolérance",
    "expert_relevant": "Expertise pertinente",
    "patient_priority": "Priorité",
    "why_relevant": "Raison de la pertinence",
    "sources_relevant": "Sources & Références",
    "suggestions": "Suggestions",
    "suggestion": "Suggestion",
    "why": "Justification clinique",
    "references": "Références",
    "name": "Nom",
    "page": "Page",
    "position": "Section / Position",
    "excerpt": "Extrait",
    "is_mtd_complete": "Dossier complet ?",
    "what_missing": "Éléments manquants",
    "reflection": "Réflexion / Synthèse du débat",
    "intervention_required": "Intervention conseillée",
    "intervention_type": "Type d'intervention",
    "justification": "Justification du consensus",
    # SMA Field Name translations
    "smn1_deletion_confirmed": "Délétion SMN1 confirmée",
    "smn2_copy_count": "Nombre de copies SMN2",
    "other_genetic_variants": "Autres variantes génétiques",
    "sma_type": "Type de SMA",
    "motor_milestones": "Acquisitions motrices",
    "hfmse_score": "Score HFMSE",
    "chop_intend_score": "Score CHOP INTEND",
    "rulm_score": "Score RULM",
    "requires_ventilation_support": "Assistance respiratoire requise",
    "ventilation_type": "Type de ventilation",
    "daily_ventilation_hours": "Heures de ventilation/jour",
    "uses_cough_assist": "Utilise un assistant à la toux",
    "forced_vital_capacity_percent": "Capacité vitale forcée (CVF %)",
    "has_scoliosis": "Présence de scoliose",
    "scoliosis_cobb_angle": "Angle de Cobb",
    "spine_surgery_history": "Antécédent de chirurgie du rachis",
    "joint_contractures": "Rétractions articulaires",
    "wheelchair_user": "Utilisateur de fauteuil roulant",
    "has_dysphagia": "Présence de dysphagie",
    "feeding_mode": "Mode d'alimentation",
    "history_aspiration_pneumonia": "Antécédents de fausses routes",
    "nutritional_status": "Statut nutritionnel",
    # Enum Values & Labels
    "Male": "Homme",
    "Female": "Femme",
    "Other": "Autre",
    "Not_given": "Non spécifié",
    "not_given": "Non spécifié",
    "male": "Homme",
    "female": "Femme",
    "other": "Autre",
    "urgent": "Urgent",
    "medium": "Moyen",
    "low": "Faible",
    "no answer": "Non spécifié",
    "Patient must be treated urgently": "Priorité haute (Le patient doit être traité de toute urgence)",
    "Patient must be treated as soon as possible": "Priorité moyenne (Le patient doit être traité dès que possible)",
    "Patient is not urgent": "Priorité basse (Pas d'urgence immédiate)",
    "No limitation of activities (none)": "0 - Pas de limitation des activités (normal)",
    "Limitation in strenuous activities, but able to do light work or other activities": "1 - Limitation lors d'efforts physiques intenses, mais capable de faire un travail léger",
    "Considerable limitation in activities; some assistance occasionally needed": "2 - Limitation considérable ; assistance requise occasionnellement",
    "Severe limitation in activities; frequent assistance required": "3 - Limitation sévère ; assistance fréquente requise",
    "Complete limitation of activities; unable to perform any activity": "4 - Limitation complète ; incapable de réaliser la moindre activité",
    "Pancreas": "Pancréas",
    "Colon": "Côlon",
    "Liver": "Foie",
    "Stomach": "Estomac",
    "Oesophagus": "Œsophage",
    "Rectum": "Rectum",
    "Intra-hepatic bile duct": "Voies biliaires intra-hépatiques",
    "Extra-hepatic bile duct": "Voies biliaires extra-hépatiques",
    "unknown": "Inconnu",
    "Surgery": "Chirurgie",
    "Chemotherapy": "Chimiothérapie",
    "Radiotherapy": "Radiothérapie",
    "Immunotherapy": "Immunothérapie",
    "Curative": "Curatif",
    "Palliative": "Palliatif",
    "Adjuvant": "Adjuvant",
    "Neo-adjuvant": "Néo-adjuvant",
    "Good": "Bonne",
    "Medium": "Moyenne",
    "Poor": "Mauvaise",
    # Domains
    "oncology": "Oncologie",
    "sma": "Amyotrophie spinale",
    # Clinical & Technical Agents
    "Administrative": "Extraction administrative & clinique",
    "MDT Coordinator": "Coordinateur RCP",
    "Ressource Assistant": "Assistant référentiels",
    "pancreas expert": "Expert Pancréas",
    "oesophagus expert": "Expert Œsophage",
    "hepatocellular expert": "Expert Foie / CHC",
    "neurologist expert": "Expert Neurologue",
    "geneticist expert": "Expert Généticien",
    "pulmonologist expert": "Expert Pneumologue",
    "physiotherapy expert": "Expert MPR / Rééducation",
    "orthopedist expert": "Expert Orthopédiste",
}

AGENT_ICONS: dict[str, str] = {
    "administrative": "🗂️",
    "mdt coordinator": "⚖️",
    "ressource assistant": "📚",
    "pancreas expert": "🩺",
    "oesophagus expert": "🩺",
    "hepatocellular expert": "🩺",
    "neurologist expert": "🧠",
    "geneticist expert": "🧬",
    "pulmonologist expert": "🫁",
    "physiotherapy expert": "🦿",
    "orthopedist expert": "🦴",
}


def get_agent_icon_and_label(agent_name: str) -> tuple[str, str]:
    """Return a clinical icon and translated display label for a given agent identifier."""
    clean = (agent_name or "").strip().lower()
    icon = AGENT_ICONS.get(clean, "🩺")
    label = str(translate(agent_name))
    return icon, label


DOMAIN_FR_LABELS: dict[str, str] = {
    "oncology": "Oncologie",
    "sma": "Amyotrophie spinale",
}


def translate_domain_fr(domain: str) -> str:
    """Retourne le libellé en français du domaine médical configuré."""
    if not domain:
        return ""
    clean = domain.strip().lower()
    return DOMAIN_FR_LABELS.get(clean, domain.strip().capitalize())


def get_icon_svg() -> str:
    """
    Génère l'icône d'application DataSyntis (favicon et raccourci bureau hospitalier) :
    feuillets documentaires superposés, lignes de synthèse structurées et pastille de validation clinique.
    """
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">\n'
        "  <defs>\n"
        '    <linearGradient id="dsSlate" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" stop-color="#1E293B" />\n'
        '      <stop offset="100%" stop-color="#0F172A" />\n'
        "    </linearGradient>\n"
        '    <linearGradient id="dsTeal" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" stop-color="#72A8A2" />\n'
        '      <stop offset="100%" stop-color="#3E7B76" />\n'
        "    </linearGradient>\n"
        '    <linearGradient id="dsSage" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" stop-color="#84A98C" />\n'
        '      <stop offset="100%" stop-color="#52796F" />\n'
        "    </linearGradient>\n"
        "  </defs>\n"
        '  <rect x="4" y="4" width="92" height="92" rx="22" fill="url(#dsSlate)" stroke="#334155" stroke-width="2" />\n'
        "  <!-- Feuillet documentaire consolidé en arrière-plan (Sarcelle) -->\n"
        '  <rect x="18" y="16" width="46" height="58" rx="8" fill="url(#dsTeal)" opacity="0.82" />\n'
        "  <!-- Fiche de synthèse clinique au premier plan -->\n"
        '  <rect x="28" y="24" width="48" height="58" rx="8" fill="#F8FAFC" stroke="url(#dsTeal)" stroke-width="2.5" />\n'
        '  <rect x="35" y="33" width="24" height="5.5" rx="2.75" fill="url(#dsTeal)" />\n'
        '  <circle cx="66.5" cy="35.75" r="3" fill="#D94668" />\n'
        '  <rect x="35" y="44" width="34" height="4.5" rx="2.25" fill="#64748B" />\n'
        '  <rect x="35" y="53" width="28" height="4.5" rx="2.25" fill="#64748B" />\n'
        '  <rect x="35" y="62" width="20" height="4.5" rx="2.25" fill="#94A3B8" />\n'
        "  <!-- Pastille de validation et conformité RCP (Sauge / Vert) -->\n"
        '  <circle cx="70" cy="68" r="13" fill="url(#dsSage)" stroke="#1E293B" stroke-width="2.5" />\n'
        '  <path d="M64.5 68 L68.5 72 L76 64" fill="none" stroke="#F8FAFC" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />\n'
        "</svg>"
    )


def get_logo_svg(domain: str) -> str:
    """Génère le logotype SVG DataSyntis intégrant dynamiquement le domaine médical en français."""
    domain_fr = translate_domain_fr(domain)
    subtitle_line = (
        f"  <text x=\"114\" y=\"92\" font-family=\"'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif\" "
        f'font-size="23" font-weight="600" letter-spacing="1.4" fill="#CBD5E1">- {domain_fr}</text>\n'
        if domain_fr
        else ""
    )
    brand_y = "59" if domain_fr else "70"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 385 106" width="385" height="106">\n'
        "  <defs>\n"
        '    <linearGradient id="dsSlate" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" stop-color="#1E293B" />\n'
        '      <stop offset="100%" stop-color="#0F172A" />\n'
        "    </linearGradient>\n"
        '    <linearGradient id="dsTeal" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" stop-color="#88BDBC" />\n'
        '      <stop offset="100%" stop-color="#4A857F" />\n'
        "    </linearGradient>\n"
        '    <linearGradient id="dsSage" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" stop-color="#68A38E" />\n'
        '      <stop offset="100%" stop-color="#437A68" />\n'
        "    </linearGradient>\n"
        "  </defs>\n"
        '  <g transform="translate(2, 3)">\n'
        '    <rect x="4" y="4" width="92" height="92" rx="22" fill="url(#dsSlate)" stroke="#475569" stroke-width="2" />\n'
        '    <rect x="18" y="16" width="46" height="58" rx="8" fill="url(#dsTeal)" opacity="0.82" />\n'
        '    <rect x="28" y="24" width="48" height="58" rx="8" fill="#F8FAFC" stroke="url(#dsTeal)" stroke-width="2.5" />\n'
        '    <rect x="35" y="33" width="24" height="5.5" rx="2.75" fill="url(#dsTeal)" />\n'
        '    <circle cx="66.5" cy="35.75" r="3" fill="#D94668" />\n'
        '    <rect x="35" y="44" width="34" height="4.5" rx="2.25" fill="#64748B" />\n'
        '    <rect x="35" y="53" width="28" height="4.5" rx="2.25" fill="#64748B" />\n'
        '    <rect x="35" y="62" width="20" height="4.5" rx="2.25" fill="#94A3B8" />\n'
        '    <circle cx="70" cy="68" r="13" fill="url(#dsSage)" stroke="#1E293B" stroke-width="2.5" />\n'
        '    <path d="M64.5 68 L68.5 72 L76 64" fill="none" stroke="#F8FAFC" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />\n'
        "  </g>\n"
        f'  <text x="112" y="{brand_y}" font-family="\'Inter\', \'Segoe UI\', \'Helvetica Neue\', Arial, sans-serif" font-size="52" font-weight="800" letter-spacing="-1">\n'
        '    <tspan fill="#E2E8F0">Data</tspan><tspan fill="#72A8A2">Syntis</tspan>\n'
        "  </text>\n"
        f"{subtitle_line}"
        "</svg>"
    )


def apply_card_surface_style() -> None:
    """Apply Option 1 matte clinical paper card surfaces (#F8FAFC), larger logo, visible info banners, and compact top page padding."""
    st.html(
        """
        <style>
        div[data-testid="stMainBlockContainer"],
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 2rem !important;
        }
        div[data-testid="stHeadingWithActionElements"] h1,
        .stMainBlockContainer h1 {
            padding-top: 0 !important;
            padding-bottom: 0.2rem !important;
            margin-top: 0 !important;
            font-size: 1.85rem !important;
        }
        img[data-testid="stLogo"],
        div[data-testid="stSidebarHeader"] img {
            height: 3.25rem !important;
            max-height: 3.25rem !important;
            width: auto !important;
        }
        div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"],
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stExpander"],
        div[data-testid="stMetric"] {
            background-color: light-dark(#FBFDFF, #162032) !important;
            border-color: light-dark(#CBD5E1, #334155) !important;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        }
        div[data-testid="stMetric"] {
            padding: 0.6rem 0.9rem !important;
        }
        div[data-testid="stMetricValue"] > div {
            font-size: 1.65rem !important;
            line-height: 1.2 !important;
        }
        div[data-testid="stAlertContainer"]:has(> div[data-testid="stAlertContentInfo"]) {
            background-color: light-dark(#E3EFF8, #1E3A5F) !important;
            color: light-dark(#234B6E, #DBEAFE) !important;
            border: 1px solid light-dark(#B6D4EC, #2563EB) !important;
            border-left: 4px solid light-dark(#3B6E9C, #60A5FA) !important;
            border-radius: 0.5rem !important;
            padding: 0.65rem 1rem !important;
        }
        div[data-testid="stVerticalBlock"]:has(> div[data-testid="stLayoutWrapper"] > div[class*="st-key-clinical_scroll_"]),
        div[class*="st-key-clinical_scroll_"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-clinical_scroll_"] {
            background-color: transparent !important;
            box-shadow: none !important;
            border: none !important;
        }
        </style>
        """
    )


def translate(text: Any) -> Any:
    """
    Translates English clinical labels, descriptions, and Enum values to French in the UI.
    If English is selected as language, returns the original text.
    """
    if isinstance(text, Enum):
        if hasattr(text.__class__, "labels"):
            labels_dict = text.__class__.labels()
            if text in labels_dict:
                return translate(labels_dict[text])
        val = text.value if hasattr(text, "value") else text.name
        return translate(val)

    if not isinstance(text, str):
        return text

    # If the user explicitly selects English, bypass translation
    if st.session_state.get("language", "Français") == "English":
        return text

    stripped = text.strip()
    if stripped in TRANSLATIONS:
        return TRANSLATIONS[stripped]

    lower = stripped.lower()
    if lower in TRANSLATIONS:
        return TRANSLATIONS[lower]

    return text
