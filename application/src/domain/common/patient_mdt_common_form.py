from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from enum import Enum

import inspect
import json
from typing import Any, ClassVar, Optional, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, PastDatetime, ValidationError, model_validator

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
            str(k): _serialize_domain_value(v)
            for k, v in val.items()
            if k != "reasoning_thinking"
        }
    if isinstance(val, (list, tuple, set)):
        return [_serialize_domain_value(item) for item in val]
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, Enum):
        return val.value
    return val


def _serialize_persistence_value(val: Any) -> Any:
    """Recursively convert domain section values into BSON-compatible primitives."""
    if isinstance(val, BaseModel):
        return _serialize_persistence_value(val.model_dump())
    if isinstance(val, dict):
        return {str(k): _serialize_persistence_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [_serialize_persistence_value(item) for item in val]
    if isinstance(val, datetime):
        return _to_naive_paris(val)
    if isinstance(val, date):
        return val.isoformat()
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
        file: str = "",
        patient_id: str | None = None,
        ui_date: datetime | None = None,
        processing_status: RCPProcessingStatus | str = RCPProcessingStatus.COMPLETED,
        processing_step: str | None = None,
        processing_progress_pct: float = 0.0,
        sections: dict[str, Any] | None = None,
        execution_times: dict[str, float] | None = None,
        manual_edits: dict[str, dict[str, Any]] | None = None,
        *,
        document: str | None = None,
    ) -> None:
        self.file = file or document or ""
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
        self.manual_edits: dict[str, dict[str, Any]] = (
            dict(manual_edits) if manual_edits else {}
        )
        self.date_refresh: datetime = datetime.now()

    # ------------------------------------------------------------------
    # Section Schema Introspection
    # ------------------------------------------------------------------

    @classmethod
    def get_section_models(cls) -> list[type[BaseModel]]:
        """
        Return all domain section Pydantic models defined on this `PatientMDTForm` subclass
        (excluding `default_model` and `PatientMDTFormCheck`), ordered from fastest
        single-agent factual extractions to multi-agent expert evaluations and collaborative debates.
        """
        models = []
        for name, obj in inspect.getmembers(cls):
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModel)
                and name not in ("default_model", "PatientMDTFormCheck")
            ):
                models.append(obj)

        def _execution_order_key(model_cls: type[BaseModel]) -> tuple[int, int, str]:
            name = model_cls.__name__
            if name == "PatientAdministrative":
                return (0, 0, name)
            agents_count = len(getattr(model_cls, "agents", None) or [])
            is_collab = bool(getattr(model_cls, "collaborative", False))
            if not is_collab and agents_count <= 1:
                # 1. Single-agent factual clinical extractions first (~7-25s each)
                return (1, 0, name)
            if not is_collab:
                # 2. Multi-agent non-collaborative evaluations (e.g. ExpertAnswer)
                return (2, agents_count, name)
            # 3. Collaborative multi-agent debates last (MTDCompleted before CareOrientationProposal)
            debate_rank = 0 if name == "MTDCompleted" else 1
            return (3, debate_rank, name)

        return sorted(models, key=_execution_order_key)

    @classmethod
    def is_expert_section_model(cls, model_cls: type[BaseModel]) -> bool:
        """
        Return True if `model_cls` belongs to Wave 3 (`WAVE3_EXPERTS`: multi-agent
        specialist opinion or collaborative MDT debate).
        """
        if model_cls.__name__ in (
            "ExpertAnswer",
            "MTDCompleted",
            "CareOrientationProposal",
        ):
            return True
        if bool(getattr(model_cls, "collaborative", False)):
            return True
        agents = getattr(model_cls, "agents", None) or []
        return len(agents) > 1

    @classmethod
    def get_factual_clinical_models(cls) -> list[type[BaseModel]]:
        """
        Return factual single-agent clinical section models executed in Wave 2 (`WAVE2_CLINICAL`),
        excluding `PatientAdministrative` and Wave 3 expert/collaborative models.
        """
        return [
            m for m in cls.get_clinical_models() if not cls.is_expert_section_model(m)
        ]

    @classmethod
    def get_expert_models(cls) -> list[type[BaseModel]]:
        """
        Return multi-agent and collaborative expert section models executed in Wave 3 (`WAVE3_EXPERTS`).
        """
        return [m for m in cls.get_clinical_models() if cls.is_expert_section_model(m)]

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
            manual_edits=raw_doc.get("manual_edits") or {},
        )
        instance.hydrate_sections(raw_doc)
        return instance

    NON_EDITABLE_SECTIONS: tuple[str, ...] = (
        "CareOrientationProposal",
        "ExpertAnswer",
        "PatientMDTFormCheck",
    )

    @classmethod
    def is_section_manually_editable(
        cls, section_or_model: str | type[BaseModel]
    ) -> bool:
        """
        Return True if `section_or_model` can be manually modified by a user.
        AI synthesis/proposal sections (`CareOrientationProposal`, `ExpertAnswer`) are read-only.
        """
        if isinstance(section_or_model, str):
            model_cls = cls.get_section_model(section_or_model)
            name = section_or_model
        else:
            model_cls = section_or_model
            name = getattr(section_or_model, "__name__", str(section_or_model))

        if name in cls.NON_EDITABLE_SECTIONS or model_cls is None:
            return False
        if name == "MTDCompleted":
            return True
        if getattr(model_cls, "collaborative", False):
            return False
        if len(getattr(model_cls, "agents", [])) > 1:
            return False
        return True

    @classmethod
    def is_section_manually_edited(
        cls,
        doc_or_form: "dict[str, Any] | PatientMDTForm | None",
        section_name: str,
    ) -> bool:
        """Return True if `section_name` has been manually edited by a user."""
        if doc_or_form is None:
            return False
        if isinstance(doc_or_form, PatientMDTForm):
            manual_map = doc_or_form.manual_edits
        elif isinstance(doc_or_form, dict):
            manual_map = doc_or_form.get("manual_edits") or {}
        else:
            return False
        if not isinstance(manual_map, dict):
            return False
        entry = manual_map.get(section_name)
        return bool(isinstance(entry, dict) and entry.get("is_manual"))

    @classmethod
    def build_manual_edit_trace(
        cls,
        existing_doc: dict[str, Any] | None,
        section_name: str,
        new_validated_payload: dict[str, Any],
        *,
        edited_by: str | None = None,
        edited_at: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Build an updated `manual_edits` dictionary for `existing_doc` that preserves
        the original AI extraction (`ai_original`), field-level diffs (`modified_fields`),
        and chronological `edit_history` for downstream LLM-as-a-Judge evaluation.
        """
        doc = existing_doc or {}
        now = edited_at or datetime.now()
        manual_edits = dict(doc.get("manual_edits") or {})
        prev_entry = (
            dict(manual_edits.get(section_name))
            if isinstance(manual_edits.get(section_name), dict)
            else {}
        )
        current_section_val = (
            dict(doc.get(section_name))
            if isinstance(doc.get(section_name), dict)
            else None
        )

        # Capture the original AI output once before the first manual edit of the current AI cycle
        if prev_entry.get("is_manual") and "ai_original" in prev_entry:
            ai_original = prev_entry.get("ai_original")
        else:
            ai_original = (
                _serialize_persistence_value(dict(current_section_val))
                if isinstance(current_section_val, dict)
                else None
            )

        meta_keys = {"reasoning_thinking", "time_execution"}
        ai_clean = (
            {k: v for k, v in ai_original.items() if k not in meta_keys}
            if isinstance(ai_original, dict)
            else {}
        )
        human_clean = {
            k: v for k, v in (new_validated_payload or {}).items() if k not in meta_keys
        }

        all_field_keys = list(
            dict.fromkeys(list(ai_clean.keys()) + list(human_clean.keys()))
        )
        modified_fields: dict[str, dict[str, Any]] = {}
        for field_key in all_field_keys:
            ai_val = ai_clean.get(field_key)
            human_val = human_clean.get(field_key)
            if ai_val != human_val:
                modified_fields[field_key] = {
                    "ai_value": ai_val,
                    "human_value": human_val,
                }

        prev_clean = (
            {k: v for k, v in current_section_val.items() if k not in meta_keys}
            if isinstance(current_section_val, dict)
            else {}
        )
        step_keys = list(
            dict.fromkeys(list(prev_clean.keys()) + list(human_clean.keys()))
        )
        step_changed_fields = [
            k for k in step_keys if prev_clean.get(k) != human_clean.get(k)
        ]

        history = list(prev_entry.get("edit_history") or [])
        history.append(
            {
                "edited_at": now,
                "edited_by": edited_by,
                "previous_value": prev_clean if prev_clean else None,
                "new_value": human_clean,
                "changed_fields": step_changed_fields,
            }
        )

        ai_thinking = (
            ai_original.get("reasoning_thinking")
            if isinstance(ai_original, dict)
            else None
        )
        archived_traces = list(prev_entry.get("archived_judge_traces") or [])

        manual_edits[section_name] = {
            "is_manual": True,
            "edited_at": now,
            "edited_by": edited_by,
            "ai_original": ai_original,
            "ai_reasoning_thinking": ai_thinking,
            "human_value": human_clean,
            "modified_fields": modified_fields,
            "edit_history": history,
            "archived_judge_traces": archived_traces,
        }
        return manual_edits

    @classmethod
    def archive_manual_edit_before_ai_rerun(
        cls,
        manual_edits: dict[str, Any] | None,
        section_name: str,
        *,
        rerun_at: datetime | None = None,
    ) -> dict[str, Any]:
        """
        When a manually edited section is explicitly re-extracted by AI, clear the active
        `is_manual` protection flag while archiving the human-vs-AI comparison trace inside
        `archived_judge_traces` so LLM-as-a-Judge evaluation data is never lost.
        """
        updated_map = dict(manual_edits or {})
        entry = updated_map.get(section_name)
        if not isinstance(entry, dict):
            return updated_map

        now = rerun_at or datetime.now()
        archived = list(entry.get("archived_judge_traces") or [])
        if entry.get("is_manual") and (
            entry.get("modified_fields") or entry.get("human_value")
        ):
            archived.append(
                {
                    "archived_at": now,
                    "edited_at": entry.get("edited_at"),
                    "edited_by": entry.get("edited_by"),
                    "ai_original": entry.get("ai_original"),
                    "ai_reasoning_thinking": entry.get("ai_reasoning_thinking"),
                    "human_value": entry.get("human_value"),
                    "modified_fields": entry.get("modified_fields") or {},
                }
            )
        updated_map[section_name] = {
            "is_manual": False,
            "last_ai_rerun_at": now,
            "edit_history": list(entry.get("edit_history") or []),
            "archived_judge_traces": archived,
        }
        return updated_map

    @classmethod
    def validate_manual_section_update(
        cls,
        section_name: str,
        section_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate a manually edited section payload against the domain section model
        and return a persistence-ready dictionary.
        """
        model_cls = cls.get_section_model(section_name)
        if model_cls is None:
            raise ValueError(f"Unknown section model '{section_name}'.")
        if not cls.is_section_manually_editable(model_cls):
            raise ValueError(
                f"Section '{section_name}' is an AI synthesis proposal and cannot be manually modified."
            )

        payload = dict(section_data or {})
        if model_cls.__name__ == "PatientAdministrative":
            from src.domain.patient import PatientIdentity

            dob = PatientIdentity.parse_date_birth(payload.get("date_birth"))
            d_rcp = PatientIdentity.parse_date_birth(payload.get("date_rcp"))
            if dob and d_rcp and dob.replace(tzinfo=None) > d_rcp.replace(tzinfo=None):
                raise ValueError("Date of birth must be before Date of RCP")
            computed_age = PatientIdentity.compute_age(dob, d_rcp)
            if payload.get("age") is None:
                payload["age"] = computed_age if computed_age is not None else 0
            elif computed_age is not None:
                payload["age"] = computed_age
            if not payload.get("gender"):
                payload["gender"] = Gender.not_given.value  # noqa: F405
            payload["first_name"] = str(payload.get("first_name") or "").strip()
            payload["last_name"] = str(payload.get("last_name") or "").strip()
            validated = model_cls.model_validate(payload)
            dumped = _serialize_persistence_value(validated.model_dump())
            # Preserve historical date_rcp if manually entered (> 5 years ago)
            if d_rcp is not None and dumped.get("date_rcp") is None:
                dumped["date_rcp"] = _to_naive_paris(d_rcp)
            return dumped

        is_multi_agent = len(getattr(model_cls, "agents", [])) > 1 and not getattr(
            model_cls, "collaborative", False
        )
        if is_multi_agent:
            out: dict[str, Any] = {}
            for agent_key, agent_val in payload.items():
                if isinstance(agent_val, dict):
                    validated_sub = model_cls.model_validate(agent_val)
                    sub_dump = _serialize_persistence_value(validated_sub.model_dump())
                    if "reasoning_thinking" in agent_val:
                        sub_dump["reasoning_thinking"] = agent_val["reasoning_thinking"]
                    out[agent_key] = sub_dump
            return out

        validated = model_cls.model_validate(payload)
        dumped = _serialize_persistence_value(validated.model_dump())
        if "reasoning_thinking" in payload:
            dumped["reasoning_thinking"] = payload["reasoning_thinking"]
        return dumped

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
                        raw_agent_val = value[agent_cls.agent_name]
                        try:
                            validated_by_agent[agent_cls.agent_name] = (
                                model_cls.model_validate(raw_agent_val)
                            )
                        except ValidationError:
                            validated_by_agent[agent_cls.agent_name] = raw_agent_val
                if validated_by_agent:
                    self.sections[key] = validated_by_agent
            else:
                try:
                    self.sections[key] = model_cls.model_validate(value)
                except ValidationError:
                    self.sections[key] = value

    def to_persistence(self) -> dict[str, Any]:
        """Convert this domain aggregate into a persistence-ready dictionary."""
        payload: dict[str, Any] = {
            "file": self.file,
            "execution_times": dict(self.execution_times),
            "processing_status": self.processing_status,
        }
        if self.manual_edits:
            payload["manual_edits"] = _serialize_persistence_value(self.manual_edits)
        if self.patient_id is not None:
            payload["patient_id"] = self.patient_id
        if self.ui_date is not None:
            payload["ui_date"] = self.ui_date
        if self.processing_step is not None:
            payload["processing_step"] = self.processing_step
        if self.processing_progress_pct:
            payload["processing_progress_pct"] = self.processing_progress_pct

        for section_name, section_val in self.sections.items():
            payload[section_name] = _serialize_persistence_value(section_val)
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
            "PENDING_EXPERTS",
            "PROCESSING_EXPERTS",
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

        care_adaptation_suggested = None
        proposed_care_type = None
        suggested_priority_raw = None
        if "CareOrientationProposal" in d and isinstance(
            d["CareOrientationProposal"], dict
        ):
            proposal_data = d["CareOrientationProposal"]
            if "care_adaptation_suggested" in proposal_data:
                care_adaptation_suggested = proposal_data.get(
                    "care_adaptation_suggested"
                )
                proposed_care_type = proposal_data.get("proposed_care_type")
                suggested_priority_raw = proposal_data.get("suggested_priority")
            else:
                for agent_data in proposal_data.values():
                    if (
                        isinstance(agent_data, dict)
                        and "care_adaptation_suggested" in agent_data
                    ):
                        care_adaptation_suggested = agent_data.get(
                            "care_adaptation_suggested"
                        )
                        proposed_care_type = agent_data.get("proposed_care_type")
                        suggested_priority_raw = agent_data.get("suggested_priority")
                        break

        if suggested_priority_raw is not None:
            s_prio = str(
                suggested_priority_raw.value
                if isinstance(suggested_priority_raw, Enum)
                else suggested_priority_raw
            ).lower()
            is_manual_proposal = cls.is_section_manually_edited(
                d, "CareOrientationProposal"
            )
            for urgency in list(PatientPriority):  # noqa: F405
                if s_prio in (urgency.value.lower(), urgency.name.lower()):
                    if urgency.name == "urgent":
                        urgency_score = 2
                        urgency_level = "Urgent"
                    elif urgency.name == "medium":
                        if is_manual_proposal or urgency_score < 1:
                            urgency_score = 1
                            urgency_level = "Semi-urgent"
                    elif urgency.name == "low":
                        if is_manual_proposal or urgency_score == 0:
                            urgency_score = 0
                            urgency_level = "Standard"
                    elif urgency.name == "not_given" and is_manual_proposal:
                        urgency_score = 0
                        urgency_level = "Indéfini"
        elif (
            cls.is_section_manually_edited(d, "CareOrientationProposal")
            and care_adaptation_suggested is False
        ):
            urgency_score = 0
            urgency_level = "Standard"

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
            "care_adaptation_suggested": care_adaptation_suggested,
            "proposed_care_type": proposed_care_type,
            "intervention_required": care_adaptation_suggested,
            "intervention_type": proposed_care_type,
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
                    or doc.get("CareOrientationProposal")
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
            "manual_edits",
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

    class CareOrientationProposal(default_model):
        """
        Pre-MDT collaborative synthesis proposing whether an initiation or adaptation
        of patient care should be discussed by the medical board, its priority, and rationale.
        """

        agents: ClassVar[list[type[OncowflowAgent]]] = Agents().expert_agents
        collaborative = True

        care_adaptation_suggested: bool = Field(
            description=(
                "Does the clinical file suggest that an initiation or adaptation of care "
                "(medical, respiratory, nutritional, rehabilitative, or surgical) should be discussed by the physicians?"
            )
        )
        suggested_priority: Optional[PatientPriority] = Field(  # noqa: F405
            default=None,
            description="Suggested priority level for MDT discussion and care management. None if routine follow-up.",
        )
        proposed_care_type: Optional[str] = Field(
            default=None,
            description=(
                "Suggested area or modality of care to discuss during the MDT meeting "
                "(e.g., disease-modifying therapy, surgery, chemotherapy, NIV/Cough Assist, nutritional support, orthopedic care). "
                "None if no specific adaptation is suggested."
            ),
        )
        clinical_rationale: str = Field(
            description="Clinical rationale and guideline arguments summarizing the expert debate to assist the physicians."
        )

        question: ClassVar[str] = """
            Based on the multidisciplinary expert debate, synthesize a pre-MDT orientation proposal to assist the medical board (do not replace the physicians' final decision):
            Determine whether an initiation or adaptation of care should be discussed for this patient.
            If yes, specify:
            1. The suggested priority level for the MDT discussion.
               CRITICAL SAFETY RULE: If even a single expert in the debate flags the case as urgent or high priority, you MUST default to classifying `suggested_priority` as urgent (high priority), regardless of whether other experts recommend a lower priority.
            2. The proposed area or modality of care to discuss.
            Provide a clear clinical rationale detailing the positions of the experts and highlighting any divergence in opinions regarding urgency.
            """
