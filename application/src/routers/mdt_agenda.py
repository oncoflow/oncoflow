"""REST router for managing and scheduling the Next MDT Agenda (`/api/v1/mdt-agenda`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.use_cases.mdt_agenda import MDTAgendaService
from src.models.mdt_agenda import (
    MDTAgendaAddPatientsRequest,
    MDTAgendaDetailResponse,
    MDTAgendaMovePatientRequest,
    MDTAgendaReorderRequest,
    MDTAgendaUpdateRequest,
)
from src.routers.dependencies import DomainConfigDep, require_db

router = APIRouter(prefix="/mdt-agenda", tags=["mdt-agenda"])


def get_mdt_agenda_service(
    config: DomainConfigDep, db=Depends(require_db)
) -> MDTAgendaService:
    """FastAPI dependency providing a domain-scoped `MDTAgendaService`."""
    return MDTAgendaService.from_config(config, db_client=db)


MDTAgendaServiceDep = Annotated[MDTAgendaService, Depends(get_mdt_agenda_service)]


@router.get("", response_model=MDTAgendaDetailResponse)
def get_mdt_agenda(service: MDTAgendaServiceDep):
    """Retrieve the active Next MDT Agenda, scheduled items, specialist windows, and candidate pool."""
    return service.get_agenda_detail()


@router.patch("", response_model=MDTAgendaDetailResponse)
def update_mdt_agenda_options(
    request: MDTAgendaUpdateRequest,
    service: MDTAgendaServiceDep,
):
    """Update Next MDT Agenda options (`session_date`, `sort_strategy`, `attending_experts`, or enrolled `patient_ids`)."""
    try:
        return service.update_options(
            session_date=request.session_date,
            clear_session_date=request.clear_session_date,
            sort_strategy=request.sort_strategy,
            defer_incomplete_files=request.defer_incomplete_files,
            attending_experts=request.attending_experts,
            toggle_expert=request.toggle_expert,
            patient_ids=request.patient_ids,
            reset_enrolled_patients=request.reset_enrolled_patients,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post("/schedule", response_model=MDTAgendaDetailResponse)
def schedule_new_mdt_meeting(
    request: MDTAgendaUpdateRequest,
    service: MDTAgendaServiceDep,
):
    """Onboarding endpoint to schedule a new MDT meeting (sets date, strategy, attending experts, and enrolled patients)."""
    try:
        return service.update_options(
            session_date=request.session_date,
            clear_session_date=request.clear_session_date,
            sort_strategy=request.sort_strategy or "hybrid",
            defer_incomplete_files=False
            if request.defer_incomplete_files is None
            else request.defer_incomplete_files,
            attending_experts=request.attending_experts,
            patient_ids=request.patient_ids,
            reset_enrolled_patients=True,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post("/patients", response_model=MDTAgendaDetailResponse)
def add_patients_to_mdt_agenda(
    request: MDTAgendaAddPatientsRequest,
    service: MDTAgendaServiceDep,
):
    """Add one, multiple, or all candidate patients to the Next MDT Agenda and recompute passage order."""
    return service.add_patients(
        patient_ids=request.patient_ids,
        patient_id=request.patient_id,
        add_all_candidates=request.add_all_candidates,
        enroll_all_candidates=request.enroll_all_candidates,
        filter_mode=request.filter_mode,
    )


@router.delete("/patients/{patient_id}", response_model=MDTAgendaDetailResponse)
def remove_patient_from_mdt_agenda(
    patient_id: str,
    service: MDTAgendaServiceDep,
):
    """Remove a single patient from the Next MDT Agenda and recompute passage order."""
    return service.remove_patient(patient_id)


@router.delete("/patients", response_model=MDTAgendaDetailResponse)
def clear_mdt_agenda_patients(service: MDTAgendaServiceDep):
    """Clear all enrolled patients from the Next MDT Agenda."""
    return service.clear_patients()


@router.post(
    "/patients/{patient_id}/move",
    response_model=MDTAgendaDetailResponse,
)
def move_patient_in_mdt_agenda(
    patient_id: str,
    request: MDTAgendaMovePatientRequest,
    service: MDTAgendaServiceDep,
):
    """Move an enrolled patient up/down or pin/unpin their scheduled position."""
    try:
        return service.move_patient(
            patient_id=patient_id,
            direction=request.direction,
            target_position=request.target_position,
            pinned=request.pinned,
        )
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.put("/reorder", response_model=MDTAgendaDetailResponse)
def reorder_mdt_agenda_patients(
    request: MDTAgendaReorderRequest,
    service: MDTAgendaServiceDep,
):
    """Explicitly reorder enrolled patients in the Next MDT Agenda."""
    return service.reorder_patients(
        patient_ids=request.patient_ids,
        switch_to_manual=request.switch_to_manual,
    )
