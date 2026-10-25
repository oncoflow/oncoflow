import os
import inspect
from typing import Any
from types import NoneType
from datetime import datetime
from enum import Enum
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from langchain_core.callbacks import BaseCallbackHandler
from pandas import DataFrame
from pydantic import BaseModel
from src.infrastructure.llm.factory import get_llm_client
from src.application.config import AppConfig
from src.application.app_functions import (
    delete_document,
    enqueue_rcp_rerun,
    full_read_mtd_agents,
    get_rcp_active_jobs_state,
)
from src.application.patient import (
    extract_rcp_date,
    resolve_patient_dossier,
    select_latest_analyzed_rcp,
)
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.agents import Agents
from src.domain.patient import Patient
from src.domain.patient_mdt_form import PatientMDTForm
from src.domain.common.common_ressources import PatientPriority
from src.ui.patient_mdt.translations import translate


class ThreadSafeStreamlitCallbackHandler(BaseCallbackHandler):
    def __init__(self, parent_container):
        self.parent_container = parent_container
        self.ctx = get_script_run_ctx()
        self.thinking_container = None
        self.thinking_text = ""
        self.in_think = False
        self.agent_name = "Assistant"

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        try:
            if self.ctx and not get_script_run_ctx():
                add_script_run_ctx(threading.current_thread(), self.ctx)
            # Reset thinking state for each new agent/LLM run to open a new expander
            self.thinking_container = None
            self.thinking_text = ""
            self.in_think = False

            # Extract agent name from tags if present
            tags = kwargs.get("tags", [])
            self.agent_name = tags[0] if tags else "Assistant"
        except Exception as e:
            logger.warning(f"Callback on_llm_start failed: {e}")

    def on_llm_new_token(self, token: str, chunk: Any = None, **kwargs: Any) -> None:
        try:
            if self.ctx and not get_script_run_ctx():
                add_script_run_ctx(threading.current_thread(), self.ctx)

            reasoning_token = None
            if chunk and hasattr(chunk, "message"):
                msg = chunk.message
                reasoning_token = getattr(msg, "reasoning_content", None)
                if not reasoning_token and isinstance(
                    getattr(msg, "additional_kwargs", None), dict
                ):
                    reasoning_token = msg.additional_kwargs.get("reasoning_content")

            is_think_token = False
            clean_token = token

            if reasoning_token:
                is_think_token = True
                clean_token = reasoning_token
            else:
                if "<think>" in token:
                    self.in_think = True
                    clean_token = token.replace("<think>", "")
                    is_think_token = True
                elif "</think>" in token:
                    self.in_think = False
                    clean_token = token.replace("</think>", "")
                    is_think_token = True
                elif self.in_think:
                    is_think_token = True

            if is_think_token:
                # Do not show thinking if it's just general system/Assistant runs without an expert tag
                if getattr(self, "agent_name", "Assistant") == "Assistant":
                    return
                self.thinking_text += clean_token
                if not self.thinking_container:
                    with self.parent_container:
                        self.thinking_container = st.empty()
                with self.thinking_container:
                    agent_display = getattr(self, "agent_name", "Assistant")
                    agent_display = (
                        agent_display[0].upper() + agent_display[1:]
                        if agent_display
                        else "Assistant"
                    )
                    with st.expander(
                        f"💭 Réflexion : {agent_display} / Thinking...", expanded=True
                    ):
                        with st.container(height=250, border=False):
                            st.write(self.thinking_text)
        except Exception as e:
            logger.warning(f"Callback on_llm_new_token failed: {e}")

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        try:
            if self.ctx and not get_script_run_ctx():
                add_script_run_ctx(threading.current_thread(), self.ctx)
            tool_name = serialized.get("name", "tool")
            with self.parent_container:
                st.write(f"🔧 *Appel de l'outil / Tool:* `{tool_name}`")
        except Exception as e:
            logger.warning(f"Callback on_tool_start failed: {e}")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        try:
            if self.ctx and not get_script_run_ctx():
                add_script_run_ctx(threading.current_thread(), self.ctx)
            with self.parent_container:
                st.error(f"❌ *Erreur outil / Tool error:* {error}")
        except Exception as e:
            logger.warning(f"Callback on_tool_error failed: {e}")


app_conf = AppConfig()

db_client = None
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


def trigger_ai(pill_key: str, run_key: str):
    val = st.session_state.get(pill_key)
    if val == ":material/robot: AI exec":
        # Reset pills selection inside the callback (allowed in Streamlit)
        st.session_state[pill_key] = None
        # Set trigger flag
        st.session_state[run_key] = True


def update_date(filename, date):
    if db_client is not None:
        db_client.update_docs(
            "rcp_info", {"file": filename}, {"$set": {"ui_date": date}}
        )


def get_form_models():
    """Récupère dynamiquement les classes de modèles définies dans PatientMDTForm"""
    models = []
    for name, obj in inspect.getmembers(PatientMDTForm):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name != "default_model"
        ):
            models.append(obj)
    return models


def resolve_patient_and_rcps() -> tuple[Patient | None, list[dict], str | None]:
    """
    Résout le dossier patient, la liste chronologique de ses fiches RCP (de la plus récente à la plus ancienne),
    ainsi que le fichier RCP actuellement sélectionné.
    """
    patient_id_param = st.query_params.get("patient_id")
    file_param = st.query_params.get("file")
    return resolve_patient_dossier(
        db_client=db_client,
        patient_id_param=patient_id_param,
        file_param=file_param,
        logger=logger,
    )


def render_field(label, value):
    """Affiche un champ de manière formatée"""

    translated_label = translate(label)

    if isinstance(value, PatientPriority):
        translated_value = translate(value)
        if value.name == "urgent":
            st.error(translated_value, icon="🚨")
        elif value.name == "medium":
            st.warning(translated_value, icon="⚠️")
        elif value.name == "low":
            st.success(translated_value)
    elif isinstance(value, datetime):
        st.markdown(f""" **{translated_label}:** {value.strftime("%d-%m-%Y")}""")
    elif isinstance(value, bool):
        if value:
            st.success(translated_label, icon="✔️")
        else:
            st.error(translated_label, icon="✖️")
    elif isinstance(value, list):
        with st.expander(f"{translated_label}", expanded=False):
            for item in value:
                if isinstance(item, dict):
                    with st.container(border=True):
                        for k, v in item.items():
                            st.markdown(f"**{translate(k)}:** {translate(v)}")
                else:
                    st.markdown(f"- {translate(item)}")
    elif isinstance(value, dict):
        for field_name, field_info in value.items():
            render_field(translate(field_name), field_info)
    elif isinstance(value, Enum):
        render_field(translated_label, translate(value))
    elif isinstance(value, BaseModel):
        render_field(translated_label, value.__dict__)
    elif isinstance(value, int):
        st.markdown(f"**{translated_label}:**  {translate(value)}")
    elif not isinstance(value, NoneType):
        translated_value = translate(value)
        if len(str(translated_value)) > 30:
            st.markdown(
                f"""
            **{translated_label}:**\\
            {translated_value}"""
            )
        else:
            st.markdown(f"**{translated_label}:**  {translated_value}")


def render_fields(data: BaseModel):
    """Affiche les champs d'un modèle"""

    for field_name, field_info in data.__class__.model_fields.items():
        label = field_info.description if field_info.description else field_name

        render_field(translate(label), getattr(data, field_name))


def render_model_data(data: BaseModel):
    """Affiche les données d'un modèle Pydantic dynamiquement"""

    for field_name, field_info in data.__class__.model_fields.items():
        label = field_info.description if field_info.description else field_name
        render_field(translate(label), getattr(data, field_name))


def rerun_all_models(filename: str, section_key: str = "default"):
    models = get_form_models()
    models.sort(key=lambda x: 0 if x.__name__ == "PatientAdministrative" else 1)
    st.session_state["run_full"] = True

    for model_cls in models:
        model_name = model_cls.__name__
        title = model_cls.__doc__.strip() if model_cls.__doc__ else model_name
        st.session_state[f"run_ai_{section_key}_{filename}_{title}"] = True
    st.session_state["run_full"] = None
    st.rerun()


def get_mtd_reader(filename: str | None = None):
    target_file = filename or st.query_params.get("file")
    if (
        "reader" not in st.session_state
        or st.session_state["reader"] is None
        or getattr(st.session_state["reader"], "document", None) != target_file
    ):
        st.session_state["reader"] = PatientMDTForm(app_conf, target_file)
    return st.session_state["reader"]


def render_dossier_header(
    filename: str,
    patient: Patient | None = None,
):
    """Affiche l'en-tête principal du dossier patient avec le bouton Retour."""
    c1, c2 = st.columns([1, 6], vertical_alignment="center")
    if c1.button("◀️ Retour", width="stretch", key="btn_back_dossier"):
        st.query_params.clear()
        st.rerun()

    if patient is not None:
        c2.subheader(f"👤 Dossier Patient : {patient.display_label}")
    else:
        c2.subheader(f"Dossier : {filename}")


def render_patient_identity_banner(
    patient: Patient | None,
    patient_rcps: list[dict],
    latest_file: str,
):
    """Affiche le bandeau d'identité administrative du patient dans l'onglet 'Données patient'."""
    if patient is None:
        return

    with st.container(border=True):
        cols = st.columns([2, 2, 2, 2])
        cols[0].markdown(f"**Nom complet :** {patient.full_name}")
        if patient.born_name:
            cols[0].caption(f"Nom de naissance : {patient.born_name}")

        dob_str = (
            patient.date_birth.strftime("%d/%m/%Y")
            if isinstance(patient.date_birth, datetime)
            else "Non renseignée"
        )
        cols[1].markdown(f"**Date de naissance :** {dob_str}")

        gender_val = (
            patient.gender.value
            if hasattr(patient.gender, "value")
            else str(patient.gender)
        )
        cols[2].markdown(f"**Sexe :** {translate(gender_val)}")
        cols[3].markdown(
            f"**Nombre de RCP :** {len(patient_rcps)}  \n"
            f"**Dernière RCP :** `{latest_file}`"
        )


def render_rcp_timeline_selector(
    filename: str,
    patient: Patient | None = None,
    patient_rcps: list[dict] | None = None,
) -> str:
    """
    Affiche le sélecteur chronologique permettant de remonter dans le temps parmi toutes les fiches RCP du patient.
    Retourne le nom du fichier RCP sélectionné.
    """
    patient_rcps = patient_rcps or []
    file_options = [doc["file"] for doc in patient_rcps if "file" in doc]
    if not file_options:
        return filename

    latest_analyzed = select_latest_analyzed_rcp(patient_rcps)
    latest_file = latest_analyzed.get("file") if latest_analyzed else None

    file_to_label: dict[str, str] = {}
    for idx, doc in enumerate(patient_rcps):
        f_name = doc["file"]
        rcp_dt = extract_rcp_date(doc)
        date_str = rcp_dt.strftime("%d/%m/%Y") if rcp_dt else "Date inconnue"
        prefix = (
            "⭐ Dernière RCP"
            if f_name == latest_file
            else f"RCP #{len(patient_rcps) - idx}"
        )
        file_to_label[f_name] = f"{prefix} — 📅 {date_str} ({f_name})"

    default_file = filename if filename in file_options else file_options[0]

    st.markdown("##### 🕰️ Sélectionner une fiche RCP dans l'historique du patient")
    if len(file_options) <= 4:
        chosen_file = st.segmented_control(
            "Sélectionner une fiche RCP dans l'historique",
            options=file_options,
            default=default_file,
            format_func=lambda f: file_to_label.get(f, f),
            label_visibility="collapsed",
            key=f"rcp_timeline_{patient.patient_id if patient else filename}",
        )
    else:
        chosen_file = st.selectbox(
            "Sélectionner une fiche RCP dans l'historique",
            options=file_options,
            index=file_options.index(default_file),
            format_func=lambda f: file_to_label.get(f, f),
            label_visibility="collapsed",
            key=f"rcp_timeline_select_{patient.patient_id if patient else filename}",
        )

    chosen_file = chosen_file or default_file

    if chosen_file != filename:
        st.query_params["file"] = chosen_file
        if patient is not None:
            st.query_params["patient_id"] = patient.patient_id
        st.rerun()

    return chosen_file


def power_mode(
    element,
    filename: str | None = None,
    key_prefix: str = "default",
    patient_rcps: list[dict] | None = None,
):
    active_file = filename or st.query_params.get("file")
    if "power" in st.session_state:
        if st.session_state["power"]:
            po = element.popover(":repeat: AI process")
            mm = app_conf.llm.models
            mp = app_conf.rcp.doc_type

            rcp_files = [
                d["file"]
                for d in (patient_rcps or [])
                if isinstance(d, dict) and "file" in d
            ]
            if active_file and active_file not in rcp_files:
                rcp_files.insert(0, active_file)

            if len(rcp_files) > 1:
                target_rcp_file = po.selectbox(
                    "Fiche RCP à relancer",
                    options=rcp_files,
                    index=rcp_files.index(active_file)
                    if active_file in rcp_files
                    else 0,
                    key=f"pow_target_file_{key_prefix}_{active_file}",
                )
            else:
                target_rcp_file = active_file
                po.caption(f"📄 Fiche RCP cible : `{target_rcp_file}`")

            nm = po.selectbox(
                "Modèle",
                get_llm_client(app_conf).get_models(),
                placeholder="Select modèle",
                key=f"pow_model_{key_prefix}_{active_file}",
            )
            parser = po.selectbox(
                "Doc parser",
                ["UnstructuredPDFLoader", "openparse", "docling", "ollamaOcr"],
                placeholder="Select parser",
                key=f"pow_parser_{key_prefix}_{active_file}",
            )
            target_active_state = (
                get_rcp_active_jobs_state(app_conf, target_rcp_file)
                if app_conf.queue.enabled
                and app_conf.rcp.display_type == "mongodb"
                and target_rcp_file
                else {"has_any_job": False}
            )
            if po.button(
                "🔄 Relancer cette RCP",
                key=f"pow_rerun_{key_prefix}_{active_file}",
                width="stretch",
                disabled=target_active_state.get("has_any_job", False),
            ):
                if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
                    from src.infrastructure.documents.mongodb import Mongodb

                    client = Mongodb(app_conf)
                    client.delete_document_cache(file_name=target_rcp_file)
                    client.close()
                    res = enqueue_rcp_rerun(app_conf, target_rcp_file, model_name=None)
                    if not res.get("already_queued"):
                        st.toast(
                            "⏳ Fiche ajoutée à la file de traitement",
                            icon="⏳",
                        )
                    else:
                        st.toast(
                            "ℹ️ Cette fiche est déjà dans la file de traitement",
                            icon="ℹ️",
                        )
                else:
                    app_conf.llm.models = nm
                    app_conf.rcp.doc_type = parser
                    with st.status(f"Relance IA sur {target_rcp_file} ..."):
                        from src.infrastructure.documents.mongodb import Mongodb

                        client = Mongodb(app_conf)
                        client.delete_document_cache(file_name=target_rcp_file)
                        client.close()
                        full_read_mtd_agents(
                            app_conf=app_conf,
                            filename=target_rcp_file,
                            logger=logger,
                        )
                        app_conf.llm.models = mm
                        app_conf.rcp.doc_type = mp
                        st.write("Succès")
                st.rerun()
            po.divider()
            po.caption("Gestion du cache (fiche RCP uniquement)")
            if po.button(
                "🗑️ Vider le cache de cette RCP",
                help="Supprimer le cache Markdown de cette fiche RCP uniquement pour forcer une ré-extraction",
                width="stretch",
                key=f"pow_clear_{key_prefix}_{active_file}",
            ):
                from src.infrastructure.documents.mongodb import Mongodb

                client = Mongodb(app_conf)
                client.delete_document_cache(file_name=target_rcp_file)
                client.close()
                st.toast(f"Cache vidé pour {target_rcp_file}", icon="🗑️")
                st.rerun()


def form_rcp_chat(filename: str, section_key: str = "rcp"):
    """
    Onglet Assistant IA rattaché à une fiche RCP unique (opérant exclusivement sur `filename`).
    """
    st.header(f"Poser une question sur la fiche RCP ({filename})")
    st.info(f"📄 **Périmètre : Fiche RCP unique** (`{filename}`)")

    state_prefix = f"rcp_chat_{section_key}_{filename}"
    active_key = f"{state_prefix}_active"
    messages_key = f"{state_prefix}_messages"
    agent_key = f"{state_prefix}_agent"

    if active_key not in st.session_state:
        st.session_state[active_key] = False
    if messages_key not in st.session_state:
        st.session_state[messages_key] = []

    agents = Agents()
    available_agents = agents.list
    agent_choice = st.selectbox(
        "Choisir l'agent",
        list(available_agents.keys()),
        key=f"{state_prefix}_select",
        disabled=st.session_state[active_key],
    )
    if not st.session_state[active_key]:
        if st.button("Démarrer le chat sur cette fiche", key=f"{state_prefix}_start"):
            with st.spinner(f"Démarrage du chat sur la fiche {filename} ..."):
                reader = get_mtd_reader(filename)
                agent_cls = available_agents[agent_choice]
                st.session_state[agent_key] = agent_cls(
                    config=app_conf,
                    mtd=reader,
                )
                st.session_state[active_key] = True
            st.rerun()
    else:
        if st.button("Arrêter le chat", key=f"{state_prefix}_stop"):
            st.session_state[active_key] = False
            if agent_key in st.session_state:
                del st.session_state[agent_key]
            st.session_state[messages_key] = []
            try:
                from src.application.app_functions import unload_active_models

                unload_active_models(app_conf)
            except Exception:
                pass
            st.rerun()

        messages = st.container(height=300)

        for message in st.session_state.get(messages_key, []):
            with messages.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input(
            f"Votre question sur la fiche {filename}",
            key=f"{state_prefix}_input",
        ):
            st.session_state[messages_key].append({"role": "user", "content": prompt})
            with messages.chat_message("user"):
                st.markdown(prompt)

            with messages.chat_message("assistant"):
                with st.spinner("Analyse de la fiche RCP en cours..."):
                    try:
                        resp = st.session_state[agent_key].ask(prompt)
                        st.markdown(resp.response)
                        st.session_state[messages_key].append(
                            {"role": "assistant", "content": resp.response}
                        )
                    except Exception as e:
                        st.error(f"Erreur lors de la génération de la réponse: {e}")


def form_dossier_chat(
    patient: Patient | None = None,
    patient_rcps: list[dict] | None = None,
    current_filename: str | None = None,
):
    """
    Onglet Assistant IA opérant sur l'intégralité du dossier patient
    (toutes les fiches RCP associées au patient ainsi que l'historique des extractions IA).
    """
    st.header("Poser une question sur l'ensemble du dossier patient")

    active_file = current_filename or st.query_params.get("file")
    patient_rcps = patient_rcps or []

    # Liste chronologique (du plus ancien au plus récent) de tous les fichiers RCP du dossier patient
    chronological_files = [d["file"] for d in reversed(patient_rcps) if "file" in d]
    if not chronological_files and active_file:
        chronological_files = [active_file]

    dossier_key = (
        f"patient_{patient.patient_id}"
        if patient is not None
        else f"file_{active_file}"
    )

    st.info(
        f"🗂️ **Périmètre : Dossier patient complet + Historique IA** ({len(chronological_files)} fiche(s) RCP : "
        + ", ".join(f"`{f}`" for f in chronological_files)
        + ")"
    )

    if (
        "chat_file" not in st.session_state
        or st.session_state["chat_file"] != dossier_key
    ):
        st.session_state["chat_file"] = dossier_key
        st.session_state["messages"] = []
        st.session_state["chat_active"] = False

    if "chat_active" not in st.session_state:
        st.session_state["chat_active"] = False

    agents = Agents()
    available_agents = agents.list
    agent_choice = st.selectbox(
        "Choisir l'agent",
        list(available_agents.keys()),
        key="agent_dossier_chat_select",
        disabled=st.session_state["chat_active"],
    )
    if not st.session_state["chat_active"]:
        if st.button("Démarrer le chat sur le dossier", key="btn_start_dossier_chat"):
            with st.spinner("Démarrage du chat sur l'ensemble du dossier patient ..."):
                patient_readers = [
                    PatientMDTForm(app_conf, f) for f in chronological_files
                ]
                agent_cls = available_agents[agent_choice]
                st.session_state["agent"] = agent_cls(
                    config=app_conf,
                    patient_readers=patient_readers,
                )
                st.session_state["chat_active"] = True
            st.rerun()
    else:
        if st.button("Arrêter le chat", key="btn_stop_dossier_chat"):
            st.session_state["chat_active"] = False
            if "agent" in st.session_state:
                del st.session_state["agent"]
            st.session_state["messages"] = []
            try:
                from src.application.app_functions import unload_active_models

                unload_active_models(app_conf)
            except Exception:
                pass
            st.rerun()

        messages = st.container(height=400)

        for message in st.session_state.get("messages", []):
            with messages.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input(
            "Votre question sur le dossier patient", key="dossier_chat_input"
        ):
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with messages.chat_message("user"):
                st.markdown(prompt)

            with messages.chat_message("assistant"):
                with st.spinner("Analyse du dossier patient en cours..."):
                    try:
                        resp = st.session_state["agent"].ask(prompt)
                        st.markdown(resp.response)
                        st.session_state["messages"].append(
                            {"role": "assistant", "content": resp.response}
                        )
                    except Exception as e:
                        st.error(f"Erreur lors de la génération de la réponse: {e}")


def render_rcp_detail_view(
    target_filename: str,
    section_key: str = "default",
    patient_rcps: list[dict] | None = None,
):
    """
    Affiche la vue complète d'une fiche RCP donnée (`target_filename`) :
    - Barre d'actions de la fiche (Relancer cette RCP / Power mode)
    - Colonne gauche : Téléchargement et lecteur PDF
    - Colonne droite : Onglets (Données Cliniques, Assistant IA sur la fiche, Aperçu du document)
    """
    active_state = (
        get_rcp_active_jobs_state(app_conf, target_filename)
        if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb"
        else {
            "has_any_job": False,
            "has_full_job": False,
            "active_models": [],
            "current_step": None,
        }
    )

    if active_state["has_any_job"]:
        b_col1, b_col2 = st.columns([5, 1], vertical_alignment="center")
        step_text = (
            f" ({active_state['current_step']})"
            if active_state.get("current_step")
            else ""
        )
        b_col1.info(
            f"⏳ **Cette fiche est dans la file de traitement{step_text}.** "
            "Les rubriques s'affichent automatiquement au fur et à mesure de leur avancement."
        )
        if b_col2.button(
            "🔄 Actualiser",
            key=f"btn_refresh_detail_{section_key}_{target_filename}",
            width="stretch",
        ):
            st.rerun()

    bar_c1, bar_c2, bar_c3 = st.columns([5, 1, 1], vertical_alignment="center")
    bar_c1.markdown(f"**📄 Fiche RCP active :** `{target_filename}`")
    if bar_c2.button(
        "🔄 Relancer cette RCP",
        help=(
            "Cette fiche est déjà dans la file de traitement"
            if active_state["has_any_job"]
            else f"Ajouter la fiche {target_filename} à la file de traitement"
        ),
        width="stretch",
        key=f"btn_rerun_rcp_{section_key}_{target_filename}",
        disabled=active_state["has_any_job"],
    ):
        if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
            res = enqueue_rcp_rerun(app_conf, target_filename, model_name=None)
            if not res.get("already_queued"):
                st.toast("⏳ Fiche ajoutée à la file de traitement", icon="⏳")
            else:
                st.toast(
                    "ℹ️ Cette fiche est déjà dans la file de traitement",
                    icon="ℹ️",
                )
            st.rerun()
        else:
            rerun_all_models(target_filename, section_key=section_key)
    power_mode(
        bar_c3,
        filename=target_filename,
        key_prefix=f"{section_key}_{target_filename}",
        patient_rcps=patient_rcps,
    )

    col_left, col_right = st.columns([1, 1], gap="medium")

    with col_left:
        file_path = f"{app_conf.rcp.path}/{target_filename}"
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                st.download_button(
                    f"⏬ Télécharger PDF ({target_filename})",
                    f,
                    file_name=target_filename,
                    mime="application/pdf",
                    width="stretch",
                    key=f"dl_pdf_{section_key}_{target_filename}",
                )

            bbox_path = f"{file_path}.bbox"
            viewer_path = bbox_path if os.path.exists(bbox_path) else file_path
            pdf_viewer(
                viewer_path,
                height=800,
                key=f"pdf_viewer_{section_key}_{target_filename}",
            )
        else:
            st.error(f"Fichier introuvable: {file_path}")

    with col_right:
        tab_data, tab_chat, tab_preview = st.tabs(
            [
                "📋 Données Cliniques",
                "💬 Assistant IA sur la fiche",
                "📄 Aperçu du document",
            ]
        )

        with tab_data:
            data = (
                db_client.database["rcp_info"].find_one({"file": target_filename})
                if db_client is not None
                else None
            ) or {}
            execution_times = data.get("execution_times", {})
            models = get_form_models()
            # On met PatientAdministrative en premier si présent
            models.sort(key=lambda x: 0 if x.__name__ == "PatientAdministrative" else 1)

            for model_cls in models:
                model_name = model_cls.__name__
                title = model_cls.__doc__.strip() if model_cls.__doc__ else model_name
                pill_key = f"pills_{section_key}_{target_filename}_{title}"
                run_key = f"run_ai_{section_key}_{target_filename}_{title}"
                is_section_queued = active_state["has_full_job"] or (
                    model_name in active_state["active_models"]
                )
                with st.expander(f"📌 {translate(title)}", expanded=True):
                    st.pills(
                        "Retry ai",
                        label_visibility="collapsed",
                        options=[":material/robot: AI exec"],
                        selection_mode="single",
                        key=pill_key,
                        on_change=trigger_ai,
                        args=(pill_key, run_key),
                        disabled=is_section_queued,
                    )
                    if st.session_state.get(run_key):
                        st.session_state[run_key] = False
                        if (
                            app_conf.queue.enabled
                            and app_conf.rcp.display_type == "mongodb"
                        ):
                            res = enqueue_rcp_rerun(
                                app_conf, target_filename, model_name=model_name
                            )
                            if not res.get("already_queued"):
                                st.toast(
                                    "⏳ Rubrique ajoutée à la file de traitement",
                                    icon="⏳",
                                )
                            else:
                                st.toast(
                                    "ℹ️ Cette rubrique est déjà dans la file de traitement",
                                    icon="ℹ️",
                                )
                            st.rerun()
                        else:
                            try:
                                with st.status(
                                    f"Relance de l'IA pour {model_name} ({target_filename}) ..."
                                ) as status:
                                    st_callback = ThreadSafeStreamlitCallbackHandler(
                                        status
                                    )
                                    reader = get_mtd_reader(target_filename)
                                    reader.read_model(
                                        model_cls, upsert=True, callbacks=[st_callback]
                                    )
                            except Exception as e:
                                logger.error(f"Erreur lors de la relance de l'IA : {e}")
                                st.error(f"Erreur lors de l'exécution de l'IA : {e}")
                            finally:
                                st.rerun()

                    if model_name in data:
                        model_data = data[model_name]

                        # Gestion des agents multiples (dictionnaire de résultats)
                        is_multi = (
                            hasattr(model_cls, "agents")
                            and len(model_cls.agents) > 1
                            and not getattr(model_cls, "collaborative", False)
                        )

                        if is_multi and isinstance(model_data, dict):
                            agent_names = list(model_data.keys())
                            if agent_names:
                                tabs = st.tabs(agent_names)
                                for tab, agent_name in zip(tabs, agent_names):
                                    agent_dict = data[model_name][agent_name]
                                    pydantic_model = model_cls.model_validate(
                                        agent_dict
                                    )
                                    with tab:
                                        render_fields(pydantic_model)
                                        thinking = (
                                            agent_dict.get("reasoning_thinking")
                                            if isinstance(agent_dict, dict)
                                            else None
                                        )
                                        if thinking:
                                            with st.expander(
                                                "💭 Réflexion / Thinking",
                                                expanded=False,
                                            ):
                                                with st.container(
                                                    height=250, border=False
                                                ):
                                                    st.write(thinking)
                        else:
                            pydantic_model = model_cls.model_validate(data[model_name])
                            render_model_data(pydantic_model)
                            thinking = (
                                model_data.get("reasoning_thinking")
                                if isinstance(model_data, dict)
                                else None
                            )
                            if thinking:
                                with st.expander(
                                    "💭 Réflexion / Thinking", expanded=False
                                ):
                                    with st.container(height=250, border=False):
                                        st.write(thinking)

                        exec_time = execution_times.get(model_name)
                        if exec_time is not None:
                            label = (
                                "Execution time"
                                if st.session_state.get("language", "Français")
                                == "English"
                                else "Temps d'exécution"
                            )
                            st.caption(f"⏱️ {label} : {exec_time:.2f} s")
                    else:
                        if is_section_queued or data.get("processing_status") in (
                            "PENDING_CLINICAL",
                            "PROCESSING_CLINICAL",
                            "PENDING_ADMIN",
                            "PROCESSING_ADMIN",
                        ):
                            st.info(
                                "⏳ Rubrique en attente dans la file de traitement..."
                            )
                        else:
                            st.warning("Données non trouvées.")

        with tab_chat:
            form_rcp_chat(target_filename, section_key=section_key)

        with tab_preview:
            tab_chunk, tab_markdown = st.tabs(
                ["📄 Format Chunks", "📄 Format Markdown"]
            )
            with tab_chunk:
                st.header("Aperçu des documents découpés")
                with st.spinner("Chargement de l'aperçu..."):
                    reader = get_mtd_reader(target_filename)
                    chunked_docs = (
                        reader.chunked_documents
                        if hasattr(reader, "chunked_documents")
                        else None
                    )

                    if chunked_docs:
                        st.success(f"{len(chunked_docs)} chunks de document trouvés.")
                        for i, doc in enumerate(chunked_docs):
                            st.subheader(f"Chunk #{i + 1}")
                            st.write(doc.page_content)
                            if doc.metadata:
                                with st.expander(
                                    "Afficher les métadonnées", expanded=False
                                ):
                                    st.json(doc.metadata)
                            st.divider()
                    else:
                        st.warning(
                            "Aucun document découpé. Le découpage se fait lors de l'utilisation de l'IA (via le chat ou l'analyse de données)."
                        )
            with tab_markdown:
                st.header("Aperçu des documents découpés")
                with st.spinner("Chargement de l'aperçu..."):
                    reader = get_mtd_reader(target_filename)
                    markdown = (
                        reader.markdown_exporter[0].page_content
                        if hasattr(reader, "markdown_exporter")
                        and reader.markdown_exporter
                        else None
                    )

                    if markdown:
                        st.markdown(markdown)
                    else:
                        st.warning("Aucun document au format markdown.")


def form():
    patient, patient_rcps, filename = resolve_patient_and_rcps()
    if not filename:
        st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt/cards.py")
        return

    # Maintenir `file` synchronisé dans `st.query_params` pour compatibilité avec les composants existants
    if st.query_params.get("file") != filename:
        st.query_params["file"] = filename

    latest_doc = select_latest_analyzed_rcp(patient_rcps) if patient_rcps else None
    latest_file = (
        latest_doc["file"] if latest_doc and "file" in latest_doc else filename
    )

    render_dossier_header(filename, patient=patient)

    top_tab_patient, top_tab_history, top_tab_dossier_chat = st.tabs(
        [
            "👤 Données patient",
            "🕰️ Historique des fiches RCP",
            "💬 Assistant IA sur le dossier",
        ]
    )

    with top_tab_patient:
        render_patient_identity_banner(
            patient=patient,
            patient_rcps=patient_rcps,
            latest_file=latest_file,
        )
        render_rcp_detail_view(
            latest_file,
            section_key="patient_latest",
            patient_rcps=patient_rcps,
        )

    with top_tab_history:
        selected_history_file = render_rcp_timeline_selector(
            filename,
            patient=patient,
            patient_rcps=patient_rcps,
        )
        render_rcp_detail_view(
            selected_history_file,
            section_key="history",
            patient_rcps=patient_rcps,
        )

    with top_tab_dossier_chat:
        form_dossier_chat(
            patient=patient,
            patient_rcps=patient_rcps,
            current_filename=filename,
        )


power = st.sidebar.toggle("Power mode", key="power")

if st.session_state["power"]:
    st.sidebar.markdown(
        f"""
                        - **Modele:**: {app_conf.llm.models}
                        - **Embed**: {app_conf.llm.embeddings}
                        - **Parser**: {app_conf.rcp.doc_type}
                        """
    )
    st.sidebar.divider()
    st.sidebar.caption("⚡ Cache documents")
    c_btn1, c_btn2 = st.sidebar.columns(2)
    if c_btn1.button(
        "🗑️ Ce doc",
        help="Supprimer le cache du document courant",
        width="stretch",
    ):
        from src.infrastructure.documents.mongodb import Mongodb

        client = Mongodb(app_conf)
        filename = st.query_params.get("file")
        if filename:
            client.delete_document_cache(file_name=filename)
            st.toast(f"Cache vidé pour {filename}", icon="🗑️")
        client.close()
        st.rerun()
    if c_btn2.button(
        "🧹 Tout vider",
        help="Vider tout le cache des documents",
        width="stretch",
    ):
        from src.infrastructure.documents.mongodb import Mongodb

        client = Mongodb(app_conf)
        client.delete_document_cache()
        client.close()
        st.toast("Tout le cache document a été vidé", icon="🧹")
        st.rerun()

if "patient_id" in st.query_params or "file" in st.query_params:
    form()
else:
    st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt/cards.py")

if "reader" in st.session_state:
    del st.session_state["reader"]
    st.session_state["reader"] = None

if db_client is not None:
    db_client.close()
