import streamlit as st

from src.domain.agents import Agents
from src.application.reader import DocumentReader
from src.application.config import AppConfig


def read(ressource: str, config: AppConfig):
    with st.spinner(f"Indexation de {ressource}..."):
        rag = DocumentReader(config, document=ressource, document_type="ressource")
        rag.read_document()
    st.toast(f"Ressource '{ressource}' indexée avec succès !", icon="✅")


app_conf = AppConfig()

pmtd = Agents()
st.title("🕵️ Liste des agents")

cols = st.columns(3)
indexed_cache: dict[str, bool] = {}

for i, (n, a) in enumerate(pmtd.list.items()):
    with cols[i % 3]:
        with st.container(border=True):
            system_prompt = (
                a.get_system_prompt()
                if hasattr(a, "get_system_prompt")
                else getattr(a, "system_prompt", "")
            )
            models = (
                a.get_models(app_conf)
                if hasattr(a, "get_models")
                else (
                    getattr(a, "models", None)
                    or [m.strip() for m in app_conf.llm.models.split(",") if m.strip()]
                )
            )
            ressources = getattr(a, "ressources", [])

            st.subheader(n)
            with st.expander("Configuration"):
                st.markdown("**Prompt :**")
                st.caption(system_prompt)
                st.markdown("**Modèles :**")
                for m in models:
                    st.markdown(f"- {m}")
            st.divider()
            st.markdown("**Ressources :**")
            for r in ressources:
                if r not in indexed_cache:
                    rag = DocumentReader(
                        app_conf, document=r, document_type="ressource"
                    )
                    try:
                        indexed_cache[r] = rag.is_indexed()
                    except Exception:
                        indexed_cache[r] = False
                is_idx = indexed_cache[r]

                c1, c2 = st.columns([3, 1], vertical_alignment="center")
                btn_name = f"📄 {r} ✅" if is_idx else f"📄 {r} ⚠️"
                if c1.button(
                    btn_name,
                    key=f"link_{n}_{r}",
                    width="stretch",
                    help="Consulter cette ressource",
                ):
                    st.switch_page(
                        "src/ui/patient_mdt/ressources.py",
                        query_params={"resource": r},
                    )

                button_label = "Re-Index" if is_idx else "Index"
                if c2.button(button_label, key=f"{n}_{r}", width="stretch"):
                    read(r, app_conf)
                    st.rerun()
