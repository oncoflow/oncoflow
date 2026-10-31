"""Pydantic request and response schemas for the `/api/v1/bug-reports` router."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.domain.bug_report import BugCategory, BugSeverity, BugStatus


class BugReportCreateRequest(BaseModel):
    """Payload to create a new bug report or improvement suggestion."""

    title: str = Field(min_length=1, description="Short title summarizing the issue")
    description: str = Field(
        min_length=1, description="Detailed description of the bug or suggestion"
    )
    category: BugCategory = Field(
        default=BugCategory.other, description="Functional category of the report"
    )
    severity: BugSeverity = Field(
        default=BugSeverity.medium, description="Severity or impact level"
    )
    page: Optional[str] = Field(
        default=None, description="Application page or component concerned"
    )
    patient_id: Optional[str] = Field(
        default=None, description="Optional patient record identifier"
    )
    rcp_file: Optional[str] = Field(
        default=None, description="Optional PatientMDTForm PDF filename"
    )
    steps_to_reproduce: Optional[str] = Field(
        default=None, description="Steps to reproduce the issue"
    )
    reporter: Optional[str] = Field(
        default="anonymous", description="Username of the reporter"
    )


class BugReportStatusUpdateRequest(BaseModel):
    """Payload to update the resolution status of an existing bug report."""

    status: BugStatus = Field(description="Target status for the bug report")


class BugReportResponse(BaseModel):
    """Serialized representation of a `BugReport` returned by the API."""

    bug_id: str
    title: str
    description: str
    category: BugCategory
    severity: BugSeverity
    status: BugStatus
    page: Optional[str] = None
    patient_id: Optional[str] = None
    rcp_file: Optional[str] = None
    steps_to_reproduce: Optional[str] = None
    reporter: Optional[str] = "anonymous"
    created_at: datetime
    updated_at: Optional[datetime] = None


class BugReportDeleteResponse(BaseModel):
    """Confirmation response when a bug report is deleted."""

    bug_id: str
    deleted: bool
