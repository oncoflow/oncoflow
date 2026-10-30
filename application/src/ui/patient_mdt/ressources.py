import os
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
from src.application.config import AppConfig
from src.application.ressources import Ressources

# Page configurations
st.title("📚 Référentiels cliniques & recommandations")
st.caption(
    "Conformité aux recommandations : consultez et indexez les référentiels scientifiques et cliniques (ex. TNCD, PNDS) servant de base au contrôle de complétude et aux propositions cadrées."
)

app_conf = AppConfig()
ressources_manager = Ressources(app_conf)


@st.cache_data(max_entries=3)
def get_resource_preview(resource_name: str, doc_type: str):
    """
    Cached function to load and parse the resource document.
    Prevents repeated slow document parsing on tab switches,
    with max_entries=3 to bound RAM usage.
    """
    from src.application.reader import DocumentReader

    config = AppConfig()
    reader = DocumentReader(config, document=resource_name, document_type="ressource")
    chunks = reader._load_document(reader.document_path)

    markdown_content = None
    if hasattr(reader, "markdown_exporter") and reader.markdown_exporter:
        markdown_content = reader.markdown_exporter[0].page_content

    serialized_chunks = [
        {"page_content": doc.page_content, "metadata": doc.metadata} for doc in chunks
    ]

    return markdown_content, serialized_chunks


available_resources = ressources_manager.list_ressources()

if not available_resources:
    st.info(
        "Aucune ressource disponible dans le dossier de configuration.",
        icon=":material/info:",
    )
else:
    default_index = 0
    query_resource = st.query_params.get("resource")
    if query_resource in available_resources:
        default_index = available_resources.index(str(query_resource))

    with st.container(border=True):
        top_c1, top_c2, top_c3, top_c4 = st.columns(
            [3, 1.5, 1.5, 1.2], vertical_alignment="bottom"
        )
        with top_c1:
            selected_resource = st.selectbox(
                "Sélectionner un référentiel clinique",
                options=available_resources,
                index=default_index,
            )
        st.query_params["resource"] = selected_resource

        # Reset chat if selected resource changes
        if "chat_resource" not in st.session_state:
            st.session_state["chat_resource"] = selected_resource
        elif st.session_state["chat_resource"] != selected_resource:
            st.session_state["chat_resource"] = selected_resource
            st.session_state["chat_active_res"] = False
            if "agent_res" in st.session_state:
                del st.session_state["agent_res"]
            if "messages_res" in st.session_state:
                del st.session_state["messages_res"]

        is_indexed = ressources_manager.is_indexed(selected_resource)

        with top_c2:
            btn_label = "🔄 Ré-indexer (RAG)" if is_indexed else "🚀 Indexer (RAG)"
            if st.button(
                btn_label,
                width="stretch",
                type="secondary" if is_indexed else "primary",
            ):
                with st.spinner(f"Indexation de {selected_resource} en cours..."):
                    try:
                        ressources_manager.index_ressource(selected_resource)
                        st.toast(
                            f"Ressource '{selected_resource}' indexée avec succès !",
                            icon="✅",
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur d'indexation : {e}")

        chat_active = st.session_state.get("chat_active_res", False)

        with top_c3:
            if is_indexed:
                if not chat_active:
                    if st.button(
                        "💬 Interroger l'IA",
                        width="stretch",
                        type="primary",
                    ):
                        st.session_state["chat_active_res"] = True
                        st.session_state["messages_res"] = [
                            {
                                "role": "assistant",
                                "content": (
                                    f"Bonjour ! Je suis prêt à répondre à vos questions concernant "
                                    f"le référentiel **`{selected_resource}`**."
                                ),
                            }
                        ]
                        with st.spinner("Initialisation de l'agent IA..."):
                            from src.domain.agents import get_domain_agents
                            from src.application.reader import DocumentReader

                            reader = DocumentReader(
                                app_conf,
                                document=selected_resource,
                                document_type="ressource",
                            )
                            agents = get_domain_agents(app_conf.domain)
                            agent_cls = agents.list["Ressource Assistant"]
                            st.session_state["agent_res"] = agent_cls(
                                config=app_conf, additionnal_readers=[reader]
                            )
                        st.rerun()
                else:
                    if st.button(
                        "❌ Fermer l'Assistant IA",
                        width="stretch",
                        type="secondary",
                    ):
                        st.session_state["chat_active_res"] = False
                        if "agent_res" in st.session_state:
                            del st.session_state["agent_res"]
                        if "messages_res" in st.session_state:
                            del st.session_state["messages_res"]
                        try:
                            from src.application.app_functions import (
                                unload_active_models,
                            )

                            unload_active_models(app_conf)
                        except Exception:
                            pass
                        st.rerun()
            else:
                st.button(
                    "💬 Interroger l'IA",
                    width="stretch",
                    disabled=True,
                    help="Indexez d'abord ce référentiel pour activer l'Assistant IA.",
                )

        with top_c4:
            if st.button(
                "🩺 Modules d'expertise",
                width="stretch",
            ):
                st.query_params.clear()
                st.switch_page("src/ui/patient_mdt/agents.py")

        status_badge = (
            ":green-badge[✅ Indexé dans la base vectorielle]"
            if is_indexed
            else ":orange-badge[⚠️ Non indexé — indexation requise pour le RAG]"
        )
        file_path = os.path.join(app_conf.rcp.additional_path, selected_resource)
        meta_c1, meta_c2 = st.columns([4, 1], vertical_alignment="center")
        meta_c1.markdown(
            f"📖 **Fichier actif :** `{selected_resource}` · {status_badge}"
        )
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                meta_c2.download_button(
                    "⏬ Télécharger PDF",
                    f,
                    file_name=selected_resource,
                    mime="application/pdf",
                    width="stretch",
                )

    if os.path.exists(file_path):
        if chat_active:
            col_doc, col_chat = st.columns([3, 2], gap="large")
        else:
            col_doc = st.container(key="clinical_scroll_res_doc")

        with col_doc:
            tab_pdf, tab_markdown, tab_chunks = st.tabs(
                [
                    "📄 Aperçu PDF",
                    "📝 Format Markdown",
                    "🧱 Blocs vectoriels (Chunks)",
                ]
            )

            with tab_pdf:
                if selected_resource.lower().endswith(".pdf"):
                    pdf_viewer(file_path, height=800)
                else:
                    st.info("Aperçu PDF non disponible pour ce type de fichier.")

            with tab_markdown:
                with st.spinner("Génération de l'aperçu Markdown..."):
                    try:
                        markdown_content, _ = get_resource_preview(
                            selected_resource, app_conf.rcp.doc_type
                        )
                        if markdown_content:
                            with st.container(height=750, border=True):
                                st.markdown(markdown_content)
                        else:
                            st.warning(
                                "Aucun contenu Markdown disponible pour cette ressource."
                            )
                    except Exception as e:
                        st.error(f"Erreur lors de la génération du Markdown : {e}")

            with tab_chunks:
                with st.spinner("Génération de l'aperçu des chunks..."):
                    try:
                        _, chunks = get_resource_preview(
                            selected_resource, app_conf.rcp.doc_type
                        )
                        if chunks:
                            st.success(
                                f"{len(chunks)} chunks trouvés.",
                                icon=":material/check_circle:",
                            )
                            with st.container(height=700, border=True):
                                for i, chunk in enumerate(chunks):
                                    st.markdown(f"**Chunk #{i + 1}**")
                                    st.write(chunk["page_content"])
                                    if chunk["metadata"]:
                                        with st.expander("Métadonnées", expanded=False):
                                            st.json(chunk["metadata"])
                        else:
                            st.warning("Aucun chunk disponible pour cette ressource.")
                    except Exception as e:
                        st.error(f"Erreur lors de la génération des chunks : {e}")

        if chat_active:
            with col_chat:
                st.subheader(":material/chat: Assistant IA (Référentiel)")
                st.caption(
                    f"Interrogez directement le contenu du référentiel `{selected_resource}`."
                )

                messages_container = st.container(height=620, border=True)

                for message in st.session_state.get("messages_res", []):
                    with messages_container.chat_message(message["role"]):
                        st.markdown(message["content"])

                if prompt := st.chat_input("Posez une question sur ce référentiel..."):
                    st.session_state["messages_res"].append(
                        {"role": "user", "content": prompt}
                    )
                    with messages_container.chat_message("user"):
                        st.markdown(prompt)

                    with messages_container.chat_message("assistant"):
                        with st.spinner("Recherche dans le référentiel en cours..."):
                            try:
                                agent = st.session_state["agent_res"]
                                resp = agent.ask(prompt)
                                st.markdown(resp.response)
                                st.session_state["messages_res"].append(
                                    {"role": "assistant", "content": resp.response}
                                )
                            except Exception as e:
                                st.error(
                                    f"Erreur lors de la génération de la réponse : {e}"
                                )
    else:
        st.error(f"Fichier introuvable sur le disque : {file_path}")
