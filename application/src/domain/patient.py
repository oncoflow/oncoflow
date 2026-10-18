from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from src.domain.common.common_ressources import Gender


class Patient(BaseModel):
    """
    Domain model representing a patient and their associated MDT/RCP files.
    """

    patient_id: str = Field(description="Unique normalized identifier of the patient")
    first_name: str = Field(default="", description="First name of the patient")
    last_name: str = Field(default="", description="Last name of the patient")
    born_name: Optional[str] = Field(
        default=None, description="Name of the patient at birth"
    )
    date_birth: Optional[datetime] = Field(
        default=None,
        description="Date of birth of the patient (Format: YYYY-MM-DD)",
    )
    gender: Gender = Field(
        default=Gender.not_given, description="Gender of the patient"
    )
    files: list[str] = Field(
        default_factory=list, description="List of associated RCP PDF filenames"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last update timestamp"
    )

    @field_validator("date_birth", mode="before")
    @classmethod
    def parse_date_birth(cls, v: Any) -> Optional[datetime]:
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return None
        return None

    @field_validator("gender", mode="before")
    @classmethod
    def parse_gender(cls, v: Any) -> Gender:
        if isinstance(v, Gender):
            return v
        if isinstance(v, str):
            for g in Gender:
                if v.lower() in (g.value.lower(), g.name.lower()):
                    return g
        return Gender.not_given

    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else "Inconnu"

    @property
    def display_label(self) -> str:
        if self.date_birth:
            return f"{self.full_name} ({self.date_birth.strftime('%d-%m-%Y')})"
        return self.full_name
