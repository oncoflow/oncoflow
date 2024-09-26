import environ
import streamlit as st
import time

from src.application.config import AppConfig
from src.application.app_functions import full_read_file


app_conf = environ.to_config(AppConfig)
PAGES_DIR_SRC = "src/ui"
uploaded_files = st.file_uploader("Choisir un fichier", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    with st.status("Chargement des fichiers pdf ..."):
        for uploaded_file in uploaded_files:
            f=f"{uploaded_file.name}"
            bytes_data = uploaded_file.getvalue()
            st.write(f"Chargement du fichier pdf {f}...")
            with open(f"{app_conf.rcp.path}/{f}" , "wb") as pdf:
                pdf.write(bytes_data)
            
            st.write("Passage de l'IA...")
            full_read_file(app_conf=app_conf, filename=f)
            st.write("Succès")
            time.sleep(1)
        st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt_oncologic/datas.py")