from datetime import datetime
from typing import Any
import streamlit as st

from src.application.config import AppConfig
from src.application.use_cases import PatientRecordService
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.queue import QueueBroker
from src.ui.patient_mdt.translations import get_agent_icon_and_label, translate

# Application configuration
app_conf = AppConfig()

# Database connection
db_client = None
if app_conf.rcp.display_type == "mongodb":
    db_client = Mongodb(app_conf)

logger = app_conf.set_logger("ui", default_context={"page": "cards"})


@st.dialog("Confirmation de suppression")
def delete_card(filename: str):
    st.error(
        f"Voulez-vous vraiment supprimer la fiche RCP : `{filename}` ?",
        icon=":material/warning:",
    )
    st.caption("Cette action est irréversible.")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "Confirmer la suppression",
            type="primary",
            icon=":material/delete_forever:",
            key=f"btn_danger_confirm_card_{filename}",
        ):
            record_service = PatientRecordService.from_config(
                app_conf, db_client=db_client
            )
            record_service.delete_patient_mdt_form_document(filename)
            st.rerun()


@st.dialog("Confirmation de suppression du dossier patient")
def delete_patient_card(patient_id: str, patient_name: str):
    st.error(
        f"Voulez-vous vraiment supprimer l'intégralité du dossier patient : **{patient_name}** ?",
        icon=":material/warning:",
    )
    st.caption(
        "Toutes les fiches RCP associées à ce patient seront supprimées. Cette action est irréversible."
    )
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "Confirmer la suppression du dossier",
            type="primary",
            icon=":material/delete_forever:",
            key=f"btn_danger_confirm_patient_{patient_id}",
        ):
            record_service = PatientRecordService.from_config(
                app_conf, db_client=db_client
            )
            record_service.delete_patient_record(patient_id)
            st.rerun()


def get_rcp_data() -> list[dict]:
    """Fetch PatientMDTForm records from the repository and format them for display."""
    if db_client is None or not hasattr(db_client, "database"):
        return []
    record_service = PatientRecordService.from_config(app_conf, db_client=db_client)
    return record_service.list_patient_mdt_form_cards()


@st.fragment(run_every="4s")
def render_queue_status_banner():
    """
    Display a discreet business status banner only when forms are currently
    processing or pending in the processing queue.
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

    with st.container(key="clinical_scroll_queue_banner"):
        c_info, c_btn = st.columns([5, 1], vertical_alignment="center")
        with c_info:
            st.info(
                f"**File de traitement active :** {processing} fiche(s) en cours d'analyse, "
                f"{pending} tâche(s) en attente.",
                icon=":material/hourglass_top:",
            )
        with c_btn:
            if st.button(
                "Actualiser",
                icon=":material/refresh:",
                key="btn_refresh_cards_queue",
                width="stretch",
            ):
                st.rerun(scope="app")


def get_patients_cards_data() -> list[dict]:
    """
    Fetch PatientRecords and build each patient card based on their latest analyzed PatientMDTForm.
    """
    if db_client is None or not hasattr(db_client, "database"):
        return []
    record_service = PatientRecordService.from_config(app_conf, db_client=db_client)
    return record_service.list_patient_cards()


def set_sort_order(column_key: str):
    """Set the session state for sorting the list view."""
    if st.session_state.get("list_sort_by") == column_key:
        st.session_state.list_sort_ascending = not st.session_state.get(
            "list_sort_ascending", False
        )
    else:
        st.session_state.list_sort_by = column_key
        st.session_state.list_sort_ascending = True


def _format_urgency_badge(urgency: str | None) -> str:
    if urgency == "Urgent":
        return ":red-badge[🚨 Priorité haute]"
    if urgency == "Semi-urgent":
        return ":orange-badge[🟠 Semi-urgent]"
    if urgency == "Standard":
        return ":green-badge[🟢 Standard]"
    return ":gray-badge[⚪ Non qualifié]"


def display_as_list(
    data: list[dict], section_prefix: str = "rcp", is_patient_section: bool = False
):
    """Display records as a sortable list/table."""
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
    default_val = default_value_map.get(sort_by, "")

    sorted_data = sorted(
        data,
        key=lambda x: x.get(sort_by) if x.get(sort_by) is not None else default_val,
        reverse=not ascending,
    )

    def get_sort_indicator(column_key: str) -> str:
        if st.session_state.get("list_sort_by") == column_key:
            return " ▲" if st.session_state.get("list_sort_ascending") else " ▼"
        return ""

    # Clickable header
    header_cols = st.columns((3, 2, 2, 3, 4, 2), vertical_alignment="center")

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

    # Table body inside bordered row cards for scannability
    for item in sorted_data:
        with st.container(border=True):
            row_cols = st.columns((3, 2, 2, 3, 4, 2), vertical_alignment="center")

            refresh_str = (
                item["date_refresh"].strftime("%d/%m/%Y")
                if item.get("date_refresh")
                else "Inconnue"
            )
            rcp_count = item.get("rcp_count")
            title_text = (
                f"**{item['patient']}** (:blue-badge[{rcp_count} RCP])"
                if is_patient_section and rcp_count
                else f"**{item['patient']}**"
            )
            row_cols[0].markdown(
                title_text,
                help=f"Dernière mise à jour : {refresh_str} — Fiche : {item['file']}",
            )
            if not is_patient_section:
                row_cols[0].caption(f"📄 `{item['file']}`")

            # Date column
            date_str = (
                item["date"].strftime("%d/%m/%Y") if item.get("date") else "Inconnue"
            )
            row_cols[1].markdown(f"📅 {date_str}")

            # Urgency column
            row_cols[2].markdown(_format_urgency_badge(item.get("urgency")))

            # Status column
            with row_cols[3]:
                proc_status = item.get("processing_status")
                status_badges = []
                if proc_status == "PENDING_CLINICAL":
                    status_badges.append(":blue-badge[⏳ Extraction en attente]")
                elif proc_status == "PROCESSING_CLINICAL":
                    status_badges.append(":blue-badge[🔄 Extraction en cours]")
                elif proc_status == "PENDING_EXPERTS":
                    status_badges.append(":violet-badge[⏳ Concertation en attente]")
                elif proc_status == "PROCESSING_EXPERTS":
                    status_badges.append(":violet-badge[🩺 Concertation en cours]")
                elif proc_status == "FAILED":
                    status_badges.append(":red-badge[❌ Échec d'extraction]")
                elif item["missing"]:
                    status_badges.append(
                        f":orange-badge[⚠️ À compléter ({len(item['missing'])})]"
                    )
                else:
                    status_badges.append(":green-badge[✅ Dossier conforme]")

                care_req = item.get(
                    "care_adaptation_suggested", item.get("intervention_required")
                )
                care_type = item.get(
                    "proposed_care_type", item.get("intervention_type")
                )
                if care_req is True:
                    int_type = (
                        f" ({translate(care_type)})"
                        if care_type and len(str(care_type)) <= 24
                        else ""
                    )
                    status_badges.append(
                        f":red-badge[🧭 Adaptation suggérée{int_type}]"
                    )
                elif care_req is False:
                    status_badges.append(":gray-badge[Suivi habituel]")

                st.markdown(" ".join(status_badges))
                if item["missing"]:
                    with st.expander("⚠️ Pièces ou données requises"):
                        for m in item["missing"]:
                            st.markdown(f"- {m}")

            # Experts column
            if item["experts"]:
                row_cols[4].markdown(
                    " ".join(
                        [
                            f":violet-badge[{get_agent_icon_and_label(e)[0]} {get_agent_icon_and_label(e)[1]}]"
                            for e in item["experts"]
                        ]
                    )
                )
            else:
                row_cols[4].caption("Non déterminé")

            # Actions column
            unique_id = (
                item.get("patient_id") or item["file"]
                if is_patient_section
                else item["file"]
            )
            needs_id = not is_patient_section and (
                item.get("patient") == "Inconnu"
                or item.get("processing_status") == "FAILED"
            )
            with row_cols[5]:
                if needs_id:
                    b1, b_id, b2 = st.columns([2, 1, 1])
                else:
                    b1, b2 = st.columns([2, 1])
                    b_id = None
                with b1:
                    st.link_button(
                        "👁️ Consulter",
                        item["link"],
                        width="stretch",
                        help="Ouvrir le dossier clinique structuré",
                    )
                if b_id is not None:
                    with b_id:
                        st.link_button(
                            ":material/person_add:",
                            f"{item['link']}&action=identify",
                            width="stretch",
                            help="Saisir l'identité du patient ou rattacher la fiche à un dossier existant",
                        )
                with b2:
                    if st.button(
                        ":material/delete:",
                        key=f"btn_del_list_{section_prefix}_{unique_id}",
                        type="secondary",
                        width="stretch",
                        help="Supprimer ce dossier (action irréversible)",
                    ):
                        if is_patient_section and item.get("patient_id"):
                            delete_patient_card(item["patient_id"], item["patient"])
                        else:
                            delete_card(item["file"])


def display_as_cards(
    data: list[dict], section_prefix: str = "rcp", is_patient_section: bool = False
):
    """Display records as equal-height cards in a 3-column grid."""
    for row_start in range(0, len(data), 3):
        row_items = data[row_start : row_start + 3]
        cols = st.columns(3)
        for offset, item in enumerate(row_items):
            i = row_start + offset
            with cols[offset]:
                with st.container(border=True, height="stretch"):
                    badge_urgent = _format_urgency_badge(item.get("urgency"))

                    proc_status = item.get("processing_status")
                    badge_status = ""
                    if proc_status == "PENDING_CLINICAL":
                        badge_status = ":blue-badge[⏳ Extraction en attente]"
                    elif proc_status == "PROCESSING_CLINICAL":
                        badge_status = ":blue-badge[🔄 Extraction en cours]"
                    elif proc_status == "PENDING_EXPERTS":
                        badge_status = ":violet-badge[⏳ Concertation en attente]"
                    elif proc_status == "PROCESSING_EXPERTS":
                        badge_status = ":violet-badge[🩺 Concertation en cours]"
                    elif proc_status == "FAILED":
                        badge_status = ":red-badge[❌ Échec d'extraction]"
                    elif item["missing"]:
                        badge_status = (
                            f":orange-badge[⚠️ À compléter ({len(item['missing'])})]"
                        )
                    else:
                        badge_status = ":green-badge[✅ Dossier conforme]"

                    badge_intervention = ""
                    care_req = item.get(
                        "care_adaptation_suggested", item.get("intervention_required")
                    )
                    care_type = item.get(
                        "proposed_care_type", item.get("intervention_type")
                    )
                    if care_req is True:
                        int_type = (
                            f" ({translate(care_type)})"
                            if care_type and len(str(care_type)) <= 24
                            else ""
                        )
                        badge_intervention = (
                            f":red-badge[🧭 Adaptation suggérée{int_type}]"
                        )
                    elif care_req is False:
                        badge_intervention = ":gray-badge[Suivi habituel]"

                    badge_rcp_count = ""
                    if is_patient_section and item.get("rcp_count"):
                        badge_rcp_count = f":blue-badge[🗂️ {item['rcp_count']} RCP]"

                    refresh_str = (
                        item["date_refresh"].strftime("%d/%m/%Y")
                        if item.get("date_refresh")
                        else "Inconnue"
                    )
                    st.subheader(
                        item["patient"],
                        help=f"Dernière structuration : {refresh_str} — Source : {item['file']}",
                    )

                    badges = [
                        badge_urgent,
                        badge_status,
                        badge_rcp_count,
                        badge_intervention,
                    ]
                    badges_str = " ".join([b for b in badges if b])
                    if badges_str:
                        st.markdown(badges_str)

                    if item["date"] is not None:
                        date_caption = (
                            f"📅 Dernière séance RCP : **{item['date'].strftime('%d/%m/%Y')}**"
                            if is_patient_section
                            else f"📅 Date de séance RCP : **{item['date'].strftime('%d/%m/%Y')}**"
                        )
                        st.caption(date_caption)
                    else:
                        st.caption("📅 Date de séance non renseignée")

                    if not is_patient_section:
                        st.caption(f"📄 `{item['file']}`")

                    # Experts
                    if item["experts"]:
                        experts_badges = " ".join(
                            [
                                f":violet-badge[{get_agent_icon_and_label(e)[0]} {get_agent_icon_and_label(e)[1]}]"
                                for e in item["experts"]
                            ]
                        )
                        st.markdown(f"**Expertise requise :** {experts_badges}")
                    else:
                        st.caption("**Expertise requise :** Non qualifiée")

                    # Push footer elements (missing items expander + action buttons) to the bottom of the card
                    st.space("stretch")

                    # Missing items
                    if item["missing"]:
                        with st.expander(
                            f"⚠️ Éléments requis manquants ({len(item['missing'])})",
                        ):
                            for m in item["missing"]:
                                st.markdown(f"- {m}")

                    # Action buttons
                    unique_id = (
                        item.get("patient_id") or item["file"]
                        if is_patient_section
                        else item["file"]
                    )
                    needs_id = not is_patient_section and (
                        item.get("patient") == "Inconnu"
                        or item.get("processing_status") == "FAILED"
                    )
                    if needs_id:
                        b1, b_id, b2 = st.columns(
                            [3, 1, 1], vertical_alignment="bottom"
                        )
                    else:
                        b1, b2 = st.columns([3, 1], vertical_alignment="bottom")
                        b_id = None
                    with b1:
                        st.link_button(
                            "👁️ Consulter le dossier",
                            item["link"],
                            width="stretch",
                        )
                    if b_id is not None:
                        with b_id:
                            st.link_button(
                                ":material/person_add:",
                                f"{item['link']}&action=identify",
                                width="stretch",
                                help="Saisir l'identité du patient ou rattacher la fiche à un dossier existant",
                            )
                    with b2:
                        if st.button(
                            ":material/delete:",
                            key=f"btn_del_card_{section_prefix}_{unique_id}_{i}",
                            type="secondary",
                            width="stretch",
                            help="Supprimer ce dossier (action irréversible)",
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
    """Apply dashboard filters to a list of card items."""
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
    """Sort a list of card items according to the selected sort option."""
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


def render_kpi_summary(patient_data: list[dict], rcp_data: list[dict]):
    """Render clinical triage KPI metrics at the top of the dashboard."""
    source = patient_data if patient_data else rcp_data
    total_patients = len(patient_data)
    urgent_count = sum(1 for item in source if item.get("urgency") == "Urgent")
    incomplete_count = sum(1 for item in source if len(item.get("missing", [])) > 0)
    total_rcps = len(rcp_data)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "📁 Dossiers structurés",
        total_patients,
        f"{total_rcps} document(s) intégré(s)",
        border=True,
        height="stretch",
    )
    k2.metric(
        "🚨 Priorité haute (RCP)",
        urgent_count,
        delta="Passage prioritaire" if urgent_count > 0 else "Aucune urgence critique",
        delta_color="inverse" if urgent_count > 0 else "off",
        border=True,
        height="stretch",
    )
    k3.metric(
        "⚠️ Contrôle de complétude",
        incomplete_count,
        delta="Pièces à compléter" if incomplete_count > 0 else "Conformité validée",
        delta_color="inverse" if incomplete_count > 0 else "normal",
        border=True,
        height="stretch",
    )
    interventions_count = sum(
        1
        for item in source
        if item.get("care_adaptation_suggested", item.get("intervention_required"))
        is True
    )
    k4.metric(
        "🧭 Orientations / Adaptations",
        interventions_count,
        delta="Adaptation à discuter" if interventions_count > 0 else "Suivi habituel",
        delta_color="off",
        border=True,
        height="stretch",
    )


def cards_view():
    title_col, action_col = st.columns([4, 1.2], vertical_alignment="center")
    with title_col:
        st.title("📇 Préparation & Ordonnancement RCP")
        st.caption(
            "L'outil d'analyse documentaire qui prépare le terrain pour faciliter et optimiser la décision médicale collégiale."
        )
    with action_col:
        if st.button(
            "📥 Intégrer des documents",
            type="primary",
            width="stretch",
        ):
            st.switch_page("src/ui/patient_mdt/upload.py")

    render_queue_status_banner()

    rcp_data = get_rcp_data()
    patient_data = get_patients_cards_data()

    if not rcp_data and not patient_data:
        with st.container(border=True):
            st.subheader("📋 Aucun dossier préparé pour la séance RCP")
            st.markdown(
                "**DataSyntis** libère du temps médical utile en transformant le chaos documentaire "
                "en dossiers directement exploitables pour la décision RCP :"
            )
            p1, p2, p3 = st.columns(3)
            with p1:
                st.markdown(
                    "📄 **Exhaustivité documentaire**\n\n"
                    "Ingestion multi-PDF agnostique et consolidation chronologique par patient."
                )
            with p2:
                st.markdown(
                    "✅ **Conformité aux recommandations**\n\n"
                    "Contrôle systématique de complétude et propositions cadrées sur les référentiels."
                )
            with p3:
                st.markdown(
                    "🩺 **Fluidité logistique**\n\n"
                    "Ordonnancement de la séance selon le degré d'urgence et l'expertise requise."
                )
        return

    render_kpi_summary(patient_data, rcp_data)

    # --- Compact Full-Width Filter & View Toolbar ---
    with st.container(border=True):
        f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns(
            [3, 2, 2, 1.5, 1.2], vertical_alignment="bottom"
        )
        with f_col1:
            search_term = st.text_input(
                "Rechercher un dossier ou une pièce",
                placeholder="Identité patient, référence PDF...",
                icon=":material/search:",
            )
        with f_col2:
            completeness_filter = st.segmented_control(
                "Contrôle de complétude",
                options=["Tous", "Complet", "Incomplet"],
                default="Tous",
                width="stretch",
            )
            completeness_filter = completeness_filter or "Tous"
        with f_col3:
            sort_option = st.selectbox(
                "Ordonnancement de séance",
                [
                    "Urgence (Haute > Basse)",
                    "Urgence (Basse > Haute)",
                    "Date (Récent > Ancien)",
                    "Date (Ancien > Récent)",
                ],
            )
        with f_col4:
            view_mode = st.segmented_control(
                "Affichage",
                options=["Cartes", "Liste"],
                default="Cartes",
                width="stretch",
            )
            view_mode = view_mode or "Cartes"
        with f_col5:
            with st.popover(
                "🔍 Filtres",
                width="stretch",
            ):
                urgency_options = ["Urgent", "Semi-urgent", "Standard", "Indéfini"]
                selected_urgencies = st.multiselect(
                    "Niveaux de priorité",
                    options=urgency_options,
                    default=urgency_options,
                )

                all_experts = sorted(
                    list(set([e for item in rcp_data for e in item["experts"]]))
                )
                selected_experts = st.multiselect(
                    "Expertise requise", options=all_experts
                )

                dates = [x["date"] for x in rcp_data if isinstance(x["date"], datetime)]
                date_range = None
                if dates:
                    min_date, max_date = min(dates).date(), max(dates).date()
                    date_range = st.date_input(
                        "Période de séance RCP", value=(min_date, max_date)
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

    tab_patients, tab_rcps = st.tabs(
        [
            f"📁 Dossiers patients consolidés ({len(filtered_patients)})",
            f"📄 Flux documentaire RCP ({len(filtered_rcps)})",
        ]
    )

    with tab_patients:
        if filtered_patients:
            sorted_patients = _sort_cards(filtered_patients, sort_option)
            if view_mode == "Cartes":
                display_as_cards(
                    sorted_patients,
                    section_prefix="patients",
                    is_patient_section=True,
                )
            else:
                display_as_list(
                    sorted_patients,
                    section_prefix="patients",
                    is_patient_section=True,
                )
        else:
            st.info(
                "Aucun dossier patient ne correspond aux filtres sélectionnés.",
                icon=":material/search_off:",
            )

    with tab_rcps:
        if filtered_rcps:
            sorted_rcps = _sort_cards(filtered_rcps, sort_option)
            if view_mode == "Cartes":
                display_as_cards(
                    sorted_rcps,
                    section_prefix="rcp",
                    is_patient_section=False,
                )
            else:
                display_as_list(
                    sorted_rcps,
                    section_prefix="rcp",
                    is_patient_section=False,
                )
        else:
            st.info(
                "Aucune fiche RCP ne correspond aux filtres sélectionnés.",
                icon=":material/search_off:",
            )


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    cards_view()
    if db_client is not None and hasattr(db_client, "close"):
        db_client.close()
