import os
import inspect
from typing import Any
from types import NoneType
from datetime import date, datetime
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
from src.application.paths import UnsafePathError, is_safe_filename, safe_path
from src.application.reader import DocumentReader
from src.application.use_cases import (
    PatientMDTFormExtractionService,
    PatientRecordService,
)
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.documents.repositories import (
    MongoDocumentCacheRepository,
    MongoPatientMDTFormRepository,
    MongoPatientRepository,
)
from src.domain.agents import Agents
from src.domain.patient import Patient
from src.domain.patient_mdt_form import PatientMDTForm, get_domain_mdt_form_cls
from src.domain.common.common_ressources import (
    ChemotherapyData,
    ExpertSuggestion,
    MTDComplete,
    PatientPriority,
    RadiologicalExamination,
    Reference,
)
from src.ui.patient_mdt.translations import get_agent_icon_and_label, translate


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
            self.thinking_container = None
            self.thinking_text = ""
            self.in_think = False

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
                        f"Réflexion : {agent_display} / Thinking...",
                        expanded=True,
                        icon=":material/psychology:",
                    ):
                        with st.container(
                            height=250,
                            border=False,
                            key="clinical_scroll_thinking",
                        ):
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
                st.caption(f":material/build: Appel de l'outil : `{tool_name}`")
        except Exception as e:
            logger.warning(f"Callback on_tool_start failed: {e}")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        try:
            if self.ctx and not get_script_run_ctx():
                add_script_run_ctx(threading.current_thread(), self.ctx)
            with self.parent_container:
                st.error(f"Erreur outil : {error}", icon=":material/error:")
        except Exception as e:
            logger.warning(f"Callback on_tool_error failed: {e}")


app_conf = AppConfig()

db_client = None
if app_conf.rcp.display_type == "mongodb":
    db_client = Mongodb(app_conf)

PAGES_DIR_SRC = "src/ui"
logger = app_conf.set_logger("ui", default_context={"page": "datas"})


def _get_record_service(conf: AppConfig | None = None) -> PatientRecordService:
    """Instantiate a `PatientRecordService` for the active UI configuration."""
    target_conf = conf or app_conf
    return PatientRecordService.from_config(
        target_conf, db_client=db_client if conf is None else None
    )


def _get_extraction_service(
    conf: AppConfig | None = None,
) -> PatientMDTFormExtractionService:
    """Instantiate a `PatientMDTFormExtractionService` for the active UI configuration."""
    target_conf = conf or app_conf
    shared_db = db_client if conf is None else None
    record_service = _get_record_service(target_conf)
    return PatientMDTFormExtractionService(
        config=target_conf,
        patient_repo=MongoPatientRepository(target_conf, db_client=shared_db),
        mdt_form_repo=MongoPatientMDTFormRepository(target_conf, db_client=shared_db),
        cache_repo=MongoDocumentCacheRepository(target_conf, db_client=shared_db),
        patient_record_service=record_service,
    )


@st.dialog("Êtes-vous sûr ?")
def delete(items: DataFrame):
    st.write(f"Vous êtes sur le point de supprimer {items['file'].to_string()}")
    if st.button("Confirmer", type="primary"):
        record_service = _get_record_service()
        for doc in items["file"].to_list():
            record_service.delete_patient_mdt_form_document(doc)
        st.rerun()


def trigger_ai(pill_key: str, run_key: str):
    val = st.session_state.get(pill_key)
    if val:
        st.session_state[pill_key] = None
        st.session_state[run_key] = True


def update_date(filename, date):
    if db_client is not None:
        mdt_repo = MongoPatientMDTFormRepository(app_conf, db_client=db_client)
        mdt_repo.update_fields(filename, {"ui_date": date})


SECTION_META: dict[str, dict[str, Any]] = {
    # Pole 1 : Aide à la décision & Conformité RCP (Onglet Avis & Décision RCP)
    "isInterventionRequiered": {
        "order": 10,
        "tab": "decision",
        "pole": "🎯 Synthèse & Consensus collégial",
        "icon": "💉",
        "title": "Consensus d'intervention RCP",
        "default_expanded": True,
    },
    "MTDCompleted": {
        "order": 20,
        "tab": "decision",
        "pole": "📋 Conformité & Complétude du dossier",
        "icon": "✅",
        "title": "Contrôle de complétude du dossier",
        "default_expanded": True,
    },
    "ExpertAnswer": {
        "order": 30,
        "tab": "decision",
        "pole": "🩺 Avis & propositions cadrées par spécialité",
        "icon": "🩺",
        "title": "Avis des experts & Référentiels",
        "default_expanded": True,
    },
    # Pole 2 : Caractérisation clinique & biologique (Onglet Dossier clinique)
    "TumorLocation": {
        "order": 40,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🎯",
        "title": "Localisation de la tumeur primitive",
        "default_expanded": True,
    },
    "TumorBiology": {
        "order": 50,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🧬",
        "title": "Biologie tumorale (Statut MSI / MSS)",
        "default_expanded": True,
    },
    "GeneticDiagnosis": {
        "order": 45,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🧬",
        "title": "Diagnostic génétique (SMN1 / SMN2)",
        "default_expanded": True,
    },
    "PatientPerformanceStatus": {
        "order": 60,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🏃",
        "title": "Statut de performance OMS",
        "default_expanded": True,
    },
    "MotorFunctionStatus": {
        "order": 65,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🦿",
        "title": "Classification clinique & scores moteurs",
        "default_expanded": True,
    },
    "RespiratoryFunction": {
        "order": 70,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🫁",
        "title": "Fonction respiratoire & ventilation",
        "default_expanded": True,
    },
    "OrthopedicAndSpineStatus": {
        "order": 75,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🦴",
        "title": "Statut orthopédique & rachidien",
        "default_expanded": True,
    },
    "BulbarAndNutritionalStatus": {
        "order": 80,
        "tab": "clinical",
        "pole": "🩺 Caractérisation clinique & biologique",
        "icon": "🍽️",
        "title": "Statut bulbaire & nutritionnel",
        "default_expanded": True,
    },
    # Pole 3 : Bilan paraclinique & Historique thérapeutique (Onglet Dossier clinique)
    "RadiologicExams": {
        "order": 90,
        "tab": "clinical",
        "pole": "🔬 Bilan paraclinique & Historique thérapeutique",
        "icon": "🔬",
        "title": "Examens radiologiques",
        "default_expanded": True,
    },
    "PreviousCurativeSurgery": {
        "order": 100,
        "tab": "clinical",
        "pole": "🔬 Bilan paraclinique & Historique thérapeutique",
        "icon": "🔪",
        "title": "Chirurgie curative antérieure",
        "default_expanded": False,
    },
    "ChemotherapyTreament": {
        "order": 110,
        "tab": "clinical",
        "pole": "🔬 Bilan paraclinique & Historique thérapeutique",
        "icon": "💊",
        "title": "Traitements par chimiothérapie",
        "default_expanded": True,
    },
    "PlannedCurativeSurgery": {
        "order": 120,
        "tab": "clinical",
        "pole": "🔬 Bilan paraclinique & Historique thérapeutique",
        "icon": "📅",
        "title": "Chirurgie curative prévue",
        "default_expanded": False,
    },
    # Pole 4 : Données administratives (Onglet Dossier clinique)
    "PatientAdministrative": {
        "order": 200,
        "tab": "clinical",
        "pole": "👤 Données administratives extraites",
        "icon": "👤",
        "title": "Informations administratives du patient",
        "default_expanded": False,
    },
}


def get_form_models():
    """Dynamically retrieve the model classes defined in the domain's PatientMDTForm, ordered by clinical logic."""
    models = []
    form_cls = get_domain_mdt_form_cls(app_conf.domain)
    for name, obj in inspect.getmembers(form_cls):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name not in ("default_model", "PatientMDTFormCheck")
        ):
            models.append(obj)
    models.sort(key=lambda m: SECTION_META.get(m.__name__, {}).get("order", 150))
    return models


def _format_date_fr(val: Any) -> str:
    """Format a date, datetime, or ISO date string into DD/MM/YYYY."""
    if isinstance(val, (datetime, date)):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val).strftime("%d/%m/%Y")
        except ValueError:
            return val
    return str(val)


def _render_references_list(refs: list[Any], title_label: str | None = None):
    """Render clinical guideline references (e.g., TNCD) as structured citations."""
    if not refs:
        return
    if title_label:
        st.markdown(f"**📖 {title_label} ({len(refs)}) :**")
    for ref in refs:
        d = (
            ref.model_dump()
            if isinstance(ref, BaseModel)
            else (ref if isinstance(ref, dict) else {})
        )
        if not d:
            continue
        name = d.get("name") or "Référentiel"
        page = d.get("page")
        pos = d.get("position")
        excerpt = d.get("excerpt") or ""
        loc_parts = []
        if page is not None:
            loc_parts.append(f"p. {page}")
        if pos:
            loc_parts.append(str(pos))
        loc_str = f" ({', '.join(loc_parts)})" if loc_parts else ""
        st.markdown(
            f"- 📖 **{name}**{loc_str}" + (f" — *« {excerpt} »*" if excerpt else "")
        )


def _render_radiologic_exam(exam: Any):
    """Render a single RadiologicalExamination item as a structured clinical card."""
    d = (
        exam.model_dump()
        if isinstance(exam, BaseModel)
        else (exam if isinstance(exam, dict) else {})
    )
    exam_type = d.get("exam_type")
    if isinstance(exam_type, Enum):
        exam_type = exam_type.value
    exam_type_str = str(exam_type or "Imagerie")
    type_badge_map = {
        "CT": ":blue-badge[🔬 TDM / Scanner (CT)]",
        "MRI": ":violet-badge[🧲 IRM (MRI)]",
        "PET": ":orange-badge[☢️ TEP-Scan (PET)]",
        "EUS": ":green-badge[📡 Écho-endoscopie (EUS)]",
    }
    badge = type_badge_map.get(exam_type_str, f":blue-badge[🔬 {exam_type_str}]")
    date_str = (
        _format_date_fr(d.get("exam_date"))
        if d.get("exam_date")
        else "Date non précisée"
    )
    name_str = d.get("exam_name") or "Examen d'imagerie"
    result_str = d.get("exam_result")

    with st.container(border=True):
        st.markdown(f"{badge} · 📅 **{date_str}** — **{name_str}**")
        if result_str and result_str != "N/A":
            st.caption(f"**Conclusions :** {result_str}")


def _render_chemotherapy_item(chemo: Any):
    """Render a single ChemotherapyData line as a structured clinical card."""
    d = (
        chemo.model_dump()
        if isinstance(chemo, BaseModel)
        else (chemo if isinstance(chemo, dict) else {})
    )
    name = d.get("chemotherapy_name") or "Protocole non précisé"
    start = (
        _format_date_fr(d.get("chemotherapy_start_date"))
        if d.get("chemotherapy_start_date")
        else None
    )
    end = (
        _format_date_fr(d.get("chemotherapy_end_date"))
        if d.get("chemotherapy_end_date")
        else None
    )
    tol = d.get("chemotherapy_tolerance")
    if isinstance(tol, Enum):
        tol = tol.value
    tol_str = str(tol or "")
    tol_badge = (
        ":green-badge[🟢 Tolérance : Bonne]"
        if tol_str.lower() == "good"
        else ":orange-badge[🟠 Tolérance : Moyenne]"
        if tol_str.lower() == "medium"
        else ":red-badge[🔴 Tolérance : Mauvaise]"
        if tol_str.lower() == "poor"
        else f":gray-badge[Tolérance : {translate(tol_str)}]"
    )
    if start and end:
        period = f"du {start} au {end}"
    elif start:
        period = f"débutée le {start}"
    elif end:
        period = f"terminée le {end}"
    else:
        period = "dates non précisées"

    with st.container(border=True):
        st.markdown(f"💊 **{name}** · 📅 *{period}* · {tol_badge}")


def _render_expert_suggestion(sugg: Any, index: int):
    """Render an ExpertSuggestion with its clinical justification and TNCD references."""
    d = (
        sugg
        if isinstance(sugg, ExpertSuggestion)
        else (ExpertSuggestion.model_validate(sugg) if isinstance(sugg, dict) else None)
    )
    if d is None:
        return
    with st.container(border=True):
        st.markdown(f"💡 **Proposition #{index} :** {d.suggestion}")
        if d.why:
            st.markdown(f"**Justification clinique :** {d.why}")
        if d.references:
            _render_references_list(
                d.references, title_label="Références scientifiques (TNCD)"
            )


def render_expert_answer_model(pydantic_model: BaseModel):
    """Render a single specialist's `ExpertAnswer` cleanly according to relevance."""
    is_relevant = getattr(pydantic_model, "expert_relevant", False)
    why_rel = getattr(pydantic_model, "why_relevant", "")
    priority = getattr(pydantic_model, "patient_priority", None)
    suggestions = getattr(pydantic_model, "suggestions", []) or []
    sources = getattr(pydantic_model, "sources_relevant", []) or []

    if not is_relevant:
        st.markdown(
            ":gray-badge[⚪ Spécialité non directement requise pour ce dossier]"
        )
        if why_rel:
            st.caption(f"**Motif :** {why_rel}")
        return

    prio_badge = ":gray-badge[⚪ Priorité non spécifiée]"
    if isinstance(priority, PatientPriority):
        if priority.name == "urgent":
            prio_badge = f":red-badge[🚨 {translate(priority)}]"
        elif priority.name == "medium":
            prio_badge = f":orange-badge[🟠 {translate(priority)}]"
        elif priority.name == "low":
            prio_badge = f":green-badge[🟢 {translate(priority)}]"

    st.markdown(f":green-badge[✅ Expertise requise] {prio_badge}")
    if why_rel:
        st.markdown(f"**Analyse de l'expert :**\n\n{why_rel}")

    if suggestions:
        st.markdown(
            f"**💡 Propositions thérapeutiques / diagnostiques ({len(suggestions)}) :**"
        )
        for idx, s in enumerate(suggestions, start=1):
            _render_expert_suggestion(s, idx)

    if sources:
        with st.expander(
            f"📖 Sources & Référentiels mobilisés ({len(sources)})", expanded=False
        ):
            _render_references_list(sources)


def render_mtd_completed_model(pydantic_model: BaseModel):
    """Render `MTDCompleted` without redundant nested model labels."""
    mtd_comp: MTDComplete | None = getattr(pydantic_model, "mtd_complete", None)
    if mtd_comp is None:
        render_fields(pydantic_model)
        return

    if mtd_comp.is_mtd_complete and not mtd_comp.what_missing:
        st.markdown(":green-badge[✅ Dossier complet et conforme aux prérequis RCP]")
    else:
        missing_count = len(mtd_comp.what_missing or [])
        st.markdown(
            f":orange-badge[⚠️ Dossier à compléter ({missing_count} élément(s) requis)]"
        )

    if mtd_comp.what_missing:
        st.markdown("**⚠️ Éléments manquants requis avant ou pour la décision :**")
        for item in mtd_comp.what_missing:
            st.markdown(f"- {item}")

    if mtd_comp.reflection:
        st.markdown(f"**Synthèse collégiale :**\n\n{mtd_comp.reflection}")

    if mtd_comp.references:
        with st.expander(
            f"📖 Références des prérequis ({len(mtd_comp.references)})", expanded=False
        ):
            _render_references_list(mtd_comp.references)


def _extract_section_header_summary(model_name: str, model_data: Any) -> str:
    """Return a concise inline summary badge/text for the section expander title."""
    if not isinstance(model_data, dict):
        return ""

    if model_name == "isInterventionRequiered":
        req = model_data.get("intervention_required")
        itype = model_data.get("intervention_type")
        if req is True:
            return f" — 💉 Oui ({itype})" if itype else " — 💉 Oui"
        if req is False:
            return " — Surveillance / Sans geste"
    elif model_name == "MTDCompleted":
        mc = model_data.get("mtd_complete")
        if isinstance(mc, dict):
            missing = mc.get("what_missing") or []
            if missing:
                return f" — ⚠️ {len(missing)} élément(s) à compléter"
            if mc.get("is_mtd_complete") is True:
                return " — ✅ Conforme"
    elif model_name == "ExpertAnswer":
        rel_count = sum(
            1
            for v in model_data.values()
            if isinstance(v, dict) and v.get("expert_relevant") is True
        )
        return f" — {rel_count} spécialité(s) concernée(s)"
    elif model_name == "TumorLocation":
        loc = model_data.get("tumor_location")
        if loc:
            return f" — {translate(loc)}"
    elif model_name == "TumorBiology":
        msi = model_data.get("msi_state")
        if msi is True:
            return " — MSI (Instable)"
        if msi is False:
            return " — MSS (Stable)"
    elif model_name == "PatientPerformanceStatus":
        ps = model_data.get("performance_status")
        if ps is not None:
            return f" — OMS {ps}"
    elif model_name == "RadiologicExams":
        exams = model_data.get("exams_list") or []
        if isinstance(exams, list):
            return f" — {len(exams)} examen(s)"
    elif model_name == "PreviousCurativeSurgery":
        done = model_data.get("previous_curative_surgery")
        dt = model_data.get("previous_curative_surgery_date")
        if done is True:
            return f" — Oui ({_format_date_fr(dt)})" if dt else " — Oui"
        if done is False:
            return " — Non"
    elif model_name == "PlannedCurativeSurgery":
        planned = model_data.get("planned_curative_surgery")
        if planned is True:
            return " — Oui"
        if planned is False:
            return " — Non"
    elif model_name == "ChemotherapyTreament":
        chemo = model_data.get("chemotherapy")
        clist = model_data.get("chemotherapy_list") or []
        if chemo is True:
            return f" — Oui ({len(clist)} ligne(s))" if clist else " — Oui"
        if chemo is False:
            return " — Non"
    elif model_name == "GeneticDiagnosis":
        copies = model_data.get("smn2_copy_count")
        if copies is not None:
            return f" — {copies} copie(s) SMN2"
    elif model_name == "MotorFunctionStatus":
        stype = model_data.get("sma_type")
        if stype:
            return f" — {stype}"
    return ""


def resolve_patient_and_rcps() -> tuple[Patient | None, list[dict], str | None]:
    """
    Resolve the PatientRecord, the chronological list of its PatientMDTForm records (newest first),
    and the currently selected PatientMDTForm file.
    """
    patient_id_param = st.query_params.get("patient_id")
    file_param = st.query_params.get("file")
    record_service = _get_record_service()
    return record_service.resolve_patient_record(
        patient_id_param=patient_id_param,
        file_param=file_param,
    )


def render_field(label, value, field_name: str | None = None):
    """Render a single field with clinical formatting for dates, enums, and domain models."""
    translated_label = translate(label)
    is_en = st.session_state.get("language", "Français") == "English"

    if field_name == "msi_state" and isinstance(value, bool):
        msi_badge = (
            ":orange-badge[🧬 MSI — Instabilité microsatellitaire]"
            if value
            else ":blue-badge[🧬 MSS — Microsatellite stable]"
        )
        st.markdown(f"**{translated_label} :** {msi_badge}")
        return

    if isinstance(value, PatientPriority):
        translated_value = translate(value)
        if value.name == "urgent":
            st.markdown(f"**{translated_label} :** :red-badge[🚨 {translated_value}]")
        elif value.name == "medium":
            st.markdown(
                f"**{translated_label} :** :orange-badge[🟠 {translated_value}]"
            )
        elif value.name == "low":
            st.markdown(f"**{translated_label} :** :green-badge[🟢 {translated_value}]")
        else:
            st.markdown(f"**{translated_label} :** :gray-badge[{translated_value}]")
    elif isinstance(value, (datetime, date)):
        st.markdown(f"**{translated_label} :** 📅 {value.strftime('%d/%m/%Y')}")
    elif isinstance(value, bool):
        yes_label = "Yes" if is_en else "Oui"
        no_label = "No" if is_en else "Non"
        badge = f":blue-badge[✓ {yes_label}]" if value else f":gray-badge[✕ {no_label}]"
        st.markdown(f"**{translated_label} :** {badge}")
    elif isinstance(value, list):
        if not value:
            empty_label = "None" if is_en else "Aucun élément"
            st.markdown(f"**{translated_label} :** :gray-badge[{empty_label}]")
        elif all(isinstance(x, RadiologicalExamination) for x in value):
            for exam in value:
                _render_radiologic_exam(exam)
        elif all(isinstance(x, ChemotherapyData) for x in value):
            for chemo in value:
                _render_chemotherapy_item(chemo)
        elif all(isinstance(x, ExpertSuggestion) for x in value):
            for idx, sugg in enumerate(value, start=1):
                _render_expert_suggestion(sugg, idx)
        elif all(isinstance(x, Reference) for x in value):
            _render_references_list(value, title_label=translated_label)
        else:
            with st.expander(
                f"{translated_label} ({len(value)})",
                expanded=False,
                icon=":material/list:",
            ):
                for item in value:
                    if isinstance(item, BaseModel):
                        with st.container(border=True):
                            render_fields(item)
                    elif isinstance(item, dict):
                        with st.container(border=True):
                            for k, v in item.items():
                                render_field(translate(k), v, field_name=k)
                    else:
                        st.markdown(f"- {translate(item)}")
    elif isinstance(value, dict):
        for k, v in value.items():
            render_field(translate(k), v, field_name=k)
    elif isinstance(value, Enum):
        render_field(translated_label, translate(value), field_name=field_name)
    elif isinstance(value, BaseModel):
        render_fields(value)
    elif isinstance(value, (int, float)):
        st.markdown(f"**{translated_label} :** {translate(value)}")
    elif not isinstance(value, NoneType):
        translated_value = translate(value)
        if len(str(translated_value)) > 60:
            st.markdown(f"**{translated_label} :**\n\n{translated_value}")
        else:
            st.markdown(f"**{translated_label} :** {translated_value}")


def render_fields(data: BaseModel):
    """Render all fields of a Pydantic model."""
    if isinstance(data, BaseModel) and data.__class__.__name__ == "ExpertAnswer":
        render_expert_answer_model(data)
        return
    if isinstance(data, BaseModel) and data.__class__.__name__ == "MTDCompleted":
        render_mtd_completed_model(data)
        return
    for field_name, field_info in data.__class__.model_fields.items():
        label = field_info.description if field_info.description else field_name
        render_field(translate(label), getattr(data, field_name), field_name=field_name)


def render_model_data(data: BaseModel):
    """Dynamically render data from a Pydantic model."""
    render_fields(data)


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
        reader = DocumentReader(app_conf, target_file)
        reader.read_document()
        st.session_state["reader"] = reader
    elif not getattr(st.session_state["reader"], "markdown_exporter", None):
        st.session_state["reader"].read_document()
    return st.session_state["reader"]


def render_unified_patient_banner(
    filename: str,
    patient: Patient | None,
    patient_rcps: list[dict],
    latest_file: str,
    section_key: str = "patient_dossier",
) -> tuple[str, bool, str | None, dict[str, Any]]:
    """
    Render a single, unified hospital-grade Patient & RCP Header Banner combining:
    - Back button + Patient full name & administrative badges (DOB, Gender, Birth name, RCP count)
    - Document actions (Download PDF, Rerun AI analysis, Power mode options)
    - Chronological RCP timeline selector (when multiple RCP forms exist)
    Returns `(selected_file, has_pdf, file_path, active_state)`.
    """
    patient_rcps = patient_rcps or []
    file_options = [doc["file"] for doc in patient_rcps if "file" in doc]
    default_file = (
        filename if (not file_options or filename in file_options) else file_options[0]
    )

    extraction_service = _get_extraction_service()
    active_state = (
        extraction_service.get_active_jobs_state(default_file)
        if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb"
        else {
            "has_any_job": False,
            "has_full_job": False,
            "active_models": [],
            "current_step": None,
        }
    )

    try:
        file_path = safe_path(app_conf.rcp.path, default_file)
    except UnsafePathError:
        file_path = None
    has_pdf = file_path is not None and os.path.exists(file_path)

    with st.container(border=True):
        # Row 1: Back button | Patient identity & badges | Document actions
        is_power = bool(st.session_state.get("power"))
        top_cols = st.columns(
            [1.1, 4.4, 1.4, 1.5, 1.1] if is_power else [1.1, 4.8, 1.5, 1.6],
            vertical_alignment="center",
        )
        with top_cols[0]:
            if st.button(
                "◀️ Dossiers",
                width="stretch",
                key="btn_back_dossier",
                help="Retourner au tableau de bord de préparation RCP",
            ):
                st.query_params.clear()
                st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt/cards.py")

        with top_cols[1]:
            if patient is not None:
                dob_str = (
                    patient.date_birth.strftime("%d/%m/%Y")
                    if isinstance(patient.date_birth, (datetime, date))
                    else "Non renseignée"
                )
                gender_val = (
                    patient.gender.value
                    if hasattr(patient.gender, "value")
                    else str(patient.gender)
                )
                born_part = (
                    f" · *Né(e) {patient.born_name}*" if patient.born_name else ""
                )
                st.markdown(
                    f"### 👤 {patient.full_name}  "
                    f":blue-badge[🎂 {dob_str}] "
                    f":violet-badge[⚧️ {translate(gender_val)}] "
                    f":gray-badge[🗂️ {len(patient_rcps)} RCP]"
                )
                active_doc = next(
                    (d for d in patient_rcps if d.get("file") == default_file), None
                )
                rcp_dt = (
                    PatientMDTForm.extract_mdt_date(active_doc) if active_doc else None
                )
                rcp_dt_str = (
                    rcp_dt.strftime("%d/%m/%Y") if rcp_dt else "Date non renseignée"
                )
                st.caption(
                    f"📄 **Pièce active :** `{default_file}` (Séance du **{rcp_dt_str}**)"
                    f" · Dernière RCP analysée : `{latest_file}`{born_part}"
                )
            else:
                st.markdown(f"### 📄 Dossier : `{default_file}`")

        with top_cols[2]:
            if has_pdf and file_path is not None:
                with open(file_path, "rb") as f:
                    st.download_button(
                        "⏬ Télécharger PDF",
                        f,
                        file_name=default_file,
                        mime="application/pdf",
                        width="stretch",
                        key=f"dl_pdf_{section_key}_{default_file}",
                    )

        with top_cols[3]:
            if st.button(
                "🔄 Relancer l'analyse",
                help=(
                    "Cette fiche est déjà dans la file de traitement"
                    if active_state["has_any_job"]
                    else f"Relancer l'extraction IA complète sur {default_file}"
                ),
                width="stretch",
                key=f"btn_rerun_rcp_{section_key}_{default_file}",
                disabled=active_state["has_any_job"],
            ):
                if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
                    res = extraction_service.enqueue_rerun(
                        default_file, model_name=None
                    )
                    if not res.get("already_queued"):
                        st.toast("Fiche ajoutée à la file de traitement", icon="⏳")
                    else:
                        st.toast(
                            "Cette fiche est déjà dans la file de traitement",
                            icon="ℹ️",
                        )
                    st.rerun()
                else:
                    rerun_all_models(default_file, section_key=section_key)

        if is_power:
            power_mode(
                top_cols[4],
                filename=default_file,
                key_prefix=f"{section_key}_{default_file}",
                patient_rcps=patient_rcps,
            )

        # Row 2 (only if multiple RCP forms exist): Integrated chronological timeline selector + Prev/Next navigation
        if len(file_options) > 1:
            current_idx = (
                file_options.index(default_file) if default_file in file_options else 0
            )
            date_counts: dict[str, int] = {}
            for doc in patient_rcps:
                dt_obj = PatientMDTForm.extract_mdt_date(doc)
                d_s = dt_obj.strftime("%d/%m/%Y") if dt_obj else "Date inconnue"
                date_counts[d_s] = date_counts.get(d_s, 0) + 1

            file_to_label: dict[str, str] = {}
            for idx, doc in enumerate(patient_rcps):
                f_name = doc["file"]
                rcp_dt = PatientMDTForm.extract_mdt_date(doc)
                date_str = rcp_dt.strftime("%d/%m/%Y") if rcp_dt else "Date inconnue"
                proc_status = doc.get("processing_status")
                if proc_status in (
                    "PENDING_ADMIN",
                    "PROCESSING_ADMIN",
                    "PENDING_CLINICAL",
                    "PROCESSING_CLINICAL",
                ):
                    urg_dot = "⏳"
                    status_tag = " · En cours"
                else:
                    doc_metrics = PatientMDTForm.extract_card_metrics(doc)
                    urg_val = doc_metrics.get("urgency", "Indéfini")
                    urg_dot = (
                        "🔴"
                        if urg_val == "Urgent"
                        else "🟠"
                        if urg_val == "Semi-urgent"
                        else "🟢"
                        if urg_val == "Standard"
                        else "⚪"
                    )
                    missing_cnt = len(doc_metrics.get("missing", []))
                    int_req_val = doc_metrics.get("intervention_required")
                    tags = []
                    if int_req_val is True:
                        tags.append("💉")
                    if missing_cnt > 0:
                        tags.append(f"⚠️{missing_cnt}")
                    elif urg_val != "Indéfini":
                        tags.append("✅")
                    status_tag = f" {' '.join(tags)}" if tags else ""

                prefix = (
                    "⭐ Dernière RCP"
                    if f_name == latest_file
                    else f"RCP #{len(patient_rcps) - idx}"
                )
                disambig = f" ({f_name})" if date_counts.get(date_str, 0) > 1 else ""
                file_to_label[f_name] = (
                    f"{urg_dot} {prefix} · {date_str}{status_tag}{disambig}"
                )

            t_col_label, t_col_prev, t_col_sel, t_col_next = st.columns(
                [1.3, 0.75, 4.9, 0.75], vertical_alignment="center"
            )
            t_col_label.caption(
                f"🕒 **Historique ({len(file_options) - current_idx}/{len(file_options)}) :**"
            )

            has_older = current_idx + 1 < len(file_options)
            has_newer = current_idx > 0

            with t_col_prev:
                if st.button(
                    "◀ Préc.",
                    disabled=not has_older,
                    width="stretch",
                    key=f"btn_rcp_older_{section_key}_{default_file}",
                    help="Voir la séance RCP chronologiquement antérieure",
                ):
                    older_file = file_options[current_idx + 1]
                    st.query_params["file"] = older_file
                    if patient is not None:
                        st.query_params["patient_id"] = patient.patient_id
                    st.rerun()

            with t_col_next:
                if st.button(
                    "Suiv. ▶",
                    disabled=not has_newer,
                    width="stretch",
                    key=f"btn_rcp_newer_{section_key}_{default_file}",
                    help="Voir la séance RCP chronologiquement plus récente",
                ):
                    newer_file = file_options[current_idx - 1]
                    st.query_params["file"] = newer_file
                    if patient is not None:
                        st.query_params["patient_id"] = patient.patient_id
                    st.rerun()

            timeline_widget_key = f"rcp_timeline_{patient.patient_id if patient else section_key}_{default_file}"
            with t_col_sel:
                if len(file_options) <= 4:
                    chosen_file = st.segmented_control(
                        "Sélectionner une fiche RCP dans l'historique",
                        options=file_options,
                        default=default_file,
                        format_func=lambda f: file_to_label.get(f, f),
                        label_visibility="collapsed",
                        width="stretch",
                        key=timeline_widget_key,
                    )
                else:
                    chosen_file = st.selectbox(
                        "Sélectionner une fiche RCP dans l'historique",
                        options=file_options,
                        index=current_idx,
                        format_func=lambda f: file_to_label.get(f, f),
                        label_visibility="collapsed",
                        key=timeline_widget_key,
                    )

            chosen_file = chosen_file or default_file
            if chosen_file != filename:
                st.query_params["file"] = chosen_file
                if patient is not None:
                    st.query_params["patient_id"] = patient.patient_id
                st.rerun()
            return chosen_file, has_pdf, file_path, active_state

    return default_file, has_pdf, file_path, active_state


def power_mode(
    element,
    filename: str | None = None,
    key_prefix: str = "default",
    patient_rcps: list[dict] | None = None,
):
    active_file = filename or st.query_params.get("file")
    if st.session_state.get("power"):
        po = element.popover("Options IA", icon=":material/tune:", width="stretch")

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
                index=rcp_files.index(active_file) if active_file in rcp_files else 0,
                key=f"pow_target_file_{key_prefix}_{active_file}",
            )
        else:
            target_rcp_file = active_file
            po.caption(f":material/description: Fiche RCP cible : `{target_rcp_file}`")

        nm = po.selectbox(
            "Modèle LLM",
            get_llm_client(app_conf).get_models(),
            placeholder="Sélectionner un modèle",
            key=f"pow_model_{key_prefix}_{active_file}",
        )
        parser = po.selectbox(
            "Extracteur PDF (Parser)",
            ["UnstructuredPDFLoader", "openparse", "docling", "ollamaOcr"],
            placeholder="Sélectionner un parser",
            key=f"pow_parser_{key_prefix}_{active_file}",
        )
        extraction_service = _get_extraction_service()
        target_active_state = (
            extraction_service.get_active_jobs_state(target_rcp_file)
            if app_conf.queue.enabled
            and app_conf.rcp.display_type == "mongodb"
            and target_rcp_file
            else {"has_any_job": False}
        )
        if po.button(
            "Relancer avec ces paramètres",
            icon=":material/refresh:",
            type="primary",
            key=f"pow_rerun_{key_prefix}_{active_file}",
            width="stretch",
            disabled=target_active_state.get("has_any_job", False),
        ):
            if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
                cache_repo = MongoDocumentCacheRepository(app_conf, db_client=db_client)
                cache_repo.delete_cache(file_name=target_rcp_file)
                res = extraction_service.enqueue_rerun(target_rcp_file, model_name=None)
                if not res.get("already_queued"):
                    st.toast(
                        "Fiche ajoutée à la file de traitement",
                        icon="⏳",
                    )
                else:
                    st.toast(
                        "Cette fiche est déjà dans la file de traitement",
                        icon="ℹ️",
                    )
            else:
                run_conf = app_conf.model_copy(deep=True)
                run_conf.llm.models = nm
                run_conf.rcp.doc_type = parser
                with st.status(f"Relance IA sur {target_rcp_file} ..."):
                    run_cache = MongoDocumentCacheRepository(run_conf)
                    run_cache.delete_cache(file_name=target_rcp_file)
                    run_extraction = _get_extraction_service(run_conf)
                    run_extraction.extract_all_sections(filename=target_rcp_file)
                    st.write("Succès")
            st.rerun()

        po.caption("Gestion du cache (fiche RCP uniquement)")
        if po.button(
            "Vider le cache de cette RCP",
            icon=":material/delete:",
            help="Supprimer le cache Markdown de cette fiche RCP uniquement pour forcer une ré-extraction",
            width="stretch",
            key=f"pow_clear_{key_prefix}_{active_file}",
        ):
            cache_repo = MongoDocumentCacheRepository(app_conf, db_client=db_client)
            cache_repo.delete_cache(file_name=target_rcp_file)
            st.toast(f"Cache vidé pour {target_rcp_file}", icon="🗑️")
            st.rerun()


def form_rcp_chat(filename: str, section_key: str = "rcp"):
    """
    AI Assistant attached to a single PatientMDTForm record (`filename`).
    """
    st.caption(
        f":material/description: **Périmètre : Fiche RCP unique** (`{filename}`)"
    )

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
    c_sel, c_btn = st.columns([3, 2], vertical_alignment="bottom")
    with c_sel:
        agent_choice = st.selectbox(
            "Choisir l'agent spécialiste",
            list(available_agents.keys()),
            format_func=lambda a: (
                f"{get_agent_icon_and_label(a)[0]} {get_agent_icon_and_label(a)[1]}"
            ),
            key=f"{state_prefix}_select",
            disabled=st.session_state[active_key],
        )
    with c_btn:
        if not st.session_state[active_key]:
            if st.button(
                "Démarrer la discussion",
                icon=":material/play_arrow:",
                type="primary",
                width="stretch",
                key=f"{state_prefix}_start",
            ):
                with st.spinner(f"Initialisation de l'agent sur {filename}..."):
                    reader = get_mtd_reader(filename)
                    agent_cls = available_agents[agent_choice]
                    st.session_state[agent_key] = agent_cls(
                        config=app_conf,
                        mtd=reader,
                    )
                    st.session_state[active_key] = True
                st.rerun()
        else:
            if st.button(
                "Terminer la session",
                icon=":material/stop_circle:",
                width="stretch",
                key=f"{state_prefix}_stop",
            ):
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

    if st.session_state[active_key]:
        messages = st.container(height=520, border=True)

        for message in st.session_state.get(messages_key, []):
            with messages.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input(
            f"Posez votre question sur la fiche {filename}...",
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
                        st.error(f"Erreur lors de la génération de la réponse : {e}")


def form_dossier_chat(
    patient: Patient | None = None,
    patient_rcps: list[dict] | None = None,
    current_filename: str | None = None,
):
    """
    AI Assistant operating across the entire patient dossier
    (all PatientMDTForm records associated with the patient as well as the AI extraction history).
    """
    active_file = current_filename or st.query_params.get("file")
    patient_rcps = patient_rcps or []

    chronological_files = [d["file"] for d in reversed(patient_rcps) if "file" in d]
    if not chronological_files and active_file:
        chronological_files = [active_file]

    dossier_key = (
        f"patient_{patient.patient_id}"
        if patient is not None
        else f"file_{active_file}"
    )

    st.caption(
        f":material/folder_shared: **Périmètre : Dossier patient complet + Historique IA** "
        f"({len(chronological_files)} fiche(s) RCP : "
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
    c_sel, c_btn = st.columns([3, 2], vertical_alignment="bottom")
    with c_sel:
        agent_choice = st.selectbox(
            "Choisir l'agent spécialiste",
            list(available_agents.keys()),
            format_func=lambda a: (
                f"{get_agent_icon_and_label(a)[0]} {get_agent_icon_and_label(a)[1]}"
            ),
            key="agent_dossier_chat_select",
            disabled=st.session_state["chat_active"],
        )
    with c_btn:
        if not st.session_state["chat_active"]:
            if st.button(
                "Démarrer la discussion",
                icon=":material/play_arrow:",
                type="primary",
                width="stretch",
                key="btn_start_dossier_chat",
            ):
                with st.spinner("Initialisation de l'agent sur le dossier patient..."):
                    extraction_service = _get_extraction_service()
                    patient_readers = extraction_service.build_patient_readers(
                        chronological_files
                    )
                    agent_cls = available_agents[agent_choice]
                    st.session_state["agent"] = agent_cls(
                        config=app_conf,
                        patient_readers=patient_readers,
                    )
                    st.session_state["chat_active"] = True
                st.rerun()
        else:
            if st.button(
                "Terminer la session",
                icon=":material/stop_circle:",
                width="stretch",
                key="btn_stop_dossier_chat",
            ):
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

    if st.session_state["chat_active"]:
        messages = st.container(height=520, border=True)

        for message in st.session_state.get("messages", []):
            with messages.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input(
            "Posez votre question sur l'ensemble du dossier patient...",
            key="dossier_chat_input",
        ):
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with messages.chat_message("user"):
                st.markdown(prompt)

            with messages.chat_message("assistant"):
                with st.spinner("Analyse longitudinale du dossier en cours..."):
                    try:
                        resp = st.session_state["agent"].ask(prompt)
                        st.markdown(resp.response)
                        st.session_state["messages"].append(
                            {"role": "assistant", "content": resp.response}
                        )
                    except Exception as e:
                        st.error(f"Erreur lors de la génération de la réponse : {e}")


def _compute_longitudinal_deltas(
    current_doc: dict[str, Any], prev_doc: dict[str, Any]
) -> list[str]:
    """Compare the active RCP document against the immediately preceding RCP document and return badge strings."""
    deltas: list[str] = []
    curr_m = PatientMDTForm.extract_card_metrics(current_doc)
    prev_m = PatientMDTForm.extract_card_metrics(prev_doc)

    # 1. Urgency evolution
    c_urg = curr_m.get("urgency", "Indéfini")
    p_urg = prev_m.get("urgency", "Indéfini")
    if c_urg != "Indéfini" and p_urg != "Indéfini" and c_urg != p_urg:
        badge_c = (
            "red"
            if c_urg == "Urgent"
            else "orange"
            if c_urg == "Semi-urgent"
            else "green"
        )
        deltas.append(f":{badge_c}-badge[⚡ Urgence : {p_urg} → {c_urg}]")

    # 2. Intervention consensus evolution
    c_int = curr_m.get("intervention_required")
    p_int = prev_m.get("intervention_required")
    if c_int is not None and p_int is not None and c_int != p_int:
        if c_int is True:
            deltas.append(":red-badge[💉 Décision : Surveillance → Intervention]")
        else:
            deltas.append(":green-badge[✅ Décision : Intervention → Surveillance]")

    # 3. WHO / OMS Performance status evolution
    c_ps = (
        current_doc.get("PatientPerformanceStatus", {}).get("performance_status")
        if isinstance(current_doc.get("PatientPerformanceStatus"), dict)
        else None
    )
    p_ps = (
        prev_doc.get("PatientPerformanceStatus", {}).get("performance_status")
        if isinstance(prev_doc.get("PatientPerformanceStatus"), dict)
        else None
    )
    if isinstance(c_ps, int) and isinstance(p_ps, int):
        if c_ps > p_ps:
            deltas.append(f":orange-badge[🏃 OMS {p_ps} → OMS {c_ps} (↗ dégradation)]")
        elif c_ps < p_ps:
            deltas.append(f":green-badge[🏃 OMS {p_ps} → OMS {c_ps} (↘ amélioration)]")
        else:
            deltas.append(f":gray-badge[🏃 OMS {c_ps} stable]")

    # 4. New imaging exams or chemotherapy lines
    c_rad = (
        len(current_doc.get("RadiologicExams", {}).get("radiological_exams") or [])
        if isinstance(current_doc.get("RadiologicExams"), dict)
        else 0
    )
    p_rad = (
        len(prev_doc.get("RadiologicExams", {}).get("radiological_exams") or [])
        if isinstance(prev_doc.get("RadiologicExams"), dict)
        else 0
    )
    if c_rad > p_rad:
        deltas.append(f":blue-badge[🔬 +{c_rad - p_rad} examen(s) d'imagerie]")

    c_chemo = (
        len(current_doc.get("ChemotherapyTreament", {}).get("chemotherapy_list") or [])
        if isinstance(current_doc.get("ChemotherapyTreament"), dict)
        else 0
    )
    p_chemo = (
        len(prev_doc.get("ChemotherapyTreament", {}).get("chemotherapy_list") or [])
        if isinstance(prev_doc.get("ChemotherapyTreament"), dict)
        else 0
    )
    if c_chemo > p_chemo:
        deltas.append(f":violet-badge[💊 +{c_chemo - p_chemo} ligne(s) de chimio.]")

    # 5. SMA motor scores evolution (HFMSE / CHOP-INTEND / RULM)
    if isinstance(current_doc.get("MotorFunctionStatus"), dict) and isinstance(
        prev_doc.get("MotorFunctionStatus"), dict
    ):
        for field_key, label_short in (
            ("hfmse_score", "HFMSE"),
            ("chop_intend_score", "CHOP-INTEND"),
            ("rulm_score", "RULM"),
        ):
            c_sc = current_doc["MotorFunctionStatus"].get(field_key)
            p_sc = prev_doc["MotorFunctionStatus"].get(field_key)
            if (
                isinstance(c_sc, (int, float))
                and isinstance(p_sc, (int, float))
                and c_sc != p_sc
            ):
                diff = c_sc - p_sc
                sign = "+" if diff > 0 else ""
                b_col = "green" if diff > 0 else "orange"
                deltas.append(
                    f":{b_col}-badge[🦿 {label_short} : {p_sc} → {c_sc} ({sign}{diff})]"
                )

    # 6. Completeness resolution
    c_miss = len(curr_m.get("missing", []))
    p_miss = len(prev_m.get("missing", []))
    if p_miss > 0 and c_miss == 0:
        deltas.append(":green-badge[✅ Pièces manquantes complétées]")
    elif c_miss != p_miss and (c_miss > 0 or p_miss > 0):
        deltas.append(f":gray-badge[📋 Pièces à compléter : {p_miss} → {c_miss}]")

    return deltas


def render_clinical_summary_card(data: dict, patient_rcps: list[dict] | None = None):
    """Render a structured synoptic clinical highlight banner at the top of the clinical data panel."""
    metrics = PatientMDTForm.extract_card_metrics(data)
    urgency = metrics.get("urgency", "Indéfini")
    missing = metrics.get("missing", [])
    int_req = metrics.get("intervention_required")
    int_type = metrics.get("intervention_type")
    experts = metrics.get("experts", [])

    urg_badge = (
        ":red-badge[🚨 Priorité haute]"
        if urgency == "Urgent"
        else ":orange-badge[🟠 Semi-urgent]"
        if urgency == "Semi-urgent"
        else ":green-badge[🟢 Standard]"
        if urgency == "Standard"
        else ":gray-badge[⚪ Non qualifié]"
    )
    comp_badge = (
        f":orange-badge[⚠️ À compléter ({len(missing)})]"
        if missing
        else ":green-badge[✅ Dossier conforme]"
    )
    if int_req is True:
        int_label = f" ({int_type})" if int_type else ""
        int_badge = f":red-badge[💉 Intervention{int_label}]"
    elif int_req is False:
        int_badge = ":gray-badge[Surveillance / Sans geste]"
    else:
        int_badge = ":gray-badge[Intervention non évaluée]"

    experts_badges = " ".join(
        [
            f":violet-badge[{get_agent_icon_and_label(e)[0]} {get_agent_icon_and_label(e)[1]}]"
            for e in experts
        ]
    )

    # Extract synoptic clinical markers (Oncology & SMA) as (label, value) pairs
    marker_pairs: list[tuple[str, str]] = []
    if isinstance(data.get("TumorLocation"), dict):
        loc = data["TumorLocation"].get("tumor_location")
        if loc:
            marker_pairs.append(("🎯 Organe primitif", str(translate(loc))))
    if isinstance(data.get("PatientPerformanceStatus"), dict):
        ps = data["PatientPerformanceStatus"].get("performance_status")
        if ps is not None:
            marker_pairs.append(("🏃 Score OMS", f"OMS {ps}"))
    if isinstance(data.get("TumorBiology"), dict):
        msi = data["TumorBiology"].get("msi_state")
        if msi is True:
            marker_pairs.append(("🧬 Biologie", "MSI (Instable)"))
        elif msi is False:
            marker_pairs.append(("🧬 Biologie", "MSS (Stable)"))
    if isinstance(data.get("PreviousCurativeSurgery"), dict) or isinstance(
        data.get("ChemotherapyTreament"), dict
    ):
        tx_parts = []
        if isinstance(data.get("PreviousCurativeSurgery"), dict):
            prev_s = data["PreviousCurativeSurgery"].get("previous_curative_surgery")
            if prev_s is True:
                tx_parts.append("Chir. réalisée")
            elif prev_s is False:
                tx_parts.append("Sans chir.")
        if isinstance(data.get("ChemotherapyTreament"), dict):
            chemo = data["ChemotherapyTreament"].get("chemotherapy")
            if chemo is True:
                tx_parts.append("Chimio. oui")
            elif chemo is False:
                tx_parts.append("Chimio. non")
        if tx_parts:
            marker_pairs.append(("💊 Antécédents", " · ".join(tx_parts)))

    if isinstance(data.get("MotorFunctionStatus"), dict):
        sma_t = data["MotorFunctionStatus"].get("sma_type")
        if sma_t:
            marker_pairs.append(("🦿 Type SMA", str(sma_t)))
    if isinstance(data.get("GeneticDiagnosis"), dict):
        copies = data["GeneticDiagnosis"].get("smn2_copy_count")
        if copies is not None:
            marker_pairs.append(("🧬 Copies SMN2", f"{copies} copie(s)"))
    if isinstance(data.get("RespiratoryFunction"), dict):
        vent = data["RespiratoryFunction"].get("requires_ventilation_support")
        if vent is not None:
            marker_pairs.append(("🫁 Ventilation", "Requise" if vent else "Aucune"))
    if isinstance(data.get("BulbarAndNutritionalStatus"), dict):
        feed = data["BulbarAndNutritionalStatus"].get("feeding_mode")
        if feed:
            marker_pairs.append(("🍽️ Alimentation", str(translate(feed))))

    # Find immediately preceding RCP if patient has multiple RCPs
    prev_doc: dict[str, Any] | None = None
    cur_file = data.get("file")
    if patient_rcps and len(patient_rcps) > 1 and cur_file:
        for idx, doc in enumerate(patient_rcps):
            if doc.get("file") == cur_file and idx + 1 < len(patient_rcps):
                prev_doc = patient_rcps[idx + 1]
                break

    with st.container(border=True):
        st.markdown(
            f"**🩺 Synthèse synoptique RCP** &nbsp; {urg_badge} {comp_badge} {int_badge}"
            + (f" &nbsp; {experts_badges}" if experts_badges else "")
        )
        if marker_pairs:
            m_cols = st.columns(len(marker_pairs))
            for col, (m_label, m_val) in zip(m_cols, marker_pairs):
                col.caption(f"{m_label}  \n**{m_val}**")
        if prev_doc is not None:
            prev_dt = PatientMDTForm.extract_mdt_date(prev_doc)
            prev_dt_str = (
                prev_dt.strftime("%d/%m/%Y")
                if prev_dt
                else prev_doc.get("file", "séance antérieure")
            )
            deltas = _compute_longitudinal_deltas(data, prev_doc)
            if deltas:
                st.markdown(
                    f":small[**📈 Évolution vs RCP du {prev_dt_str} :**] &nbsp; "
                    + " ".join(deltas)
                )
        if missing:
            st.caption("⚠️ **Pièces / données à compléter :** " + ", ".join(missing))


def _render_form_sections_list(
    models: list[type[BaseModel]],
    data: dict[str, Any],
    execution_times: dict[str, Any],
    active_state: dict[str, Any],
    extraction_service: PatientMDTFormExtractionService,
    target_filename: str,
    section_key: str,
    tab_suffix: str,
) -> None:
    """Render a filtered list of clinical or decision form sections grouped by clinical pole."""
    current_pole: str | None = None
    for model_cls in models:
        model_name = model_cls.__name__
        meta = SECTION_META.get(model_name, {})
        pole_label = meta.get("pole", "📋 Rubriques complémentaires")
        if pole_label != current_pole:
            current_pole = pole_label
            st.markdown(f"##### {current_pole}")

        raw_title = model_cls.__doc__.strip() if model_cls.__doc__ else model_name
        display_title = meta.get("title") or translate(raw_title)
        icon_str = meta.get("icon", "📌")
        run_key = f"run_ai_{section_key}_{tab_suffix}_{target_filename}_{raw_title}"
        is_section_queued = active_state["has_full_job"] or (
            model_name in active_state["active_models"]
        )
        exec_time = execution_times.get(model_name)
        time_badge = (
            f" :small[:gray[· ⏱️ {exec_time:.1f}s]]" if exec_time is not None else ""
        )
        header_summary = (
            _extract_section_header_summary(model_name, data.get(model_name))
            if model_name in data
            else " — ⚠️ Non extrait"
        )
        default_exp = meta.get("default_expanded", True)
        if model_name not in data:
            default_exp = False

        with st.expander(
            f"{icon_str} **{display_title}**{header_summary}{time_badge}",
            expanded=default_exp,
        ):
            if st.session_state.get(run_key):
                st.session_state[run_key] = False
                if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
                    res = extraction_service.enqueue_rerun(
                        target_filename, model_name=model_name
                    )
                    if not res.get("already_queued"):
                        st.toast(
                            "Rubrique ajoutée à la file de traitement",
                            icon="⏳",
                        )
                    else:
                        st.toast(
                            "Cette rubrique est déjà dans la file de traitement",
                            icon="ℹ️",
                        )
                    st.rerun()
                else:
                    try:
                        with st.status(
                            f"Relance de l'IA pour {model_name} ({target_filename}) ..."
                        ) as status:
                            st_callback = ThreadSafeStreamlitCallbackHandler(status)
                            reader = get_mtd_reader(target_filename)
                            form_cls = get_domain_mdt_form_cls(app_conf.domain)
                            form = form_cls(document=target_filename)
                            extraction_service.extract_section(
                                form=form,
                                reader=reader,
                                model_cls=model_cls,
                                upsert=True,
                                callbacks=[st_callback],
                            )
                            data = (
                                db_client.database["rcp_info"].find_one(
                                    {"file": target_filename}
                                )
                                if db_client is not None
                                else form.sections
                            ) or {}
                    except Exception as e:
                        logger.error(f"Erreur lors de la relance de l'IA : {e}")
                        st.error(f"Erreur lors de l'exécution de l'IA : {e}")
                    finally:
                        st.rerun()

            single_thinking: str | None = None
            multi_thinkings: dict[str, str] = {}

            if model_name in data:
                model_data = data[model_name]

                is_multi = (
                    hasattr(model_cls, "agents")
                    and len(model_cls.agents) > 1
                    and not getattr(model_cls, "collaborative", False)
                )

                if is_multi and isinstance(model_data, dict):
                    raw_agents = list(model_data.keys())

                    def _expert_sort_key(
                        ag_name: str,
                    ) -> tuple[int, int, str]:
                        ag_d = model_data.get(ag_name)
                        if not isinstance(ag_d, dict):
                            return (2, 9, ag_name)
                        rel = bool(ag_d.get("expert_relevant"))
                        prio_val = str(ag_d.get("patient_priority") or "").lower()
                        prio_rank = (
                            0
                            if "urgent" in prio_val and "not" not in prio_val
                            else 1
                            if "soon" in prio_val or "medium" in prio_val
                            else 2
                        )
                        return (0 if rel else 1, prio_rank, ag_name)

                    agent_names = sorted(raw_agents, key=_expert_sort_key)
                    if agent_names:
                        tab_labels = []
                        for ag_name in agent_names:
                            ag_icon, ag_label = get_agent_icon_and_label(ag_name)
                            ag_d = model_data.get(ag_name)
                            if isinstance(ag_d, dict) and ag_d.get("expert_relevant"):
                                prio_val = str(
                                    ag_d.get("patient_priority") or ""
                                ).lower()
                                if "urgent" in prio_val and "not" not in prio_val:
                                    tab_labels.append(f"🚨 {ag_icon} {ag_label}")
                                else:
                                    tab_labels.append(f"✅ {ag_icon} {ag_label}")
                            else:
                                tab_labels.append(f"⚪ {ag_icon} {ag_label}")

                        tabs = st.tabs(tab_labels)
                        for tab, agent_name in zip(tabs, agent_names):
                            agent_dict = data[model_name][agent_name]
                            pydantic_model = model_cls.model_validate(agent_dict)
                            if isinstance(agent_dict, dict) and agent_dict.get(
                                "reasoning_thinking"
                            ):
                                multi_thinkings[agent_name] = agent_dict[
                                    "reasoning_thinking"
                                ]
                            with tab:
                                render_fields(pydantic_model)
                else:
                    pydantic_model = model_cls.model_validate(data[model_name])
                    render_model_data(pydantic_model)
                    if isinstance(model_data, dict):
                        single_thinking = model_data.get("reasoning_thinking")
            else:
                if is_section_queued or data.get("processing_status") in (
                    "PENDING_CLINICAL",
                    "PROCESSING_CLINICAL",
                    "PENDING_ADMIN",
                    "PROCESSING_ADMIN",
                ):
                    st.info(
                        "Rubrique en attente dans la file de traitement...",
                        icon=":material/hourglass_top:",
                    )
                else:
                    st.warning(
                        "Données non extraites pour cette rubrique.",
                        icon=":material/warning:",
                    )

            with st.container(
                horizontal=True,
                horizontal_alignment="right",
                vertical_alignment="center",
            ):
                if single_thinking or multi_thinkings:
                    with st.popover(
                        "💭 :small[Réflexion IA]",
                        type="tertiary",
                        help="Afficher le raisonnement détaillé de l'IA pour cette rubrique",
                    ):
                        with st.container(
                            height=280,
                            width=520,
                            border=False,
                            key=f"clinical_scroll_pop_{section_key}_{tab_suffix}_{target_filename}_{model_name}",
                        ):
                            if multi_thinkings:
                                t_tabs = st.tabs(list(multi_thinkings.keys()))
                                for t_tab, (ag_name, ag_think) in zip(
                                    t_tabs, multi_thinkings.items()
                                ):
                                    with t_tab:
                                        st.write(ag_think)
                            elif single_thinking:
                                st.write(single_thinking)

                time_help = (
                    f" (Dernier temps d'analyse : {exec_time:.2f} s)"
                    if exec_time is not None
                    else ""
                )
                if st.button(
                    ":blue[:material/refresh:] :small[Relancer cette rubrique]",
                    type="tertiary",
                    key=f"btn_retry_{section_key}_{tab_suffix}_{target_filename}_{model_name}",
                    disabled=is_section_queued,
                    help=f"Relancer l'extraction IA de cette rubrique uniquement{time_help}",
                ):
                    st.session_state[run_key] = True


def render_rcp_detail_view(
    target_filename: str,
    section_key: str = "default",
    patient_rcps: list[dict] | None = None,
    patient: Patient | None = None,
    has_pdf: bool | None = None,
    file_path: str | None = None,
    active_state: dict[str, Any] | None = None,
):
    """
    Render the complete side-by-side view of a given PatientMDTForm record (`target_filename`):
    - Left column: PDF viewer
    - Right column: Synoptic card pinned at top + 4 Tabs (Clinical Record, MDT Opinions & Decision, AI Assistant, Document Preview)
    """
    extraction_service = _get_extraction_service()
    if active_state is None:
        active_state = (
            extraction_service.get_active_jobs_state(target_filename)
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
            f"**Cette fiche est dans la file de traitement{step_text}.** "
            "Les rubriques s'affichent automatiquement au fur et à mesure de leur avancement.",
            icon=":material/hourglass_top:",
        )
        if b_col2.button(
            "Actualiser",
            icon=":material/refresh:",
            key=f"btn_refresh_detail_{section_key}_{target_filename}",
            width="stretch",
        ):
            st.rerun()

    if file_path is None and has_pdf is None:
        try:
            file_path = safe_path(app_conf.rcp.path, target_filename)
        except UnsafePathError:
            file_path = None
        has_pdf = file_path is not None and os.path.exists(file_path)

    col_left, col_right = st.columns([1, 1], gap="medium")

    with col_left:
        if has_pdf and file_path is not None:
            bbox_path = f"{file_path}.bbox"
            viewer_path = bbox_path if os.path.exists(bbox_path) else file_path
            pdf_viewer(
                viewer_path,
                height=800,
                key=f"pdf_viewer_{section_key}_{target_filename}",
            )
        else:
            st.error(
                f"Fichier PDF introuvable : `{target_filename}`",
                icon=":material/error:",
            )

    with col_right:
        data = (
            db_client.database["rcp_info"].find_one({"file": target_filename})
            if db_client is not None
            else None
        ) or {}
        execution_times = data.get("execution_times", {})
        models = get_form_models()
        clinical_models = [
            m
            for m in models
            if SECTION_META.get(m.__name__, {}).get("tab", "clinical") == "clinical"
        ]
        decision_models = [
            m
            for m in models
            if SECTION_META.get(m.__name__, {}).get("tab", "clinical") == "decision"
        ]

        if data:
            render_clinical_summary_card(data, patient_rcps=patient_rcps)

        tab_clinical, tab_decision, tab_chat, tab_preview = st.tabs(
            [
                "🩺 Dossier clinique",
                "⚖️ Avis & Décision RCP",
                "💬 Assistant IA",
                "📄 Texte & Chunks",
            ]
        )

        with tab_clinical:
            with st.container(
                height=660,
                border=False,
                key=f"clinical_scroll_clin_{section_key}_{target_filename}",
            ):
                _render_form_sections_list(
                    models=clinical_models,
                    data=data,
                    execution_times=execution_times,
                    active_state=active_state,
                    extraction_service=extraction_service,
                    target_filename=target_filename,
                    section_key=section_key,
                    tab_suffix="clin",
                )

        with tab_decision:
            with st.container(
                height=660,
                border=False,
                key=f"clinical_scroll_dec_{section_key}_{target_filename}",
            ):
                _render_form_sections_list(
                    models=decision_models,
                    data=data,
                    execution_times=execution_times,
                    active_state=active_state,
                    extraction_service=extraction_service,
                    target_filename=target_filename,
                    section_key=section_key,
                    tab_suffix="dec",
                )

        with tab_chat:
            chat_scope = st.segmented_control(
                "Portée de l'Assistant IA",
                options=[
                    "Dossier patient complet",
                    "Fiche RCP active uniquement",
                ],
                default="Dossier patient complet",
                width="stretch",
                key=f"chat_scope_{section_key}_{target_filename}",
            )
            if chat_scope == "Fiche RCP active uniquement":
                form_rcp_chat(target_filename, section_key=section_key)
            else:
                form_dossier_chat(
                    patient=patient,
                    patient_rcps=patient_rcps,
                    current_filename=target_filename,
                )

        with tab_preview:
            preview_mode = st.segmented_control(
                "Format d'aperçu",
                options=["Format Markdown", "Découpage vectoriel (Chunks)"],
                default="Format Markdown",
                width="stretch",
                key=f"preview_mode_{section_key}_{target_filename}",
            )
            with st.container(height=700, border=True):
                if preview_mode == "Découpage vectoriel (Chunks)":
                    st.subheader("Aperçu des blocs vectoriels (Chunks)")
                    with st.spinner("Chargement des chunks..."):
                        reader = get_mtd_reader(target_filename)
                        chunked_docs = (
                            reader.chunked_documents
                            if hasattr(reader, "chunked_documents")
                            else None
                        )

                        if chunked_docs:
                            st.success(
                                f"{len(chunked_docs)} chunks de document trouvés.",
                                icon=":material/check_circle:",
                            )
                            for i, doc in enumerate(chunked_docs):
                                st.markdown(f"**Chunk #{i + 1}**")
                                st.write(doc.page_content)
                                if doc.metadata:
                                    with st.expander(
                                        "Afficher les métadonnées", expanded=False
                                    ):
                                        st.json(doc.metadata)
                        else:
                            st.warning(
                                "Aucun document découpé. Le découpage se fait lors de l'utilisation de l'IA."
                            )
                else:
                    st.subheader("Aperçu au format Markdown")
                    with st.spinner("Chargement du Markdown..."):
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
                            st.warning("Aucun contenu au format Markdown.")


def form():
    patient, patient_rcps, filename = resolve_patient_and_rcps()
    if not filename:
        st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt/cards.py")
        return

    if st.query_params.get("file") != filename:
        st.query_params["file"] = filename

    latest_doc = (
        PatientMDTForm.select_latest_analyzed(patient_rcps) if patient_rcps else None
    )
    latest_file = (
        latest_doc["file"] if latest_doc and "file" in latest_doc else filename
    )

    selected_file, has_pdf, file_path, active_state = render_unified_patient_banner(
        filename=filename,
        patient=patient,
        patient_rcps=patient_rcps,
        latest_file=latest_file,
        section_key="patient_dossier",
    )
    render_rcp_detail_view(
        selected_file,
        section_key="patient_dossier",
        patient_rcps=patient_rcps,
        patient=patient,
        has_pdf=has_pdf,
        file_path=file_path,
        active_state=active_state,
    )


power = st.sidebar.toggle("Mode expert (Power mode)", key="power")

if st.session_state.get("power"):
    st.sidebar.caption(
        f"**Modèle :** `{app_conf.llm.models}`  \n"
        f"**Embeddings :** `{app_conf.llm.embeddings}`  \n"
        f"**Parser :** `{app_conf.rcp.doc_type}`"
    )
    st.sidebar.caption(":material/bolt: Cache documents")
    c_btn1, c_btn2 = st.sidebar.columns(2)
    if c_btn1.button(
        "Ce doc",
        icon=":material/delete:",
        help="Supprimer le cache du document courant",
        width="stretch",
    ):
        cache_repo = MongoDocumentCacheRepository(app_conf, db_client=db_client)
        filename = st.query_params.get("file")
        if filename:
            cache_repo.delete_cache(file_name=filename)
            st.toast(f"Cache vidé pour {filename}", icon="🗑️")
        st.rerun()
    if c_btn2.button(
        "Tout vider",
        icon=":material/cleaning_services:",
        help="Vider tout le cache des documents (administrateurs)",
        width="stretch",
        disabled=not st.session_state.get("is_admin", False),
    ):
        cache_repo = MongoDocumentCacheRepository(app_conf, db_client=db_client)
        cache_repo.delete_cache(clear_all=True)
        st.toast("Tout le cache document a été vidé", icon="🧹")
        st.rerun()

# `?file=` is user-controlled: reject anything that is not a plain file name
# (path traversal such as `../../etc/passwd`) before any filesystem access.
_raw_file_param = st.query_params.get("file")
if _raw_file_param is not None and not is_safe_filename(_raw_file_param):
    logger.warning("Rejected unsafe 'file' query parameter")
    del st.query_params["file"]
    st.error("Nom de fichier invalide.")
    st.stop()

if "patient_id" in st.query_params or "file" in st.query_params:
    form()
else:
    st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt/cards.py")

if db_client is not None:
    db_client.close()
