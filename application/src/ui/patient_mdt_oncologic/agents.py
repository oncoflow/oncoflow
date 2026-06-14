import streamlit as st

from src.domain.agents import Agents
from src.application.reader import DocumentReader
from src.application.config import AppConfig


def read(ressource: str, config: AppConfig):
    with st.spinner(f"Indexation de {ressource}..."):
        rag = DocumentReader(config, document=ressource, document_type="ressource")
        rag.read_document()
    st.toast(f"Ressource '{ressource}' indexée avec succès !", icon="✅")


pmtd = Agents()
st.title("🕵️ Liste des agents")

cols = st.columns(3)
app_conf = AppConfig()
for i, (n, a) in enumerate(pmtd.list.items()):
    with cols[i % 3]:
        with st.container(border=True):
            ag = a(app_conf)
            st.subheader(n)
            with st.expander("Configuration"):
                st.markdown("**Prompt :**")
                st.caption(ag.system_prompt)
                st.markdown("**Modèles :**")
                for m in ag.models:
                    st.markdown(f"- {m}")
            st.divider()
            st.markdown("**Ressources :**")
            for r in ag.ressources:
                rag = DocumentReader(app_conf, document=r, document_type="ressource")
                is_idx = False
                try:
                    is_idx = rag.is_indexed()
                except Exception:
                    pass

                c1, c2 = st.columns([3, 1], vertical_alignment="center")
                if is_idx:
                    c1.markdown(f"📄 **{r}** :green[✓]")
                else:
                    c1.caption(f"📄 {r}")

                button_label = "Re-Index" if is_idx else "Index"
                if c2.button(button_label, key=f"{n}_{r}", use_container_width=True):
                    read(r, app_conf)
                    st.rerun()
