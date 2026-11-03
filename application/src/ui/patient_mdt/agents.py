import streamlit as st

from src.domain.agents import get_domain_agents
from src.application.reader import DocumentReader
from src.application.config import AppConfig
from src.ui.patient_mdt.translations import get_agent_icon_and_label


def read(ressource: str, config: AppConfig):
    with st.spinner(f"Indexation de {ressource}..."):
        rag = DocumentReader(config, document=ressource, document_type="ressource")
        rag.read_document()
    st.toast(f"Ressource '{ressource}' indexée avec succès !", icon="✅")


app_conf = AppConfig()

pmtd = get_domain_agents(app_conf.domain)
st.title("🩺 Modules d'expertise & Référentiels associés")
st.caption(
    "Conformité aux recommandations : consultez les modules d'analyse spécialisés mobilisés lors de la structuration des dossiers RCP et gérez l'indexation de leurs référentiels cliniques."
)

agent_items = list(pmtd.list.items())
indexed_cache: dict[str, bool] = {}

for row_start in range(0, len(agent_items), 3):
    row_slice = agent_items[row_start : row_start + 3]
    cols = st.columns(3)
    for offset, (n, a) in enumerate(row_slice):
        with cols[offset]:
            with st.container(border=True, height="stretch"):
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
                        or [
                            m.strip()
                            for m in app_conf.llm.models.split(",")
                            if m.strip()
                        ]
                    )
                )
                ressources = getattr(a, "ressources", [])

                ag_icon, ag_label = get_agent_icon_and_label(n)
                st.subheader(f"{ag_icon} {ag_label}")
                st.caption(f"Identifiant technique : `{n}`")
                if models:
                    st.markdown(
                        "**Modèle(s) :** "
                        + " ".join([f":blue-badge[{m}]" for m in models])
                    )

                with st.expander(
                    "⚙️ Instructions système (Prompt)",
                ):
                    st.caption(system_prompt)

                st.markdown("**📚 Référentiels associés :**")
                if not ressources:
                    st.caption("Aucun référentiel externe requis.")
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

                    c1, c2 = st.columns([3, 1.2], vertical_alignment="center")
                    btn_label = f"📄 {r} ✅" if is_idx else f"📄 {r} ⚠️"
                    if c1.button(
                        btn_label,
                        key=f"link_{n}_{r}",
                        width="stretch",
                        help="Consulter ce référentiel clinique",
                    ):
                        st.switch_page(
                            "src/ui/patient_mdt/ressources.py",
                            query_params={"resource": r},
                        )

                    button_label = "🔄 Ré-indexer" if is_idx else "🚀 Indexer"
                    if c2.button(
                        button_label,
                        key=f"{n}_{r}",
                        type="secondary" if is_idx else "primary",
                        width="stretch",
                    ):
                        read(r, app_conf)
                        st.rerun()
