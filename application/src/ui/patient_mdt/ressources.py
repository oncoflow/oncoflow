import os
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
from src.application.config import AppConfig
from src.application.ressources import Ressources

# Page configurations
st.title("📚 Ressources de Référence Clinique")
st.markdown(
    "Gérez et consultez les guides de référence scientifiques et cliniques (ex: TNCD) utilisés par les agents IA."
)

app_conf = AppConfig()
ressources_manager = Ressources(app_conf)

# List resources
available_resources = ressources_manager.list_ressources()

if not available_resources:
    st.info("Aucune ressource disponible dans le dossier de configuration.")
else:
    # Handle pre-selected resource from query parameters
    default_index = 0
    query_resource = st.query_params.get("resource")
    if query_resource in available_resources:
        default_index = available_resources.index(str(query_resource))

    # UI Layout: Sidebar for selection and index status, Main area for viewer
    st.sidebar.subheader("🗂️ Sélectionner une ressource")
    selected_resource = st.sidebar.selectbox(
        "Ressource",
        options=available_resources,
        index=default_index,
        label_visibility="collapsed",
    )

    # Keep query parameters in sync
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

    # Check status
    is_indexed = ressources_manager.is_indexed(selected_resource)

    # Sidebar Resource Details & Actions
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Fichier :** `{selected_resource}`")

    if is_indexed:
        st.sidebar.success("✅ Indexé dans la base vectorielle")
    else:
        st.sidebar.warning("⚠️ Non indexé dans la base vectorielle")

    # Indexation button
    btn_label = (
        "Re-indexer dans la base vectorielle"
        if is_indexed
        else "Indexer dans la base vectorielle"
    )
    if st.sidebar.button(btn_label, use_container_width=True, type="primary"):
        with st.spinner(f"Indexation de {selected_resource} en cours..."):
            try:
                ressources_manager.index_ressource(selected_resource)
                st.toast(
                    f"Ressource '{selected_resource}' indexée avec succès !",
                    icon="✅",
                )
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur d'indexation : {e}")

    # Check if chat is active
    chat_active = st.session_state.get("chat_active_res", False)

    # Back button to agents page
    st.sidebar.markdown("---")
    if st.sidebar.button("◀ Retour aux agents", use_container_width=True):
        st.query_params.clear()
        st.switch_page("src/ui/patient_mdt_oncologic/agents.py")

    @st.cache_data
    def get_resource_preview(resource_name: str, doc_type: str):
        """
        Cached function to load and parse the resource document.
        Prevents repeated slow document parsing on tab switches.
        """
        from src.application.reader import DocumentReader

        # Use standard AppConfig to load reader
        config = AppConfig()
        reader = DocumentReader(
            config, document=resource_name, document_type="ressource"
        )
        chunks = reader._load_document(reader.document_path)

        # Extract markdown if generated
        markdown_content = None
        if hasattr(reader, "markdown_exporter") and reader.markdown_exporter:
            markdown_content = reader.markdown_exporter[0].page_content

        serialized_chunks = [
            {"page_content": doc.page_content, "metadata": doc.metadata}
            for doc in chunks
        ]

        return markdown_content, serialized_chunks

    file_path = os.path.join(app_conf.rcp.additional_path, selected_resource)

    if os.path.exists(file_path):
        st.subheader(f"📄 Lecture : {selected_resource}")

        c1, c2 = st.columns([1, 1])
        # Allow downloading
        with open(file_path, "rb") as f:
            c1.download_button(
                "⏬ Télécharger le document",
                f,
                file_name=selected_resource,
                mime="application/pdf",
                use_container_width=True,
            )

        # Chat toggle button next to download
        if is_indexed:
            if not chat_active:
                if c2.button(
                    "💬 Interroger l'Assistant IA",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state["chat_active_res"] = True
                    st.session_state["messages_res"] = []
                    with st.spinner("Initialisation de l'agent IA..."):
                        from src.domain.agents import Agents
                        from src.application.reader import DocumentReader

                        # Initialize the reader for the resource document
                        reader = DocumentReader(
                            app_conf,
                            document=selected_resource,
                            document_type="ressource",
                        )

                        # Retrieve the Resource Agent
                        agents = Agents()
                        agent_cls = agents.list["Ressource Assistant"]

                        # Initialize agent with this reader as mtd (main tool source)
                        st.session_state["agent_res"] = agent_cls(
                            config=app_conf, additionnal_readers=[reader]
                        )
                    st.rerun()
            else:
                if c2.button(
                    "❌ Fermer l'Assistant IA",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state["chat_active_res"] = False
                    if "agent_res" in st.session_state:
                        del st.session_state["agent_res"]
                    if "messages_res" in st.session_state:
                        del st.session_state["messages_res"]
                    try:
                        from src.application.app_functions import unload_active_models

                        unload_active_models(app_conf)
                    except Exception:
                        pass
                    st.rerun()

        st.markdown("---")

        if chat_active:
            col_doc, col_chat = st.columns([3, 2], gap="large")
        else:
            col_doc = st.container()

        with col_doc:
            # Preview tabs
            tab_pdf, tab_markdown, tab_chunks = st.tabs(
                ["📄 Aperçu PDF", "📝 Format Markdown", "🧱 Format Chunks"]
            )

            with tab_pdf:
                if selected_resource.lower().endswith(".pdf"):
                    pdf_viewer(file_path, height=800)
                else:
                    st.info("Aperçu PDF non disponible pour ce type de fichier.")

            with tab_markdown:
                with st.spinner("Génération de l'aperçu markdown..."):
                    try:
                        markdown_content, _ = get_resource_preview(
                            selected_resource, app_conf.rcp.doc_type
                        )
                        if markdown_content:
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
                            st.success(f"{len(chunks)} chunks trouvés.")
                            for i, chunk in enumerate(chunks):
                                st.subheader(f"Chunk #{i + 1}")
                                st.write(chunk["page_content"])
                                if chunk["metadata"]:
                                    with st.expander("Métadonnées", expanded=False):
                                        st.json(chunk["metadata"])
                                st.divider()
                        else:
                            st.warning("Aucun chunk disponible pour cette ressource.")
                    except Exception as e:
                        st.error(f"Erreur lors de la génération des chunks : {e}")

        if chat_active:
            with col_chat:
                st.subheader("💬 Assistant IA (Ressource)")
                st.caption(
                    "L'agent IA (Ressource Assistant) utilise ce document de référence pour répondre à vos questions."
                )

                messages_container = st.container(height=500)

                # Render messages history
                st.session_state["messages_res"].append(
                    {
                        "role": "assistant",
                        "content": "Bonjour ! Je suis là pour répondre à vos questions concernant ce document de référence",
                    }
                )
                for message in st.session_state.get("messages_res", []):
                    with messages_container.chat_message(message["role"]):
                        st.markdown(message["content"])

                # Chat input
                if prompt := st.chat_input("Posez une question sur ce document..."):
                    # Add user message
                    st.session_state["messages_res"].append(
                        {"role": "user", "content": prompt}
                    )
                    with messages_container.chat_message("user"):
                        st.markdown(prompt)

                    # Generate agent response
                    with messages_container.chat_message("assistant"):
                        with st.spinner("Analyse en cours..."):
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
