"""Pydantic request and response schemas for the `/api/v1/mdt-agenda` router."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.domain.mdt_agenda import MDTAgendaSortStrategy, PriorityLevelLiteral


class MDTAgendaUpdateRequest(BaseModel):
    """Payload to update Next MDT Agenda configuration options."""

    session_date: Optional[date | str] = Field(
        default=None, description="Selected MDT meeting date (YYYY-MM-DD)"
    )
    clear_session_date: bool = Field(
        default=False, description="When True, clears the selected session date"
    )
    sort_strategy: Optional[MDTAgendaSortStrategy] = Field(
        default=None,
        description="Ordering strategy ('hybrid', 'urgency_first', 'expert_grouping', 'manual')",
    )
    defer_incomplete_files: Optional[bool] = Field(
        default=None,
        description="Place incomplete files at the end of the session while preserving internal sort",
    )
    attending_experts: Optional[list[str]] = Field(
        default=None,
        description="Explicit list of attending domain specialist names",
    )
    toggle_expert: Optional[str] = Field(
        default=None,
        description="Single domain specialist name to toggle in or out of `attending_experts`",
    )
    patient_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional explicit list of enrolled patient IDs when initializing/resetting a meeting",
    )
    reset_enrolled_patients: bool = Field(
        default=False,
        description="When True, resets enrolled patients to `patient_ids` (or all domain patients if `patient_ids` is None)",
    )


class MDTAgendaAddPatientsRequest(BaseModel):
    """Payload to enroll one, several, or all candidate patients into the Next MDT Agenda."""

    patient_ids: list[str] = Field(
        default_factory=list,
        description="List of patient identifiers to add to the agenda",
    )
    patient_id: Optional[str] = Field(
        default=None,
        description="Optional single patient identifier to add to the agenda",
    )
    add_all_candidates: bool = Field(
        default=False,
        description="When True, enrolls candidate patients in the domain",
    )
    enroll_all_candidates: bool = Field(
        default=False,
        description="When True, enrolls candidate patients in the domain (alias for add_all_candidates)",
    )
    filter_mode: Optional[Literal["all", "complete", "urgent"]] = Field(
        default="all",
        description="Candidate filter mode when enrolling all candidates ('all', 'complete', 'urgent')",
    )


class MDTAgendaMovePatientRequest(BaseModel):
    """Payload to move a patient up/down or pin/unpin their position in the agenda."""

    direction: Optional[Literal["up", "down"]] = Field(
        default=None,
        description="Relative movement direction ('up' or 'down')",
    )
    target_position: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-indexed target position to move and pin the patient to",
    )
    pinned: Optional[bool] = Field(
        default=None,
        description="Explicit pin state (True to pin, False to unpin and return to automatic sort)",
    )


class MDTAgendaReorderRequest(BaseModel):
    """Payload to explicitly set the passage order of enrolled patients."""

    patient_ids: list[str] = Field(
        description="Ordered list of patient identifiers defining the new sequence"
    )
    switch_to_manual: bool = Field(
        default=True,
        description="When True, switches `sort_strategy` to `manual` and clears individual pins",
    )


class MDTAgendaScheduledItemResponse(BaseModel):
    """Scheduled patient item in the Next MDT Agenda."""

    position: int
    patient_id: str
    filename: str
    patient_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    urgency: str
    urgency_score: int
    priority_level: PriorityLevelLiteral
    is_complete: bool
    missing_count: int = 0
    missing_items: list[str] = Field(default_factory=list)
    care_adaptation_suggested: Optional[bool] = None
    proposed_care_type: Optional[str] = None
    required_experts: list[str] = Field(default_factory=list)
    present_required_experts: list[str] = Field(default_factory=list)
    absent_required_experts: list[str] = Field(default_factory=list)
    quorum_met: bool = True
    expert_coverage_ratio: float = 1.0
    cluster_key: str = ""
    pinned: bool = False
    rank_reason: str = ""
    mdt_date: Optional[datetime] = None


class MDTExpertWindowResponse(BaseModel):
    """Specialist presence window summary across the scheduled MDT agenda."""

    expert_name: str
    is_attending: bool
    case_count: int = 0
    urgent_case_count: int = 0
    first_position: Optional[int] = None
    last_position: Optional[int] = None
    is_contiguous: bool = True
    patient_ids: list[str] = Field(default_factory=list)


class MDTAgendaCandidateResponse(BaseModel):
    """Non-enrolled domain patient available to be added to the Next MDT Agenda."""

    patient_id: str
    filename: str
    patient_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    urgency: str
    urgency_score: int
    priority_level: PriorityLevelLiteral
    is_complete: bool
    missing_count: int = 0
    missing_items: list[str] = Field(default_factory=list)
    care_adaptation_suggested: Optional[bool] = None
    proposed_care_type: Optional[str] = None
    required_experts: list[str] = Field(default_factory=list)
    mdt_date: Optional[datetime] = None


class MDTAgendaDetailResponse(BaseModel):
    """Complete state of the domain's Next MDT Agenda including schedule, expert windows, and candidates."""

    agenda_id: str
    domain: str
    session_date: Optional[date] = None
    sort_strategy: MDTAgendaSortStrategy
    defer_incomplete_files: bool = False
    available_experts: list[str] = Field(default_factory=list)
    attending_experts: list[str] = Field(default_factory=list)
    total_enrolled: int = 0
    urgent_count: int = 0
    incomplete_count: int = 0
    quorum_warning_count: int = 0
    items: list[MDTAgendaScheduledItemResponse] = Field(default_factory=list)
    expert_windows: list[MDTExpertWindowResponse] = Field(default_factory=list)
    candidates: list[MDTAgendaCandidateResponse] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
