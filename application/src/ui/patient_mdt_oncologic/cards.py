import environ
import pytz
from datetime import datetime
import streamlit as st

from src.application.config import AppConfig
from src.application.app_functions import delete_document
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.common_ressources import PatientPriority

# Configuration de l'application
app_conf = environ.to_config(AppConfig)

# Connexion Base de données
if app_conf.rcp.display_type == "mongodb":
    db_client = Mongodb(app_conf)

logger = app_conf.set_logger("ui", default_context={"page": "cards"})


@st.dialog("Confirmation de suppression")
def delete_card(filename: str):
    st.warning(f"Voulez-vous vraiment supprimer le dossier : {filename} ?")
    st.markdown("Cette action est irréversible.")
    if st.button("Confirmer la suppression", type="primary"):
        delete_document(app_conf, filename)
        st.rerun()


def get_rcp_data():
    """Récupère les données RCP depuis MongoDB et les formate pour l'affichage."""
    if not hasattr(db_client, "database"):
        return []

    db_datas = list(db_client.database["rcp_info"].find())

    cards_data = []
    for d in db_datas:
        # Données Patient
        patient_name = "Inconnu"
        if "PatientAdministrative" in d:
            p = d["PatientAdministrative"]
            patient_name = f"{p.get('first_name', '')} {p.get('last_name', '')}"

        # Date
        date_refresh = d.get(
            "ui_date",
            datetime.now(pytz.timezone("Europe/Paris")).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )

        date_mcp = (
            d["PatientAdministrative"]["date_rcp"]
            if "PatientAdministrative" in d and "date_rcp" in d["PatientAdministrative"]
            else None
        )
        if isinstance(date_mcp, str):
            date_mcp = datetime.fromisoformat(date_mcp)

        # Experts Pertinents & Urgence
        relevant_experts = []
        urgency_level = "Indéfini"
        urgency_score = 0  # 0: Low/None, 1: Medium, 2: Urgent

        if "ExpertAnswer" in d and isinstance(d["ExpertAnswer"], dict):
            for agent_name, agent_data in d["ExpertAnswer"].items():
                if isinstance(agent_data, dict):
                    if agent_data.get("expert_relevant"):
                        relevant_experts.append(agent_name)

                    # Urgence
                    p_prio = str(agent_data.get("patient_priority", "")).lower()
                    for urgency in list(PatientPriority):
                        if p_prio == urgency.value.lower():
                            if urgency.name == "urgent":
                                if urgency_score < 2:
                                    urgency_score = 2
                                    urgency_level = "Urgent"
                            elif urgency.name == "medium":
                                if urgency_score < 1:
                                    urgency_score = 1
                                    urgency_level = "Semi-urgent"
                            elif urgency.name == "low":
                                urgency_level = "Standard"

        # Données Manquantes
        missing_data = []
        if "MTDCompleted" in d and isinstance(d["MTDCompleted"], dict):
            for agent_name, agent_data in d["MTDCompleted"].items():
                if isinstance(agent_data, dict):
                    mtd_comp = agent_data.get("mtd_complete")
                    if isinstance(mtd_comp, dict):
                        m = mtd_comp.get("what_missing", [])
                        if isinstance(m, list):
                            missing_data.extend(m)
        else:
             missing_data.extend(["no data"])

        cards_data.append(
            {
                "file": d["file"],
                "patient": patient_name,
                "date_refresh": date_refresh,
                "date": date_mcp ,
                "experts": relevant_experts,
                "missing": list(set(missing_data)),
                "urgency": urgency_level,
                "urgency_score": urgency_score,
                "link": f"datas/?file={d['file']}",
            }
        )

    return cards_data


def cards_view():
    st.title("📇 Tableau de bord RCP")

    data = get_rcp_data()

    if not data:
        st.info("Aucune fiche RCP trouvée.")
        return

    # Layout: Main content (Left) | Filters (Right)
    col_main, col_filters = st.columns([3, 1])

    # --- Filtres (Right) ---
    with col_filters:
        st.subheader("🔍 Filtres")

        search_term = st.text_input("Rechercher", placeholder="Patient, Fichier...")

        # Urgency Filter
        urgency_options = ["Urgent", "Semi-urgent", "Standard", "Indéfini"]
        selected_urgencies = st.multiselect(
            "Urgence", options=urgency_options, default=urgency_options
        )

        # Completeness Filter
        completeness_filter = st.radio(
            "Statut dossier", ["Tous", "Complet", "Incomplet"], index=0
        )

        # Experts Filter
        all_experts = sorted(list(set([e for item in data for e in item["experts"]])))
        selected_experts = st.multiselect("Experts", options=all_experts)

        # Date Filter
        dates = [x["date"] for x in data if isinstance(x["date"], datetime)]
        date_range = None
        if dates:
            min_date, max_date = min(dates).date(), max(dates).date()
            date_range = st.date_input("Période", value=(min_date, max_date))

        # Sorting
        sort_option = st.selectbox(
            "Trier par",
            [
                "Urgence (Haute > Basse)",
                "Urgence (Basse > Haute)",
                "Date (Récent > Ancien)",
                "Date (Ancien > Récent)",
            ],
        )

    # --- Filtrage des données ---
    filtered_data = []
    for item in data:
        # Recherche textuelle
        if search_term:
            term = search_term.lower()
            if term not in item["patient"].lower() and term not in item["file"].lower():
                continue

        # Filtre Urgence
        if item["urgency"] not in selected_urgencies:
            continue

        # Filtre Incomplet
        is_incomplete = len(item["missing"]) > 0
        if completeness_filter == "Complet" and is_incomplete:
            continue
        if completeness_filter == "Incomplet" and not is_incomplete:
            continue

        # Filtre Experts
        if selected_experts:
            if not any(e in item["experts"] for e in selected_experts):
                continue

        # Filtre Date
        if date_range and len(date_range) == 2:
            start, end = date_range
            if item["date"]: 
                if not (start <= item["date"].date() <= end):
                    continue

        filtered_data.append(item)

    # --- Tri des données ---
    if sort_option == "Urgence (Haute > Basse)":
        filtered_data.sort(key=lambda x: x["urgency_score"], reverse=True)
    elif sort_option == "Urgence (Basse > Haute)":
        filtered_data.sort(key=lambda x: x["urgency_score"], reverse=False)
    elif sort_option == "Date (Récent > Ancien)":
        filtered_data.sort(key=lambda x: x["date"], reverse=True)
    elif sort_option == "Date (Ancien > Récent)":
        filtered_data.sort(key=lambda x: x["date"], reverse=False)

    # --- Affichage Cartes (Left) ---
    with col_main:
        st.caption(f"{len(filtered_data)} fiche(s)")

        cols = st.columns(3)
        for i, item in enumerate(filtered_data):
            col = cols[i % 3]
            with col:
                with st.container(border=True):
                    # Urgence Badge
                    badge_urgent = ""
                    if item["urgency"] == "Urgent":
                        badge_urgent = ":red-badge[🚨 urgent]"
                    elif item["urgency"] == "Semi-urgent":
                        badge_urgent = ":orange-badge[🟠 medium]"
                    # elif item["urgency"] == "Standard":
                    #     badge_urgent=":green-badge[🟢 not urgent]"
                    # else:
                    #     badge_urgent=":green-badge[⚪ urgent unknown]"

                    if item["missing"]:
                        badge_missing = ":orange-badge[⚠️ Dossier Incomplet]"

                    st.subheader(
                        item["patient"],
                        help=f"Refresh : {item["date_refresh"].strftime('%d-%m-%Y')} - Fichier: {item['file']}",
                    )
                    st.markdown(f"{badge_urgent} {badge_missing}")
                    
                    if item['date'] is not None:
                        st.caption(f"📅 {item['date'].strftime('%d-%m-%Y')}")
                    else:
                        st.caption("📅 Inconnu")

                    # Experts
                    if item["experts"]:
                        st.markdown(
                            "**Experts:** "
                            + ", ".join([f"`{e}`" for e in item["experts"]])
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
                    b1, b2 = st.columns(2)
                    with b1:
                        st.link_button("Ouvrir", item["link"], use_container_width=True)
                    with b2:
                        if st.button(
                            "Supprimer",
                            key=f"btn_del_{item['file']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            delete_card(item["file"])


if __name__ == "__main__":
    cards_view()
    db_client.close()
