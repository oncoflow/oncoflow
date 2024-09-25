import environ
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from pandas import DataFrame

from src.application.config import AppConfig
from src.infrastructure.documents.mongodb import Mongodb

app_conf = environ.to_config(AppConfig)

if app_conf.rcp.display_type == "mongodb":
    client = Mongodb(app_conf)

PAGES_DIR_SRC = "src/ui"


def all_datas():
    db_datas = client.database["rcp_info"].find()

    datas = [
        {
            "file": d["file"],
            "performance_status": d["PatientPerformanceStatus"]["performance_status"],
            "link": f"/?file={d['file']}",
        }
        for d in list(db_datas)
    ]

    df = DataFrame(list(datas))

    st.dataframe(
        df,
        column_config={
            "file": "Nom de la fiche",
            "performance_status": st.column_config.NumberColumn(
                "Performance", help="Status de performance"
            ),
            "link": st.column_config.LinkColumn(display_text="More Information"),
        },
    )


def form():
    st.set_page_config(layout="wide")
    if st.button("Go Back"):
        st.query_params.clear()
        st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt_oncologic/datas.py")
    col1, col2 = st.columns([1, 2],gap="medium")
    col2.title("Informations about Form from IA")
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
                """
    )
    col2.header("Examens Radiologique", divider=True)
    r_str = ""
    for r in datas["RadiologicExams"]["exams_list"]:
        r_str = f"""{r_str}
                - **{r["exam_name"]} ({r["exam_type"]})** *le {r["exam_date"]}*: {r["exam_result"]}
               """
    col2.markdown(r_str)


if "file" not in st.query_params:
    all_datas()
else:
    form()
