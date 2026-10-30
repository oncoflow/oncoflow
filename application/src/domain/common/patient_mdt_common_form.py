from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import Enum

import inspect
import json
from typing import Any, ClassVar, Optional, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, PastDatetime, model_validator

from src.application.agent.agent import OncowflowAgent
from src.domain.common.agents import Agents
from src.domain.common.common_ressources import *  # noqa: F403
from src.domain.worker.queue_job import RCPProcessingStatus

PARIS_TZ = ZoneInfo("Europe/Paris")


def _to_naive_paris(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(PARIS_TZ).replace(tzinfo=None)
    return dt


def _serialize_domain_value(val: Any) -> Any:
    if isinstance(val, BaseModel):
        return _serialize_domain_value(val.model_dump())
    if isinstance(val, dict):
        return {
            k: _serialize_domain_value(v)
            for k, v in val.items()
            if k != "reasoning_thinking"
        }
    if isinstance(val, list):
        return [_serialize_domain_value(item) for item in val]
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, Enum):
        return val.value
    return val


class NonPatientMDTFormError(ValueError):
    """Domain exception raised when an imported document is not a valid PatientMDTForm."""

    def __init__(
        self,
        filename: str,
        detected_document_type: str = "Document non-RCP",
        justification: str = "",
    ) -> None:
        self.filename = filename
        self.detected_document_type = detected_document_type or "Document non-RCP"
        self.justification = justification or ""
        details = (
            f" ({self.detected_document_type})" if self.detected_document_type else ""
        )
        reason = f" : {self.justification}" if self.justification else ""
        super().__init__(
            f"Document refusé : '{filename}' n'est pas une fiche RCP{details}{reason}"
        )


class PatientMDTForm:
    """
    Pure Domain Aggregate representing a Multidisciplinary Team meeting form (`PatientMDTForm`).
    Holds clinical/administrative sections, execution metrics, and domain rules (visibility,
    card metrics computation, chronological sorting, and AI history formatting) with zero I/O.
    """

    def __init__(
        self,
        file: str,
        patient_id: str | None = None,
        ui_date: datetime | None = None,
        processing_status: RCPProcessingStatus | str = RCPProcessingStatus.COMPLETED,
        processing_step: str | None = None,
        processing_progress_pct: float = 0.0,
        sections: dict[str, Any] | None = None,
        execution_times: dict[str, float] | None = None,
    ) -> None:
        self.file = file
        self.patient_id = patient_id
        self.ui_date = ui_date
        self.processing_status = (
            processing_status.value
            if isinstance(processing_status, RCPProcessingStatus)
            else str(processing_status or RCPProcessingStatus.COMPLETED.value)
        )
        self.processing_step = processing_step
        self.processing_progress_pct = float(processing_progress_pct or 0.0)
        self.sections: dict[str, Any] = dict(sections) if sections else {}
        self.execution_times: dict[str, float] = (
            dict(execution_times) if execution_times else {}
        )
        self.date_refresh: datetime = datetime.now()

    # ------------------------------------------------------------------
    # Section Schema Introspection
    # ------------------------------------------------------------------

    @classmethod
    def get_section_models(cls) -> list[type[BaseModel]]:
        """
        Return all domain section Pydantic models defined on this `PatientMDTForm` subclass
        (excluding `default_model` and `PatientMDTFormCheck`).
        """
        models = []
        for name, obj in inspect.getmembers(cls):
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModel)
                and name not in ("default_model", "PatientMDTFormCheck")
            ):
                models.append(obj)
        return models

    @classmethod
    def get_clinical_models(cls) -> list[type[BaseModel]]:
        """
        Return all clinical model classes defined on this `PatientMDTForm`
        (excluding `default_model`, `PatientAdministrative`, and `PatientMDTFormCheck`).
        """
        return [
            m for m in cls.get_section_models() if m.__name__ != "PatientAdministrative"
        ]

    @classmethod
    def get_section_model(cls, section_name: str) -> type[BaseModel] | None:
        """Resolve a section model class by exact or case-insensitive name."""
        direct = getattr(cls, section_name, None)
        if inspect.isclass(direct) and issubclass(direct, BaseModel):
            return direct
        target_lower = section_name.strip().lower()
        for name, obj in inspect.getmembers(cls):
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModel)
                and name.lower() == target_lower
            ):
                return obj
        return None

    # ------------------------------------------------------------------
    # Section Hydration & Persistence Mapping
    # ------------------------------------------------------------------

    def set_section(
        self,
        section_name: str,
        value: Any,
        duration: float | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        """Store a validated or serialized section value on the aggregate."""
        self.sections[section_name] = value
        effective_duration = duration if duration is not None else elapsed_seconds
        if effective_duration is not None:
            self.execution_times[section_name] = float(effective_duration)
        self.date_refresh = datetime.now()

    def get_section(self, section_name: str, default: Any = None) -> Any:
        return self.sections.get(section_name, default)

    @classmethod
    def from_persistence(cls, raw_doc: dict[str, Any]) -> Self:
        """Hydrate a `PatientMDTForm` domain aggregate from a persistence dictionary."""
        instance = cls(
            file=raw_doc.get("file", ""),
            patient_id=raw_doc.get("patient_id"),
            ui_date=raw_doc.get("ui_date"),
            processing_status=raw_doc.get(
                "processing_status", RCPProcessingStatus.COMPLETED.value
            ),
            processing_step=raw_doc.get("processing_step"),
            processing_progress_pct=raw_doc.get("processing_progress_pct", 0.0),
            execution_times=raw_doc.get("execution_times") or {},
        )
        instance.hydrate_sections(raw_doc)
        return instance

    def hydrate_sections(
        self,
        raw_doc: dict[str, Any],
        extra_models: Sequence[type[BaseModel]] | None = None,
    ) -> None:
        """Validate and populate `self.sections` from a persistence dictionary."""
        section_models = {m.__name__: m for m in self.get_section_models()}
        for m in getattr(self, "basemodel_list", None) or []:
            if inspect.isclass(m) and issubclass(m, BaseModel):
                section_models[m.__name__] = m
        for m in extra_models or []:
            section_models[m.__name__] = m

        for key, value in raw_doc.items():
            if key not in section_models or value is None:
                continue
            model_cls = section_models[key]
            is_multi_agent = len(getattr(model_cls, "agents", [])) > 1 and not getattr(
                model_cls, "collaborative", False
            )
            if is_multi_agent and isinstance(value, dict):
                validated_by_agent: dict[str, Any] = {}
                for agent_cls in model_cls.agents:
                    if agent_cls.agent_name in value:
                        validated_by_agent[agent_cls.agent_name] = (
                            model_cls.model_validate(value[agent_cls.agent_name])
                        )
                if validated_by_agent:
                    self.sections[key] = validated_by_agent
            else:
                self.sections[key] = model_cls.model_validate(value)

    def to_persistence(self) -> dict[str, Any]:
        """Convert this domain aggregate into a persistence-ready dictionary."""
        payload: dict[str, Any] = {
            "file": self.file,
            "execution_times": dict(self.execution_times),
            "processing_status": self.processing_status,
        }
        if self.patient_id is not None:
            payload["patient_id"] = self.patient_id
        if self.ui_date is not None:
            payload["ui_date"] = self.ui_date
        if self.processing_step is not None:
            payload["processing_step"] = self.processing_step
        if self.processing_progress_pct:
            payload["processing_progress_pct"] = self.processing_progress_pct

        for section_name, section_val in self.sections.items():
            if isinstance(section_val, BaseModel):
                payload[section_name] = section_val.model_dump()
            elif isinstance(section_val, dict):
                payload[section_name] = {
                    k: (v.model_dump() if isinstance(v, BaseModel) else v)
                    for k, v in section_val.items()
                }
            else:
                payload[section_name] = section_val
        return payload

    # ------------------------------------------------------------------
    # Pure Domain Specifications & Policies
    # ------------------------------------------------------------------

    @classmethod
    def _as_dict(cls, doc_or_form: "dict[str, Any] | PatientMDTForm") -> dict[str, Any]:
        if isinstance(doc_or_form, PatientMDTForm):
            return doc_or_form.to_persistence()
        return doc_or_form

    @classmethod
    def is_visible_in_cards(
        cls, doc_or_form: "dict[str, Any] | PatientMDTForm"
    ) -> bool:
        """
        Determine whether a `PatientMDTForm` record is ready to be displayed in dashboard cards.
        """
        d = cls._as_dict(doc_or_form)
        status = d.get("processing_status")
        if status in ("PENDING_ADMIN", "PROCESSING_ADMIN") and not d.get(
            "PatientAdministrative"
        ):
            return False
        return True

    @classmethod
    def extract_mdt_date(
        cls, doc_or_form: "dict[str, Any] | PatientMDTForm"
    ) -> datetime | None:
        """Extract the clinical MDT date (or `ui_date` fallback) from a form or persistence dict."""
        d = cls._as_dict(doc_or_form)
        admin = d.get("PatientAdministrative")
        if isinstance(admin, BaseModel):
            admin = admin.model_dump()
        if isinstance(admin, dict) and admin.get("date_rcp"):
            d_mdt = admin.get("date_rcp")
            if isinstance(d_mdt, str):
                try:
                    d_mdt = datetime.fromisoformat(d_mdt)
                except ValueError:
                    d_mdt = None
            if isinstance(d_mdt, datetime):
                return _to_naive_paris(d_mdt)
        ui_d = d.get("ui_date")
        if isinstance(ui_d, str):
            try:
                ui_d = datetime.fromisoformat(ui_d)
            except ValueError:
                ui_d = None
        if isinstance(ui_d, datetime):
            return _to_naive_paris(ui_d)
        return None

    @classmethod
    def extract_card_metrics(
        cls, doc_or_form: "dict[str, Any] | PatientMDTForm"
    ) -> dict[str, Any]:
        """Extract dashboard card metrics from a `PatientMDTForm` or persistence dictionary."""
        d = cls._as_dict(doc_or_form)
        processing_status = d.get("processing_status") or "COMPLETED"
        is_clinical_pending = processing_status in (
            "PENDING_CLINICAL",
            "PROCESSING_CLINICAL",
        )

        patient_name = "Inconnu"
        if "PatientAdministrative" in d and isinstance(
            d["PatientAdministrative"], dict
        ):
            p = d["PatientAdministrative"]
            first = p.get("first_name", "") or ""
            last = p.get("last_name", "") or ""
            full = f"{first} {last}".strip()
            if full:
                patient_name = full

        date_refresh = d.get(
            "ui_date",
            datetime.now(PARIS_TZ).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        if isinstance(date_refresh, str):
            try:
                date_refresh = datetime.fromisoformat(date_refresh)
            except ValueError:
                date_refresh = datetime.now()
        date_refresh = _to_naive_paris(date_refresh)

        date_mcp = (
            d["PatientAdministrative"].get("date_rcp")
            if "PatientAdministrative" in d
            and isinstance(d["PatientAdministrative"], dict)
            else None
        )
        if isinstance(date_mcp, str):
            try:
                date_mcp = datetime.fromisoformat(date_mcp)
            except ValueError:
                date_mcp = None
        date_mcp = _to_naive_paris(date_mcp)

        relevant_experts = []
        urgency_level = "Indéfini"
        urgency_score = 0

        if "ExpertAnswer" in d and isinstance(d["ExpertAnswer"], dict):
            for agent_name, agent_data in d["ExpertAnswer"].items():
                if isinstance(agent_data, dict):
                    if agent_data.get("expert_relevant"):
                        relevant_experts.append(agent_name)

                    raw_prio = agent_data.get("patient_priority", "")
                    p_prio = str(
                        raw_prio.value if isinstance(raw_prio, Enum) else raw_prio
                    ).lower()
                    for urgency in list(PatientPriority):  # noqa: F405
                        if p_prio == urgency.value.lower():
                            if urgency.name == "urgent":
                                if urgency_score < 2:
                                    urgency_score = 2
                                    urgency_level = "Urgent"
                            elif urgency.name == "medium":
                                if urgency_score < 1:
                                    urgency_score = 1
                                    urgency_level = "Semi-urgent"
                            elif urgency.name == "low":
                                if urgency_score == 0:
                                    urgency_level = "Standard"

        missing_data = []
        if "MTDCompleted" in d and isinstance(d["MTDCompleted"], dict):
            if "mtd_complete" in d["MTDCompleted"]:
                mtd_comp = d["MTDCompleted"].get("mtd_complete")
                if isinstance(mtd_comp, dict):
                    m = mtd_comp.get("what_missing", [])
                    if isinstance(m, list):
                        missing_data.extend(m)
            else:
                for agent_data in d["MTDCompleted"].values():
                    if isinstance(agent_data, dict):
                        mtd_comp = agent_data.get("mtd_complete")
                        if isinstance(mtd_comp, dict):
                            m = mtd_comp.get("what_missing", [])
                            if isinstance(m, list):
                                missing_data.extend(m)
        elif not is_clinical_pending:
            missing_data.extend(["no data"])

        intervention_required = None
        intervention_type = None
        if "isInterventionRequiered" in d and isinstance(
            d["isInterventionRequiered"], dict
        ):
            int_data = d["isInterventionRequiered"]
            if "intervention_required" in int_data:
                intervention_required = int_data.get("intervention_required")
                intervention_type = int_data.get("intervention_type")
            else:
                for agent_data in int_data.values():
                    if (
                        isinstance(agent_data, dict)
                        and "intervention_required" in agent_data
                    ):
                        intervention_required = agent_data.get("intervention_required")
                        intervention_type = agent_data.get("intervention_type")
                        break

        patient_id = d.get("patient_id")
        file_name = d.get("file", "")
        link = (
            f"datas?patient_id={patient_id}&file={file_name}"
            if patient_id
            else f"datas?file={file_name}"
        )

        return {
            "file": file_name,
            "patient_id": patient_id,
            "patient": patient_name,
            "date_refresh": date_refresh,
            "date": date_mcp,
            "experts": relevant_experts,
            "missing": list(set(missing_data)),
            "urgency": urgency_level,
            "urgency_score": urgency_score,
            "link": link,
            "intervention_required": intervention_required,
            "intervention_type": intervention_type,
            "processing_status": processing_status,
            "processing_step": d.get("processing_step"),
            "processing_progress_pct": d.get("processing_progress_pct", 0.0),
        }

    @classmethod
    def select_latest_analyzed(
        cls, mdt_docs: Sequence[dict[str, Any] | "PatientMDTForm"]
    ) -> dict[str, Any] | None:
        """
        Select the latest analyzed `PatientMDTForm` record for a patient.
        Prioritizes records with clinical AI analysis, then administrative AI analysis,
        then sorts by `date_rcp` (or `ui_date` fallback) descending.
        """
        if not mdt_docs:
            return None

        normalized_docs = [cls._as_dict(item) for item in mdt_docs]

        def sort_key(doc: dict[str, Any]):
            has_clinical_ai = int(
                bool(
                    doc.get("ExpertAnswer")
                    or doc.get("MTDCompleted")
                    or doc.get("isInterventionRequiered")
                )
            )
            has_admin_ai = int(bool(doc.get("PatientAdministrative")))
            metrics = cls.extract_card_metrics(doc)
            effective_date = (
                metrics.get("date") or metrics.get("date_refresh") or datetime.min
            )
            refresh_date = metrics.get("date_refresh") or datetime.min
            return (has_clinical_ai, has_admin_ai, effective_date, refresh_date)

        return max(normalized_docs, key=sort_key)

    @classmethod
    def format_ai_history_entries(
        cls, entries: Sequence[tuple[str, dict[str, Any]]]
    ) -> str:
        """
        Format the chronological history of AI-extracted sections across all PatientMDTForm records
        of a patient record (pure domain formatting, zero I/O).
        """
        excluded_top_keys = {
            "_id",
            "id",
            "file",
            "patient_id",
            "ui_date",
            "execution_times",
            "processing_status",
            "processing_step",
            "processing_progress_pct",
            "PatientMDTFormCheck",
        }
        sections_out: list[str] = []

        for doc_name, raw_sections in entries:
            ai_payload = {
                k: _serialize_domain_value(v)
                for k, v in (raw_sections or {}).items()
                if k not in excluded_top_keys and v is not None
            }
            mdt_dt = cls.extract_mdt_date(ai_payload) or cls.extract_mdt_date(
                raw_sections or {}
            )
            date_str = mdt_dt.strftime("%Y-%m-%d") if mdt_dt else "Inconnue"
            if ai_payload:
                body_str = json.dumps(
                    ai_payload, ensure_ascii=False, indent=2, default=str
                )
            else:
                body_str = "Aucune analyse IA enregistrée pour cette fiche RCP."

            sections_out.append(
                f"=== HISTORIQUE IA — FICHE RCP : {doc_name} (Date RCP : {date_str}) ===\n{body_str}"
            )

        return "\n\n".join(sections_out)

    # ------------------------------------------------------------------
    # Base Section Schema & Common Section Models
    # ------------------------------------------------------------------

    class default_model(BaseModel):
        question: ClassVar[str] = ""
        agents: ClassVar[list[type[OncowflowAgent]]] = [Agents.Administratives_agent]
        agents_memory: ClassVar[bool] = False
        collaborative: ClassVar[bool] = False
        collaborative_agent: ClassVar[type[OncowflowAgent] | None] = None
        reasoning_thinking: ClassVar[str | None] = None
        time_execution: ClassVar[int | None] = None

    class PatientMDTFormCheck(default_model):
        """
        Verification that the imported document is a valid PatientMDTForm.
        """

        is_patient_mdt_form: bool = Field(
            description="True if the document is a Multidisciplinary Team (MDT / RCP - Réunion de Concertation Pluridisciplinaire) medical report or form, False otherwise"
        )
        detected_document_type: str = Field(
            default="Inconnu",
            description="Type of document detected in French (e.g. 'Fiche RCP', 'Compte-rendu radiologique', 'Facture', 'Courrier médical', 'Autre document')",
        )
        justification: str = Field(
            default="",
            description="Short explanation in French justifying why this document is or is not an RCP/MDT report",
        )

        question: ClassVar[
            str
        ] = """Analyze the document content using `get_mtd_markdown` and determine whether it is a Multidisciplinary Team meeting form/report (Fiche RCP - Réunion de Concertation Pluridisciplinaire).
            1. Set `is_patient_mdt_form` to true if the document is an RCP / MDT form, report, or patient case presentation for a multidisciplinary meeting.
            2. Set `is_patient_mdt_form` to false if the document is anything else (e.g., an isolated lab test, an invoice, an administrative letter, a scientific article, or an unrelated document).
            3. Provide `detected_document_type` and `justification` in French.
            """

    class PatientAdministrative(default_model):
        """
        Patient administrative informations
        """

        first_name: str = Field(description="First name of the patient")
        last_name: str = Field(description="Last name of the patient")
        born_name: Optional[str] = Field(
            description="Name of the patient at birth", default=None
        )

        age: int = Field(description="Age of the patient")
        date_birth: Optional[PastDatetime] = Field(
            description="Date of birth of the patient (Format: YYYY-MM-DD)"
        )
        date_rcp: Optional[datetime] = Field(
            description="Date of the MTD (Format: YYYY-MM-DD)"
        )
        gender: Gender = Field(description="Gender of the patient")  # noqa: F405

        @model_validator(mode="after")
        def check_dates_coherence(self):
            now = datetime.now()
            if self.date_birth and self.date_birth.year < (now.year - 150):
                self.date_birth = None

            if self.date_rcp and self.date_rcp.year < (now.year - 5):
                self.date_rcp = None

            if self.date_birth and self.date_rcp:
                if self.date_birth.replace(tzinfo=None) > self.date_rcp.replace(
                    tzinfo=None
                ):
                    raise ValueError("Date of birth must be before Date of RCP")
            return self

        question: ClassVar[
            str
        ] = """Search and Extract the patient's administrative details from MTD.
            1. Find the patient's First Name, Last Name, Age AND Date of birth. Note that age is often written as 'XX ans'. If age is missing but Date of birth is present, you can deduce the age based on the Date of RCP.
            2. Find the date of the MTD (RCP).
            3. Find the gender of the patient.
            If a value is not found, set it to null in the JSON.
            You can use tools multiple time for each element.
            Format all dates strictly as YYYY-MM-DD (e.g. 1956-06-04).
            Ensure dates are coherent:
            1. Date of birth must be less than 150 years ago.
            2. Date of RCP must be less than 5 years ago.
            3. Date of birth must be strictly before Date of RCP.
            """

    class MTDCompleted(default_model):
        agents: ClassVar[list[type[OncowflowAgent]]] = Agents().expert_agents
        mtd_complete: MTDComplete = Field(description="Is the MDT file complete?")  # noqa: F405

        collaborative = True

        question: ClassVar[str] = """
            As an expert, determine if the MDT (Multidisciplinary Team) file is complete.
            Are there missing elements required for a treatment decision?
            You can use search_on_ressources tool what type of elements/documents is needed.
            You can use tools multiple times for each element
            """
