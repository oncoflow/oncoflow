import environ
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from pandas import DataFrame

from src.infrastructure.llm.ollama import OllamaConnect

from src.application.config import AppConfig
from src.application.app_functions import delete_document, full_read_file
from src.infrastructure.documents.mongodb import Mongodb

app_conf = environ.to_config(AppConfig)

if app_conf.rcp.display_type == "mongodb":
    client = Mongodb(app_conf)

PAGES_DIR_SRC = "src/ui"

@st.dialog("Êtes-vous sûr ?")
def delete(items: DataFrame):
    st.write(f"Vous êtes sur le point de supprimer {items['file'].to_string()}")
    if st.button("confirmer"):
        for doc in items["file"].to_list():
            delete_document(app_conf, doc)
        st.rerun()

def all_datas():
    st.query_params.clear()
    db_datas = client.database["rcp_info"].find()
    st.title("Liste des fiches RCP par priorité")
    datas = [
        {
            "file": d["file"],
            "performance_status": d["PatientPerformanceStatus"]["performance_status"] if "PatientPerformanceStatus" in d else "N/A",
            "link": f"/?file={d['file']}",
           # "delete": False
        }
        for d in list(db_datas)
    ]

    df = DataFrame(list(datas))
    df.insert(0, "Delete", False)
    

    edited_df = st.data_editor(
        df,
        column_config={
            "file": "Nom de la fiche",
            "performance_status": st.column_config.NumberColumn(
                "Performance", help="Status de performance"
            ),
            "link": st.column_config.LinkColumn(display_text="Details"),
            "Delete": "Sélectionner"
        },
        hide_index=True,
        disabled=["file", "performance_status", "link"]
    )
    if st.button("Supprimer toute les selection"):
        if len(edited_df[edited_df.Delete].index) > 0:
            delete(edited_df[edited_df.Delete])

def form():
    head1, head2, head3 = st.columns(3)
    if head1.button("Go Back"):
        st.query_params.clear()
        st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt_oncologic/datas.py")
    if "power" in st.session_state:
        if st.session_state["power"]:
            po = head2.popover("Rerun AI")
            m = app_conf.llm.models
            nm = po.selectbox("Modèle", OllamaConnect(app_conf).get_models(),placeholder="Select modèle")
            
            if po.button("Rerun"):
                app_conf.llm.models = nm
                with st.status("Rerun AI ..."):
                    full_read_file(app_conf=app_conf, filename=st.query_params['file'])
                    app_conf.llm.models = m
                    st.write("Succès")
                st.rerun()
    
    col1, col2 = st.columns([1, 2], gap="medium")
    col2.title("Informations récupérées")
    with col1:
        pdf_viewer(f"{app_conf.rcp.path}/{st.query_params['file']}")
    datas = client.database["rcp_info"].find_one({"file": st.query_params["file"]})
    col2.header("Informations patient", divider=True)
    col2.markdown(
        f"""
                  - **Prénom nom**: {datas['PatientAdministrative']['first_name']} {datas['PatientAdministrative']['last_name']}
                  - **Age**: {datas['PatientAdministrative']['age']}
                  - **Genre**: {datas['PatientAdministrative']['gender']}
                  """
    )
    col2.header("Informations sur la maladie", divider=True)
    col2.markdown(
        f"""
                - **Localisation de la tumeur** : {datas['TumorLocation']['tumor_location']} 
                - **Biologie de la tumeur** : {datas['TumorBiology']['msi_state']}
                - **Opération curative passée** :  {datas['PreviousCurativeSurgery']['previous_curative_surgery']}
                """
    )
    col2.header("Examens Radiologique", divider=True)
    r_str = ""
    for r in datas["RadiologicExams"]["exams_list"]:
        r_str = f"""{r_str}
                - **{r["exam_name"]} ({r["exam_type"]})** *le {r["exam_date"]}*: {r["exam_result"]}
               """
    col2.markdown(r_str)

    col2.header("Traitements Chimiotherapie", divider=True)
    c_str = ""
    for c in datas["ChemotherapyTreament"]["chemotherapy_list"]:
        c_str = f"""{c_str}
            - **{c["chemotherapy_name"]}** (*{c["chemotherapy_start_date"]} - {c["chemotherapy_end_date"]}*) : tolérance {c["chemotherapy_tolerance"]}
            """
    col2.markdown(c_str)


power = st.sidebar.toggle("Power mode")

if power:
    st.session_state["power"] = True
else:
    st.session_state["power"] = False


if "file" in st.query_params:
    form()
else:
    all_datas()

client.close()
