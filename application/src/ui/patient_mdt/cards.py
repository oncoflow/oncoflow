from datetime import datetime
from typing import Any
import streamlit as st

from src.application.config import AppConfig
from src.application.app_functions import delete_document, delete_patient_dossier
from src.application.patient import (
    build_patients_cards_data,
    extract_card_metrics,
    is_rcp_visible_in_cards,
)
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.queue import QueueBroker

# Configuration de l'application
app_conf = AppConfig()

# Connexion Base de données
db_client = None
if app_conf.rcp.display_type == "mongodb":
    db_client = Mongodb(app_conf)

logger = app_conf.set_logger("ui", default_context={"page": "cards"})


@st.dialog("Confirmation de suppression")
def delete_card(filename: str):
    st.warning(f"Voulez-vous vraiment supprimer la fiche RCP : {filename} ?")
    st.markdown("Cette action est irréversible.")
    if st.button("Confirmer la suppression", type="primary"):
        delete_document(app_conf, filename)
        st.rerun()


@st.dialog("Confirmation de suppression du dossier patient")
def delete_patient_card(patient_id: str, patient_name: str):
    st.warning(
        f"Voulez-vous vraiment supprimer l'intégralité du dossier patient : {patient_name} ?"
    )
    st.markdown(
        "Toutes les fiches RCP associées à ce patient seront supprimées. Cette action est irréversible."
    )
    if st.button("Confirmer la suppression du dossier", type="primary"):
        delete_patient_dossier(app_conf, patient_id)
        st.rerun()


def get_rcp_data() -> list[dict]:
    """Récupère les données RCP depuis MongoDB et les formate pour l'affichage."""
    if db_client is None or not hasattr(db_client, "database"):
        return []

    projection = {
        "file": 1,
        "patient_id": 1,
        "ui_date": 1,
        "PatientAdministrative": 1,
        "ExpertAnswer": 1,
        "MTDCompleted": 1,
        "isInterventionRequiered": 1,
        "processing_status": 1,
        "processing_step": 1,
        "processing_progress_pct": 1,
    }
    db_datas = [
        d
        for d in db_client.database["rcp_info"].find({}, projection)
        if is_rcp_visible_in_cards(d)
    ]
    cards_data = [extract_card_metrics(d) for d in db_datas]
    # Par défaut, trier les dernières RCP scannées par date de scan (ui_date / date_refresh) décroissante
    cards_data.sort(
        key=lambda x: x.get("date_refresh") or datetime.min,
        reverse=True,
    )
    return cards_data


@st.fragment(run_every="4s")
def render_queue_status_banner():
    """
    Affiche un bandeau métier discret uniquement lorsque des fiches sont en cours
    ou en attente dans la file de traitement.
    """
    if not app_conf.queue.enabled:
        return
    try:
        broker = QueueBroker(app_conf)
        try:
            stats = broker.get_queue_stats()
        finally:
            broker.close()
    except Exception:
        return

    pending = stats.get("pending", 0)
    processing = stats.get("processing", 0)
    if pending + processing <= 0:
        return

    c_info, c_btn = st.columns([5, 1], vertical_alignment="center")
    with c_info:
        st.info(
            f"⏳ **File de traitement :** {processing} fiche(s) en cours de traitement, "
            f"{pending} tâche(s) en attente."
        )
    with c_btn:
        if st.button(
            "🔄 Actualiser",
            key="btn_refresh_cards_queue",
            width="stretch",
        ):
            st.rerun(scope="app")


def get_patients_cards_data() -> list[dict]:
    """
    Récupère les dossiers patients et construit pour chacun la carte basée sur sa dernière RCP analysée.
    """
    return build_patients_cards_data(db_client)


def set_sort_order(column_key: str):
    """Sets the session state for sorting the list view."""
    if st.session_state.get("list_sort_by") == column_key:
        # Toggle direction
        st.session_state.list_sort_ascending = not st.session_state.get(
            "list_sort_ascending", False
        )
    else:
        # Set new column and default to ascending
        st.session_state.list_sort_by = column_key
        st.session_state.list_sort_ascending = True


def display_as_list(
    data, section_prefix: str = "rcp", is_patient_section: bool = False
):
    """Affiche les données sous forme de liste/tableau triable."""

    # --- Initialisation & Logique de Tri ---
    if "list_sort_by" not in st.session_state:
        st.session_state.list_sort_by = "urgency_score"
        st.session_state.list_sort_ascending = False

    sort_by = st.session_state.list_sort_by
    ascending = st.session_state.list_sort_ascending

    default_value_map = {
        "date": datetime.min,
        "patient": "",
        "urgency_score": -1,
    }

    default_val = default_value_map.get(sort_by)
    if default_val is None:
        default_val = ""

    sorted_data = sorted(
        data,
        key=lambda x: x.get(sort_by) if x.get(sort_by) is not None else default_val,
        reverse=not ascending,
    )

    def get_sort_indicator(column_key: str):
        if st.session_state.get("list_sort_by") == column_key:
            return " ▲" if st.session_state.get("list_sort_ascending") else " ▼"
        return ""

    # En-tête cliquable
    header_cols = st.columns((3, 2, 2, 3, 4, 2))

    with header_cols[0]:
        if st.button(
            f"Patient{get_sort_indicator('patient')}",
            key=f"sort_patient_{section_prefix}",
            width="stretch",
        ):
            set_sort_order("patient")
            st.rerun()

    with header_cols[1]:
        if st.button(
            f"Date RCP{get_sort_indicator('date')}",
            key=f"sort_date_{section_prefix}",
            width="stretch",
        ):
            set_sort_order("date")
            st.rerun()

    with header_cols[2]:
        if st.button(
            f"Urgence{get_sort_indicator('urgency_score')}",
            key=f"sort_urgency_{section_prefix}",
            width="stretch",
        ):
            set_sort_order("urgency_score")
            st.rerun()

    header_cols[3].markdown("**Statut du dossier**")
    header_cols[4].markdown("**Experts pertinents**")
    header_cols[5].markdown("**Actions**")
    st.divider()

    # Corps du tableau
    for item in sorted_data:
        row_cols = st.columns((3, 2, 2, 3, 4, 2))

        refresh_str = (
            item["date_refresh"].strftime("%d-%m-%Y")
            if item.get("date_refresh")
            else "Inconnue"
        )
        rcp_count = item.get("rcp_count")
        title_text = (
            f"{item['patient']} ({rcp_count} RCP)"
            if is_patient_section and rcp_count
            else item["patient"]
        )
        row_cols[0].subheader(
            title_text,
            help=f"Refresh : {refresh_str} - Dernière RCP: {item['file']}",
        )
        if not is_patient_section:
            row_cols[0].caption(f"📄 `{item['file']}`")

        # Colonne Date
        date_str = item["date"].strftime("%d-%m-%Y") if item.get("date") else "Inconnue"
        row_cols[1].markdown(f"📅 {date_str}")

        # Colonne Urgence
        urgency_map = {
            "Urgent": "🚨 Urgent",
            "Semi-urgent": "🟠 Semi-urgent",
            "Standard": "🟢 Standard",
        }
        urgency_display = urgency_map.get(item["urgency"], "⚪ Indéfini")
        row_cols[2].markdown(urgency_display)

        # Colonne Statut
        with row_cols[3]:
            proc_status = item.get("processing_status")
            if proc_status == "PENDING_CLINICAL":
                st.markdown("⏳ **Analyse clinique en attente**")
            elif proc_status == "PROCESSING_CLINICAL":
                st.markdown("🔄 **Analyse clinique en cours**")
            elif proc_status == "FAILED":
                st.markdown("❌ **Échec du traitement**")
            elif item["missing"]:
                with st.expander(f"⚠️ Incomplet ({len(item['missing'])})"):
                    for m in item["missing"]:
                        st.markdown(f"- {m}")
            else:
                st.markdown("✅ Complet")

            if item.get("intervention_required") is True:
                int_type = (
                    f" ({item['intervention_type']})"
                    if item.get("intervention_type")
                    else ""
                )
                st.markdown(f"💉 **Intervention requise**{int_type}")
            elif item.get("intervention_required") is False:
                st.markdown("✔️ Pas d'intervention")

        # Colonne Experts
        if item["experts"]:
            row_cols[4].markdown(", ".join([f"`{e}`" for e in item["experts"]]))
        else:
            row_cols[4].markdown("Aucun")

        # Colonne Actions
        unique_id = (
            item.get("patient_id") or item["file"]
            if is_patient_section
            else item["file"]
        )
        with row_cols[5]:
            b1, b2 = st.columns(2)
            with b1:
                st.link_button(
                    "👁️",
                    item["link"],
                    width="stretch",
                    help="Ouvrir le dossier",
                )
            with b2:
                if st.button(
                    "🗑️",
                    key=f"btn_del_list_{section_prefix}_{unique_id}",
                    type="primary",
                    width="stretch",
                    help="Supprimer le dossier",
                ):
                    if is_patient_section and item.get("patient_id"):
                        delete_patient_card(item["patient_id"], item["patient"])
                    else:
                        delete_card(item["file"])
        st.divider()


def display_as_cards(
    data, section_prefix: str = "rcp", is_patient_section: bool = False
):
    """Affiche les données sous forme de cartes (même format pour Dossiers Patients et Fiches RCP)."""
    cols = st.columns(3)
    for i, item in enumerate(data):
        col = cols[i % 3]
        with col:
            with st.container(border=True):
                # Urgence Badge
                badge_urgent = ""
                if item["urgency"] == "Urgent":
                    badge_urgent = ":red-badge[🚨 urgent]"
                elif item["urgency"] == "Semi-urgent":
                    badge_urgent = ":orange-badge[🟠 medium]"

                badge_missing = (
                    ":orange-badge[⚠️ Dossier Incomplet]" if item["missing"] else ""
                )

                badge_intervention = ""
                if item.get("intervention_required") is True:
                    int_type = (
                        f" ({item['intervention_type']})"
                        if item.get("intervention_type")
                        else ""
                    )
                    badge_intervention = (
                        f":orange-badge[💉 Intervention conseillée{int_type}]"
                    )
                elif item.get("intervention_required") is False:
                    badge_intervention = ":green-badge[Pas d'intervention]"

                badge_rcp_count = ""
                if is_patient_section and item.get("rcp_count"):
                    badge_rcp_count = f":blue-badge[🗂️ {item['rcp_count']} RCP]"

                badge_processing = ""
                proc_status = item.get("processing_status")
                if proc_status == "PENDING_CLINICAL":
                    badge_processing = ":blue-badge[⏳ Analyse clinique en attente]"
                elif proc_status == "PROCESSING_CLINICAL":
                    badge_processing = ":blue-badge[🔄 Analyse clinique en cours]"
                elif proc_status == "FAILED":
                    badge_processing = ":red-badge[❌ Échec du traitement]"

                refresh_str = (
                    item["date_refresh"].strftime("%d-%m-%Y")
                    if item.get("date_refresh")
                    else "Inconnue"
                )
                st.subheader(
                    item["patient"],
                    help=f"Refresh : {refresh_str} - Fichier: {item['file']}",
                )

                # Combine badges
                badges = [
                    badge_rcp_count,
                    badge_processing,
                    badge_urgent,
                    badge_missing,
                    badge_intervention,
                ]
                badges_str = " ".join([b for b in badges if b])
                if badges_str:
                    st.markdown(badges_str)

                if item["date"] is not None:
                    date_caption = (
                        f"📅 Dernière RCP : {item['date'].strftime('%d-%m-%Y')}"
                        if is_patient_section
                        else f"📅 {item['date'].strftime('%d-%m-%Y')}"
                    )
                    st.caption(date_caption)
                else:
                    st.caption("📅 Inconnu")

                if not is_patient_section:
                    st.caption(f"📄 `{item['file']}`")

                # Experts
                if item["experts"]:
                    st.markdown(
                        "**Experts:** " + ", ".join([f"`{e}`" for e in item["experts"]])
                    )
                else:
                    st.markdown("**Experts:** Inconnu")

                # Manquants
                if item["missing"]:
                    with st.expander(
                        f"⚠️ **Liste des données manquantes** ({len(item['missing'])})"
                    ):
                        for m in item["missing"]:
                            st.markdown(f"- {m}")
                else:
                    st.expander("")
                st.divider()

                # Boutons
                unique_id = (
                    item.get("patient_id") or item["file"]
                    if is_patient_section
                    else item["file"]
                )
                b1, b2 = st.columns(2)
                with b1:
                    st.link_button("Ouvrir", item["link"], width="stretch")
                with b2:
                    if st.button(
                        "Supprimer",
                        key=f"btn_del_card_{section_prefix}_{unique_id}_{i}",
                        type="primary",
                        width="stretch",
                    ):
                        if is_patient_section and item.get("patient_id"):
                            delete_patient_card(item["patient_id"], item["patient"])
                        else:
                            delete_card(item["file"])


def _filter_items(
    items: list[dict],
    search_term: str,
    selected_urgencies: list[str],
    completeness_filter: str,
    selected_experts: list[str],
    date_range: Any,
) -> list[dict]:
    """Applique les filtres du tableau de bord à une liste de cartes."""
    filtered = []
    for item in items:
        if search_term:
            term = search_term.lower()
            if term not in item["patient"].lower() and term not in item["file"].lower():
                continue

        if item["urgency"] not in selected_urgencies:
            continue

        is_incomplete = len(item["missing"]) > 0
        if completeness_filter == "Complet" and is_incomplete:
            continue
        if completeness_filter == "Incomplet" and not is_incomplete:
            continue

        if selected_experts:
            if not any(e in item["experts"] for e in selected_experts):
                continue

        if date_range and len(date_range) == 2:
            start, end = date_range
            if item["date"]:
                if not (start <= item["date"].date() <= end):
                    continue

        filtered.append(item)
    return filtered


def _sort_cards(items: list[dict], sort_option: str | None) -> list[dict]:
    """Trie une liste de cartes selon l'option choisie."""
    result = list(items)
    if sort_option == "Urgence (Haute > Basse)":
        result.sort(key=lambda x: x["urgency_score"], reverse=True)
    elif sort_option == "Urgence (Basse > Haute)":
        result.sort(key=lambda x: x["urgency_score"], reverse=False)
    elif sort_option == "Date (Récent > Ancien)":
        result.sort(key=lambda x: x.get("date") or datetime.min, reverse=True)
    elif sort_option == "Date (Ancien > Récent)":
        result.sort(key=lambda x: x.get("date") or datetime.min, reverse=False)
    return result


def cards_view():
    st.title("📇 Tableau de bord Patients & RCP")

    render_queue_status_banner()

    rcp_data = get_rcp_data()
    patient_data = get_patients_cards_data()

    if not rcp_data and not patient_data:
        st.info("Aucune fiche RCP trouvée.")
        return

    # Layout: Main content (Left) | Filters (Right)
    col_main, col_filters = st.columns([3, 1])

    with col_main:
        view_mode = st.segmented_control(
            "Vue",
            options=["Cartes", "Liste"],
            default="Cartes",
            label_visibility="collapsed",
        )
        view_mode = view_mode or "Cartes"

    # --- Filtres (Right) ---
    with col_filters:
        st.subheader("🔍 Filtres")

        search_term = st.text_input("Rechercher", placeholder="Patient, Fichier...")

        urgency_options = ["Urgent", "Semi-urgent", "Standard", "Indéfini"]
        selected_urgencies = st.multiselect(
            "Urgence", options=urgency_options, default=urgency_options
        )

        completeness_filter = st.segmented_control(
            "Statut dossier",
            options=["Tous", "Complet", "Incomplet"],
            default="Tous",
        )
        completeness_filter = completeness_filter or "Tous"

        all_experts = sorted(
            list(set([e for item in rcp_data for e in item["experts"]]))
        )
        selected_experts = st.multiselect("Experts", options=all_experts)

        dates = [x["date"] for x in rcp_data if isinstance(x["date"], datetime)]
        date_range = None
        if dates:
            min_date, max_date = min(dates).date(), max(dates).date()
            date_range = st.date_input("Période", value=(min_date, max_date))

        sort_option = None
        if view_mode == "Cartes":
            sort_option = st.selectbox(
                "Trier par",
                [
                    "Urgence (Haute > Basse)",
                    "Urgence (Basse > Haute)",
                    "Date (Récent > Ancien)",
                    "Date (Ancien > Récent)",
                ],
            )

    filtered_patients = _filter_items(
        patient_data,
        search_term,
        selected_urgencies,
        completeness_filter,
        selected_experts,
        date_range,
    )
    filtered_rcps = _filter_items(
        rcp_data,
        search_term,
        selected_urgencies,
        completeness_filter,
        selected_experts,
        date_range,
    )

    # --- Affichage (Left) ---
    with col_main:
        # 1. Section Top : Dossiers Patients (basés sur la dernière RCP analysée)
        st.subheader("📁 Dossiers Patients")
        st.caption(
            f"{len(filtered_patients)} dossier(s) patient — synthétisé(s) sur la dernière RCP analysée"
        )
        if filtered_patients:
            if view_mode == "Cartes":
                sorted_patients = _sort_cards(filtered_patients, sort_option)
                display_as_cards(
                    sorted_patients,
                    section_prefix="patients",
                    is_patient_section=True,
                )
            else:
                display_as_list(
                    filtered_patients,
                    section_prefix="patients",
                    is_patient_section=True,
                )
        else:
            st.info("Aucun dossier patient ne correspond aux filtres.")

        st.divider()

        # 2. Section Bas : Dernières RCP scannées
        st.subheader("📄 Dernières RCP scannées")
        st.caption(f"{len(filtered_rcps)} fiche(s) RCP")
        if filtered_rcps:
            if view_mode == "Cartes":
                display_as_cards(
                    filtered_rcps,
                    section_prefix="rcp",
                    is_patient_section=False,
                )
            else:
                display_as_list(
                    filtered_rcps,
                    section_prefix="rcp",
                    is_patient_section=False,
                )
        else:
            st.info("Aucune fiche RCP ne correspond aux filtres.")


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    cards_view()
    if db_client is not None and hasattr(db_client, "close"):
        db_client.close()
