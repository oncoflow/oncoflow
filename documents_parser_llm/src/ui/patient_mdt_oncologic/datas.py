import environ
import pytz
from datetime import datetime
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from pandas import DataFrame

from src.infrastructure.llm.ollama import OllamaConnect

from src.application.config import AppConfig
from src.application.app_functions import delete_document, full_read_file
from src.infrastructure.documents.mongodb import Mongodb

app_conf = environ.to_config(AppConfig)

if app_conf.rcp.display_type == "mongodb":
    db_client = Mongodb(app_conf)

PAGES_DIR_SRC = "src/ui"
logger = app_conf.set_logger("ui", default_context={"page": "datas"})

@st.dialog("Êtes-vous sûr ?")
def delete(items: DataFrame):
    st.write(f"Vous êtes sur le point de supprimer {items['file'].to_string()}")
    if st.button("confirmer"):
        for doc in items["file"].to_list():
            delete_document(app_conf, doc)
        st.rerun()


def update_date(filename, date):
    print(type(date))
    db_client.update_docs("rcp_info", {"file": filename}, {"$set": {"ui_date": date}})
    

def all_datas():
    st.query_params.clear()
    db_datas = db_client.database["rcp_info"].find()
    memory_date = {}
    st.title("Liste des fiches RCP par priorité")
    datas = [
        {
            "file": d["file"],
            "performance_status": d["PatientPerformanceStatus"]["performance_status"] if "PatientPerformanceStatus" in d else "N/A",
            "link": f"/?file={d['file']}",
            "date": datetime.now(pytz.timezone("Europe/Paris")).replace(hour=0, minute=0, second=0, microsecond=0)
                    if "ui_date" not in d else d["ui_date"]
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
            "Delete": "Sélectionner",
            "date": st.column_config.DatetimeColumn(
                "Date de réunion", format="DD-MM-YYYY HH:mm:ss"),
            "link": st.column_config.LinkColumn(display_text="Details"),
        },
        hide_index=True,
        disabled=["file", "performance_status", "link"],
        key='datas'
    )

    if len(st.session_state["datas"]["edited_rows"].items()) > 0:
        for row, col in st.session_state["datas"]["edited_rows"].items():
            if "date" in col:
                if row in memory_date:
                    if st.session_state["datas"]["edited_rows"][row]["date"] == memory_date[row]:
                        pass
                memory_date[row] = st.session_state["datas"]["edited_rows"][row]["date"]
                update_date(edited_df.loc[row]["file"], edited_df.loc[row]["date"])

                
    if st.button("Supprimer toute les selection"):
        if len(edited_df[edited_df.Delete].index) > 0:
            delete(edited_df[edited_df.Delete])

def form():
    head1, head2 = st.columns([1,2.5], vertical_alignment="bottom")
    hh1, hh2 = head1.columns([1,1.5], gap="small", vertical_alignment="bottom")
    if hh1.button("◀️ Go Back"):
        st.query_params.clear()
        st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt_oncologic/datas.py")
    with open(f"{app_conf.rcp.path}/{st.query_params['file']}", "rb") as file:
        hh2.download_button(
            label="⏬ Télécharger le PDF",
            data=file,
            file_name=st.query_params['file'],
            mime="application/pdf",
        )
    if "power" in st.session_state:
        if st.session_state["power"]:
            po = head2.popover(":repeat: AI process")
            m = app_conf.llm.models
            nm = po.selectbox("Modèle", OllamaConnect(app_conf).get_models(),placeholder="Select modèle")
            
            if po.button("Rerun"):
                app_conf.llm.models = nm
                with st.status("Rerun AI ..."):
                    full_read_file(app_conf=app_conf, filename=st.query_params['file'], logger=logger)
                    app_conf.llm.models = m
                    st.write("Succès")
                st.rerun()
    
    col1, col2 = st.columns([1, 1], gap="medium")
    col2.title("Informations récupérées")
    with col1:
        pdf_viewer(f"{app_conf.rcp.path}/{st.query_params['file']}")
    datas = db_client.database["rcp_info"].find_one({"file": st.query_params["file"]})
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

db_client.close()
