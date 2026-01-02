import streamlit as st
import environ
from src.domain.agents import Agents
from src.application.reader import DocumentReader
from src.application.config import AppConfig

from pydantic import BaseModel


def read(ressource: str):
    app_conf = environ.to_config(AppConfig)
    rag = DocumentReader(app_conf, document=ressource, document_type="ressource")
    rag.read_document()


@st.dialog("Description")
def agent(agent: BaseModel):
    app_conf = environ.to_config(AppConfig)
    ag = agent(app_conf)
    st.write(f"Agent : {a.__name__}")
    st.write(f"Prompt : {ag.system_prompt}")
    st.write(f"Custom Model : {ag.models}")
    st.write("Ressources :")
    for r in ag.ressources:
        c = st.container(horizontal=True, horizontal_alignment="distribute")
        c.write("- {r}".format(r=r))
        if c.button("Read ressource"):
            read(r)


pmtd = Agents()
st.title("List of agents")
c = st.container(horizontal=True, horizontal_alignment="distribute")

for n, a in pmtd.list.items():
    if c.button(n):
        agent(a)
