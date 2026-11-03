"""REST router for managing domain bug reports and user suggestions (`/api/v1/bug-reports`)."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.domain.bug_report import BugCategory, BugReport, BugSeverity, BugStatus
from src.domain.repositories import BugReportRepository
from src.infrastructure.documents.repositories import MongoBugReportRepository
from src.models.bug_reports import (
    BugReportCreateRequest,
    BugReportDeleteResponse,
    BugReportResponse,
    BugReportStatusUpdateRequest,
)
from src.routers.dependencies import DomainConfigDep, require_db

router = APIRouter(prefix="/bug-reports", tags=["bug-reports"])


def get_bug_report_repo(
    config: DomainConfigDep, db=Depends(require_db)
) -> BugReportRepository:
    """Instantiate a domain-scoped `BugReportRepository` backed by MongoDB."""
    return MongoBugReportRepository(config, db_client=db)


BugReportRepoDep = Annotated[BugReportRepository, Depends(get_bug_report_repo)]


@router.get("", response_model=list[BugReportResponse])
def list_bug_reports(
    repo: BugReportRepoDep,
    status_filter: Annotated[Optional[BugStatus], Query(alias="status")] = None,
    severity: Annotated[Optional[BugSeverity], Query()] = None,
    category: Annotated[Optional[BugCategory], Query()] = None,
):
    """List bug reports for the active medical domain, optionally filtered by status, severity, or category."""
    return repo.list_all(
        status=status_filter.value if status_filter else None,
        severity=severity.value if severity else None,
        category=category.value if category else None,
    )


@router.post("", response_model=BugReportResponse)
def create_bug_report(
    request: BugReportCreateRequest,
    repo: BugReportRepoDep,
):
    """Create and persist a new bug report in the active medical domain."""
    report = BugReport(
        title=request.title,
        description=request.description,
        category=request.category,
        severity=request.severity,
        page=request.page,
        patient_id=request.patient_id,
        rcp_file=request.rcp_file,
        steps_to_reproduce=request.steps_to_reproduce,
        reporter=request.reporter,
    )
    return repo.save(report)


@router.patch("/{report_id}/status", response_model=BugReportResponse)
def update_bug_report_status(
    report_id: str,
    request: BugReportStatusUpdateRequest,
    repo: BugReportRepoDep,
):
    """Update the resolution status of an existing bug report."""
    updated = repo.update_status(report_id, request.status)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rapport de bug '{report_id}' introuvable.",
        )
    return updated


@router.delete("/{report_id}", response_model=BugReportDeleteResponse)
def delete_bug_report(
    report_id: str,
    repo: BugReportRepoDep,
):
    """Delete a bug report by its identifier."""
    deleted = repo.delete(report_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rapport de bug '{report_id}' introuvable.",
        )
    return {"bug_id": report_id, "deleted": True}
