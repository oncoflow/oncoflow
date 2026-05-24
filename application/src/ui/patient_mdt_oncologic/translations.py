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
    # Field Descriptions
    "First name of the patient": "Prénom du patient",
    "Last name of the patient": "Nom de famille du patient",
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
    # Field Name translations
    "first_name": "Prénom",
    "last_name": "Nom",
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
}


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
