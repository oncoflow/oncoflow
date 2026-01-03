import environ
import pytz
from datetime import datetime
import streamlit as st

from src.application.config import AppConfig
from src.application.app_functions import delete_document
from src.infrastructure.documents.mongodb import Mongodb

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
        ui_date = d.get(
            "ui_date",
            datetime.now(pytz.timezone("Europe/Paris")).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )

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
                    if "urgent" in p_prio and "semi" not in p_prio and "pas" not in p_prio:
                        if urgency_score < 2:
                            urgency_score = 2
                            urgency_level = "Urgent"
                    elif "semi" in p_prio or "medium" in p_prio or "modéré" in p_prio:
                        if urgency_score < 1:
                            urgency_score = 1
                            urgency_level = "Semi-urgent"
                    elif ("pas" in p_prio or "low" in p_prio or "faible" in p_prio) and urgency_score == 0:
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
        
        cards_data.append({
            "file": d["file"],
            "patient": patient_name,
            "date": ui_date,
            "experts": relevant_experts,
            "missing": list(set(missing_data)),
            "urgency": urgency_level,
            "urgency_score": urgency_score,
            "link": f"datas/?file={d['file']}"
        })
        
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
        selected_urgencies = st.multiselect("Urgence", options=urgency_options, default=urgency_options)

        # Completeness Filter
        completeness_filter = st.radio("Statut dossier", ["Tous", "Complet", "Incomplet"], index=0)

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
            ["Urgence (Haute > Basse)", "Urgence (Basse > Haute)", "Date (Récent > Ancien)", "Date (Ancien > Récent)"]
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
            d_date = item["date"].date() if isinstance(item["date"], datetime) else item["date"]
            if not (start <= d_date <= end):
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
                    col_left, col_right = st.columns([1, 4])
                    with col_left:
                        # Urgence Badge
                        if item["urgency"] == "Urgent":
                            st.error("🚨")
                        elif item["urgency"] == "Semi-urgent":
                            st.warning("🟠")
                        elif item["urgency"] == "Standard":
                            st.success("🟢")
                        else:
                            st.info("⚪")

                        # Header Carte
                    with col_right:
                        st.subheader(item["patient"], help=f"{item["urgency"]} - Fichier: {item['file']}")
                    
                    # Manquants
                    if item["missing"]:
                        with st.expander(f"⚠️ **Dossier Incomplet** ({len(item['missing'])})"):
                            for m in item["missing"]:
                                st.markdown(f"- {m}")

                    st.caption(f"📅 {item['date'].strftime('%d-%m-%Y')}")
                     
                    # Experts
                    if item["experts"]:
                        st.markdown("**Experts:**" + ", ".join([f"`{e}`" for e in item["experts"]]))
                    
                    st.divider()
                    
                    # Boutons
                    b1, b2 = st.columns(2)
                    with b1:
                        st.link_button("Ouvrir", item["link"], use_container_width=True)
                    with b2:
                        if st.button("Supprimer", key=f"btn_del_{item['file']}", type="primary", use_container_width=True):
                            delete_card(item["file"])

if __name__ == "__main__":
    cards_view()
    db_client.close()
