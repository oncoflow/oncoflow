import streamlit as st
import environ
from src.domain.agents import Agents
from src.application.reader import DocumentReader
from src.application.config import AppConfig

from pydantic import BaseModel


def read(ressource: str, config: AppConfig):
    with st.spinner(f"Indexation de {ressource}..."):
        rag = DocumentReader(config, document=ressource, document_type="ressource")
        rag.read_document()
    st.toast(f"Ressource '{ressource}' indexée avec succès !", icon="✅")



pmtd = Agents()
st.title("🕵️ Liste des agents")

cols = st.columns(3)
app_conf = environ.to_config(AppConfig)
for i, (n, a) in enumerate(pmtd.list.items()):
    with cols[i % 3]:
        with st.container(border=True):
            ag = a(app_conf)
            st.subheader(n)
            with st.expander("Configuration"):
                st.markdown("**Prompt :**")
                st.caption(ag.system_prompt)
                st.markdown("**Modèles :**")
                st.write(ag.models)
            st.divider()
            st.markdown("**Ressources :**")
            for r in ag.ressources:
                c1, c2 = st.columns([3, 1], vertical_alignment="center")
                c1.caption(f"📄 {r}")
                if c2.button("Index", key=f"{n}_{r}", use_container_width=True):
                    read(r, app_conf)
