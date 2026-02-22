import environ
import os
import inspect
from types import NoneType
from datetime import datetime
from enum import Enum
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from pandas import DataFrame
from pydantic import BaseModel

from src.infrastructure.llm.ollama import OllamaConnect

from src.application.config import AppConfig
from src.application.app_functions import delete_document, full_read_mtd_agents
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.agents import Agents
from src.domain.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.domain.common_ressources import PatientPriority


app_conf = environ.to_config(AppConfig)

if app_conf.rcp.display_type == "mongodb":
    db_client = Mongodb(app_conf)

PAGES_DIR_SRC = "src/ui"
logger = app_conf.set_logger("ui", default_context={"page": "datas"})


@st.dialog("Êtes-vous sûr ?")
def delete(items: DataFrame):
    st.write(f"Vous êtes sur le point de supprimer {items['file'].to_string()}")
    if st.button("confirmer"):
        for doc in items["file"].to_list():
            delete_document(app_conf, doc)
        st.rerun()


def update_date(filename, date):
    db_client.update_docs("rcp_info", {"file": filename}, {"$set": {"ui_date": date}})


def get_form_models():
    """Récupère dynamiquement les classes de modèles définies dans PatientMDTOncologicForm"""
    models = []
    for name, obj in inspect.getmembers(PatientMDTOncologicForm):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name != "default_model"
        ):
            models.append(obj)
    return models


def render_field(label, value):
    """Affiche un champ de manière formatée"""

    if isinstance(value, PatientPriority):
        if value.name == "urgent":
            st.error(value.value, icon="🚨")
        elif value.name == "medium":
            st.warning(value.value, icon="⚠️")
        elif value.name == "low":
            st.success(value.value)
    elif isinstance(value, datetime):
        st.markdown(f""" **{label}:** {value.strftime('%d-%m-%Y')}""")
    elif isinstance(value, bool):
        if value:
            st.success(label, icon="✔️")
        else:
            st.error(label, icon="✖️")
    elif isinstance(value, list):
        with st.expander(f"{label}", expanded=False):
            for item in value:
                if isinstance(item, dict):
                    with st.container(border=True):
                        for k, v in item.items():
                            st.markdown(f"**{k}:** {v}")
                else:
                    st.markdown(f"- {item}")
    elif isinstance(value, dict):
        for field_name, field_info in value.items():
            render_field(field_name, field_info)
    elif isinstance(value, Enum):
        render_field(label, value.name)
    elif isinstance(value, BaseModel):
        render_field(label, value.__dict__)
    elif isinstance(value, int):
        st.markdown(f"**{label}:**  {value}")
    elif not isinstance(value, NoneType):
        if len(value) > 30:
            st.markdown(
                f"""
            **{label}:**\\
            {value}"""
            )
        else:
            st.markdown(f"**{label}:**  {value}")


def render_fields(data: BaseModel):
    """Affiche les champs d'un modèle"""
    model_cls: BaseModel
    for field_name, field_info in data.__class__.model_fields.items():
        label = field_info.description if field_info.description else field_name
        render_field(label, getattr(data, field_name))


def render_model_data(data: BaseModel):
    """Affiche les données d'un modèle Pydantic dynamiquement"""
    title = data.__doc__.strip() if data.__doc__ else data.__name__

    for field_name, field_info in data.__class__.model_fields.items():
        label = field_info.description if field_info.description else field_name
        render_field(label, getattr(data, field_name))


def rerun_all_models(filename):
    models = get_form_models()
    models.sort(
        key=lambda x: 0 if x.__name__ == "PatientAdministrative" else 1
    )
    st.session_state["run_full"] = True
    
    for model_cls in models:
        model_name = model_cls.__name__
        title = model_cls.__doc__.strip() if model_cls.__doc__ else model_name
        st.session_state[f"pills_{title}"] = ":material/robot: AI exec"
    st.session_state["run_full"] = None
    st.rerun()

def get_mtd_reader():
    if "reader" not in st.session_state or st.session_state["reader"] is None:
        st.session_state["reader"] = PatientMDTOncologicForm(app_conf, st.query_params["file"])
    return st.session_state["reader"]

def form_navigate(filename):
    # Navigation et Titre
    c1, c2, c3, c4 = st.columns([1, 4, 1, 1], vertical_alignment="center")
    if c1.button("◀️ Retour", width="stretch"):
        st.query_params.clear()
        st.rerun()
    c2.subheader(f"Dossier: {filename}")
    if c3.button("🔄 Rerun All", help="Relancer l'analyse complète", use_container_width=True):
        rerun_all_models(filename)
    power_mode(c4)


def power_mode(element):
    if "power" in st.session_state:
        if st.session_state["power"]:
            po = element.popover(":repeat: AI process")
            mm = app_conf.llm.models
            mp = app_conf.rcp.doc_type
            nm = po.selectbox(
                "Modèle",
                OllamaConnect(app_conf).get_models(),
                placeholder="Select modèle",
            )
            parser = po.selectbox(
                "Doc parser",
                ["UnstructuredPDFLoader", "openparse", "docling", "ollamaOcr"],
                placeholder="Select parser",
            )
            if po.button("Rerun"):
                app_conf.llm.models = nm
                app_conf.rcp.doc_type = parser
                with st.status("Rerun AI ..."):
                    full_read_mtd_agents(
                        app_conf=app_conf,
                        filename=st.query_params["file"],
                        logger=logger,
                    )
                    app_conf.llm.models = mm
                    app_conf.rcp.doc_type = mp
                    st.write("Succès")
                st.rerun()


def form_chat():
    reader: PatientMDTOncologicForm = None
    st.header("Poser une question")

    if (
        "chat_file" not in st.session_state
        or st.session_state["chat_file"] != st.query_params["file"]
    ):
        st.session_state["chat_file"] = st.query_params["file"]
        st.session_state["messages"] = []
        st.session_state["chat_active"] = False

    if "chat_active" not in st.session_state:
        st.session_state["chat_active"] = False

    agents = Agents()
    available_agents = agents.list
    if "run_button" in st.session_state and st.session_state.run_button == True:
        st.session_state.running = True
    else:
        st.session_state.running = False
    agent_choice = st.selectbox(
        "Choisir l'agent",
        list(available_agents.keys()),
        key="agent_chat_select",
        disabled=st.session_state["chat_active"],
    )
    if not st.session_state["chat_active"]:
        if st.button(
            "Démarrer le chat avec l'agent",
            disabled=st.session_state.running,
            key="run_button",
        ):
            st.session_state["chat_active"] = True
            with st.spinner("Démarrage du chat ..."):
                reader = get_mtd_reader()
                agent_cls = available_agents[agent_choice]
                st.session_state["agent"] = agent_cls(config=app_conf, mtd=reader)
            st.rerun()
    else:
        if st.button("Arrêter le chat"):
            st.session_state["chat_active"] = False
            if st.session_state["agent"] is not None:
                del st.session_state["agent"]
            del st.session_state["messages"]
            st.rerun()

        messages = st.container(height=300)

        for message in st.session_state["messages"]:
            with messages.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("Votre question"):
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with messages.chat_message("user"):
                st.markdown(prompt)

            with messages.chat_message("assistant"):
                with st.spinner("Analyse en cours..."):
                    try:
                        resp: ChatResponse = st.session_state["agent"].ask(prompt)
                        st.markdown(resp.response)
                        st.session_state["messages"].append(
                            {"role": "assistant", "content": resp.response}
                        )
                    except Exception as e:
                        st.error(f"Erreur lors de la génération de la réponse: {e}")


def form():
    filename = st.query_params["file"]
    form_navigate(filename)
    col_left, col_right = st.columns([1, 1], gap="medium")

    with col_left:
        file_path = f"{app_conf.rcp.path}/{filename}"
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                st.download_button(
                    "⏬ Télécharger PDF",
                    f,
                    file_name=filename,
                    mime="application/pdf",
                    width="stretch",
                )

            bbox_path = f"{file_path}.bbox"
            viewer_path = bbox_path if os.path.exists(bbox_path) else file_path
            pdf_viewer(viewer_path, height=800)
        else:
            st.error(f"Fichier introuvable: {file_path}")

    with col_right:

        tab_data, tab_chat, tab_preview = st.tabs(["📋 Données Cliniques", "💬 Assistant IA", "📄 Aperçu du document"])

        with tab_data:
            data = db_client.database["rcp_info"].find_one({"file": filename})
            if data:
                models = get_form_models()
                # On met PatientAdministrative en premier si présent
                models.sort(
                    key=lambda x: 0 if x.__name__ == "PatientAdministrative" else 1
                )

                for model_cls in models:
                    model_name = model_cls.__name__
                    title = (
                        model_cls.__doc__.strip() if model_cls.__doc__ else model_name
                    )
                    with st.expander(f"📌 {title}", expanded=True):
                        if (
                            f"pills_{title}_ai" in st.session_state
                            and st.session_state[f"pills_{title}_ai"]
                        ):
                            st.session_state[f"pills_{title}"] = None
                            st.session_state[f"pills_{title}_ai"] = None
                        selection = st.pills(
                            "Retry ai",
                            label_visibility="collapsed",
                            options=[":material/robot: AI exec"],
                            selection_mode="single",
                            key=f"pills_{title}",
                        )
                        if selection == ":material/robot: AI exec":
                            with st.status(f"Relance de l'IA pour {model_name} ..."):
                                reader = get_mtd_reader()
                                reader.read_model(model_cls, upsert=True)
                                st.session_state[f"pills_{title}_ai"] = True
                            st.rerun()
                        
                        if model_name in data:
                            model_data = data[model_name]

                            # Gestion des agents multiples (dictionnaire de résultats)
                            is_multi = (
                                hasattr(model_cls, "agents")
                                and len(model_cls.agents) > 1
                            )

                            if is_multi and isinstance(model_data, dict):

                                agent_names = list(model_data.keys())
                                if agent_names:
                                    tabs = st.tabs(agent_names)
                                    for tab, agent_name in zip(tabs, agent_names):
                                        pydantic_model = model_cls.model_validate(
                                            data[model_name][agent_name]
                                        )
                                        with tab:
                                            render_fields(pydantic_model)
                            else:
                                pydantic_model = model_cls.model_validate(
                                    data[model_name]
                                )
                                render_model_data(pydantic_model)
                        else:
                            st.warning("Données non trouvées.")

            else:
                st.warning("Données non trouvées.")

        with tab_chat:
            form_chat()

        with tab_preview:
            tab_chunk, tab_markdown = st.tabs(["📄 Format Chunks", "📄 Format Markdown"])
            with tab_chunk:
                st.header("Aperçu des documents découpés")
                with st.spinner("Chargement de l'aperçu..."):
                    reader = get_mtd_reader()
                    chunked_docs = (
                        reader.chunked_documents
                        if hasattr(reader, "chunked_documents")
                        else None
                    )

                    if chunked_docs:
                        st.success(f"{len(chunked_docs)} chunks de document trouvés.")
                        for i, doc in enumerate(chunked_docs):
                            st.subheader(f"Chunk #{i+1}")
                            st.write(doc.page_content)
                            if doc.metadata:
                                with st.expander("Afficher les métadonnées", expanded=False):
                                    st.json(doc.metadata)
                            st.divider()
                    else:
                        st.warning(
                            "Aucun document découpé. Le découpage se fait lors de l'utilisation de l'IA (via le chat ou l'analyse de données)."
                        )
                with tab_markdown:
                    st.header("Aperçu des documents découpés")
                    with st.spinner("Chargement de l'aperçu..."):
                        reader = get_mtd_reader()
                        markdown = (
                            reader.markdown_exporter[0].page_content
                            if hasattr(reader, "markdown_exporter")
                            else None
                        )

                        if markdown:
                            st.markdown(markdown)
                        else:
                            st.warning(
                                "Aucun document au format markdown."
                            )


power = st.sidebar.toggle("Power mode", key="power")

if st.session_state["power"] == True:
    st.sidebar.markdown(
        f"""
                        - **Modele:**: {app_conf.llm.models}
                        - **Embed**: {app_conf.llm.embeddings}
                        - **Parser**: {app_conf.rcp.doc_type}
                        """
    )


if "file" in st.query_params:
    form()
else:
    st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt_oncologic/cards.py")

if "reader" in st.session_state:
    del(st.session_state["reader"])
    st.session_state["reader"] = None

db_client.close()
