import streamlit as st
import environ
from src.domain.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.application.reader import DocumentReader
from src.application.config import AppConfig

from pydantic import BaseModel

pmtd = PatientMDTOncologicForm()

def read(ressource: str):
    app_conf = environ.to_config(AppConfig)
    rag = DocumentReader(app_conf, document=ressource, document_type="ressource")
    rag.read_document()


@st.dialog("Description")
def agent(agent: BaseModel):
    ag = agent()
    st.write(f"Agent : {a.__name__}")
    st.write(f"Prompt : {ag.system_prompt}")
    st.write(f"Custom Model : {ag.models}")
    st.write("Ressources :")
    for r in ag.ressources:
        c = st.container(horizontal=True, horizontal_alignment="distribute")
        c.write("- {r}".format(r=r))
        if c.button("Read ressource"):
            read(r)



st.title("List of agents")
c = st.container(horizontal=True, horizontal_alignment="distribute")

for a in pmtd.agent_list:
    if c.button(a.__name__):
        agent(a)
