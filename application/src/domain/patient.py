from datetime import date, datetime
import re
from typing import Any, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator
from slugify import slugify

from src.domain.common.common_ressources import Gender


def _normalize_birth_date_slug(dt: datetime | date | str | None) -> str:
    """Normalize a date into a `YYYY_MM_DD` slug component (pure domain helper)."""
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        return dt.strftime("%Y_%m_%d")
    if isinstance(dt, date):
        return dt.strftime("%Y_%m_%d")
    if isinstance(dt, str):
        s = dt.strip()
        if not s:
            return ""
        try:
            parsed = datetime.fromisoformat(s)
            return parsed.strftime("%Y_%m_%d")
        except ValueError:
            pass
        m = re.search(r"(\d{4})[-/_](\d{2})[-/_](\d{2})", s)
        if m:
            return f"{m.group(1)}_{m.group(2)}_{m.group(3)}"
    return ""


class PatientIdentity(BaseModel):
    """
    Immutable Value Object representing a patient's civil identity and deterministic key generation.
    """

    model_config = ConfigDict(frozen=True)

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

    @field_validator("date_birth", mode="before")
    @classmethod
    def parse_date_birth(cls, v: Any) -> Optional[datetime]:
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime(v.year, v.month, v.day)
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

    @classmethod
    def compute_age(
        cls,
        date_birth: datetime | date | str | None,
        reference_date: datetime | date | str | None = None,
    ) -> int | None:
        """Compute patient age in years at `reference_date` (or today if omitted)."""
        dob = cls.parse_date_birth(date_birth)
        if dob is None:
            return None
        ref = cls.parse_date_birth(reference_date) or datetime.now()
        dob_naive = dob.replace(tzinfo=None)
        ref_naive = ref.replace(tzinfo=None)
        if dob_naive > ref_naive:
            return 0
        years = ref_naive.year - dob_naive.year
        if (ref_naive.month, ref_naive.day) < (dob_naive.month, dob_naive.day):
            years -= 1
        return max(0, years)

    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else "Inconnu"

    @property
    def display_label(self) -> str:
        if self.date_birth:
            return f"{self.full_name} ({self.date_birth.strftime('%d-%m-%Y')})"
        return self.full_name

    @property
    def name_key(self) -> str:
        return self.build_name_key(self.first_name, self.last_name)

    @staticmethod
    def build_name_key(first_name: str | None, last_name: str | None) -> str:
        """Build a normalized slug key based on last name and first name."""
        fn = (first_name or "").strip()
        ln = (last_name or "").strip()
        if fn.lower() in ("inconnu", "unknown", "none", "null"):
            fn = ""
        if ln.lower() in ("inconnu", "unknown", "none", "null"):
            ln = ""
        if not fn and not ln:
            return ""
        return slugify(f"{ln}_{fn}", separator="_")

    @classmethod
    def build_id(
        cls,
        first_name: str | None,
        last_name: str | None,
        date_birth: datetime | str | None = None,
        fallback_file: str | None = None,
    ) -> str:
        """
        Build a deterministic, normalized `patient_id` from `(last_name, first_name, date_birth)`.
        Falls back to `(last_name, first_name)` if `date_birth` is missing, or `fallback_file` if unknown.
        """
        name_key = cls.build_name_key(first_name, last_name)
        if not name_key:
            file_slug = slugify(fallback_file or "unknown", separator="_")
            return f"patient_{file_slug}"

        dob_str = _normalize_birth_date_slug(date_birth)
        if dob_str:
            return f"{name_key}_{dob_str}"
        return name_key

    def build_patient_id(self, fallback_file: str | None = None) -> str:
        return self.build_id(
            first_name=self.first_name,
            last_name=self.last_name,
            date_birth=self.date_birth,
            fallback_file=fallback_file,
        )


class Patient(BaseModel):
    """
    Pure Domain Aggregate Root representing a patient and the list of their associated PatientMDTForm filenames.
    Contains zero I/O or infrastructure dependencies.
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
        default_factory=list,
        description="List of associated PatientMDTForm PDF filenames",
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last update timestamp"
    )

    @field_validator("date_birth", mode="before")
    @classmethod
    def parse_date_birth(cls, v: Any) -> Optional[datetime]:
        return PatientIdentity.parse_date_birth(v)

    @field_validator("gender", mode="before")
    @classmethod
    def parse_gender(cls, v: Any) -> Gender:
        return PatientIdentity.parse_gender(v)

    @property
    def identity(self) -> PatientIdentity:
        return PatientIdentity(
            first_name=self.first_name,
            last_name=self.last_name,
            born_name=self.born_name,
            date_birth=self.date_birth,
            gender=self.gender,
        )

    @property
    def full_name(self) -> str:
        return self.identity.full_name

    @property
    def display_label(self) -> str:
        return self.identity.display_label

    @property
    def name_key(self) -> str:
        return self.identity.name_key

    @staticmethod
    def build_name_key(first_name: str | None, last_name: str | None) -> str:
        return PatientIdentity.build_name_key(first_name, last_name)

    @classmethod
    def build_id(
        cls,
        first_name: str | None,
        last_name: str | None,
        date_birth: datetime | str | None = None,
        fallback_file: str | None = None,
    ) -> str:
        return PatientIdentity.build_id(
            first_name=first_name,
            last_name=last_name,
            date_birth=date_birth,
            fallback_file=fallback_file,
        )

    def attach_file(self, filename: str) -> bool:
        """Attach a PatientMDTForm filename to this patient aggregate if not already present."""
        if not filename or filename in self.files:
            return False
        self.files.append(filename)
        self.updated_at = datetime.now()
        return True

    def detach_file(self, filename: str) -> bool:
        """Remove a PatientMDTForm filename from this patient aggregate."""
        if filename not in self.files:
            return False
        self.files = [f for f in self.files if f != filename]
        self.updated_at = datetime.now()
        return True

    def apply_to_administrative(
        self,
        admin_data: BaseModel | dict | None,
        *,
        recompute_age: bool = False,
    ) -> dict[str, Any]:
        """
        Enforce this patient's civil identity onto an administrative section dictionary
        while preserving visit-specific fields such as `date_rcp` and `age`.
        """
        if isinstance(admin_data, BaseModel):
            admin_dict = admin_data.model_dump()
        elif isinstance(admin_data, dict):
            admin_dict = dict(admin_data)
        else:
            admin_dict = {}

        admin_dict["first_name"] = self.first_name or admin_dict.get("first_name", "")
        admin_dict["last_name"] = self.last_name or admin_dict.get("last_name", "")
        if self.born_name is not None:
            admin_dict["born_name"] = self.born_name
        if self.date_birth is not None:
            admin_dict["date_birth"] = (
                self.date_birth.strftime("%Y-%m-%d")
                if isinstance(self.date_birth, datetime)
                else self.date_birth
            )
            if recompute_age or admin_dict.get("age") is None:
                computed_age = PatientIdentity.compute_age(
                    self.date_birth, admin_dict.get("date_rcp")
                )
                if computed_age is not None:
                    admin_dict["age"] = computed_age
        if self.gender is not None and self.gender != Gender.not_given:
            admin_dict["gender"] = self.gender.value
        return admin_dict

    @classmethod
    def from_administrative(
        cls,
        admin_data: BaseModel | dict | None,
        filename: str | None = None,
        existing_patient: "Patient | dict | None" = None,
        patient_id: str | None = None,
    ) -> Self:
        """Instantiate or update a `Patient` aggregate from `PatientAdministrative` data."""
        if isinstance(admin_data, BaseModel):
            admin_dict = admin_data.model_dump()
        elif isinstance(admin_data, dict):
            admin_dict = dict(admin_data)
        else:
            admin_dict = {}

        existing_dict: dict[str, Any] = {}
        if isinstance(existing_patient, BaseModel):
            existing_dict = existing_patient.model_dump()
        elif isinstance(existing_patient, dict):
            existing_dict = dict(existing_patient)

        first_name = (
            admin_dict.get("first_name") or existing_dict.get("first_name") or ""
        ).strip()
        last_name = (
            admin_dict.get("last_name") or existing_dict.get("last_name") or ""
        ).strip()
        born_name = admin_dict.get("born_name") or existing_dict.get("born_name")
        date_birth = admin_dict.get("date_birth") or existing_dict.get("date_birth")
        gender = (
            admin_dict.get("gender") or existing_dict.get("gender") or Gender.not_given
        )

        resolved_id = (
            patient_id
            or existing_dict.get("patient_id")
            or cls.build_id(
                first_name=first_name,
                last_name=last_name,
                date_birth=date_birth,
                fallback_file=filename,
            )
        )

        files = list(existing_dict.get("files", []))
        if filename and filename not in files:
            files.append(filename)

        return cls(
            patient_id=resolved_id,
            first_name=first_name,
            last_name=last_name,
            born_name=born_name,
            date_birth=date_birth,
            gender=gender,
            files=files,
            updated_at=datetime.now(),
        )

    @classmethod
    def from_persistence(cls, raw: dict[str, Any]) -> Self:
        """Hydrate a `Patient` aggregate from a persistence dictionary."""
        clean = {k: v for k, v in raw.items() if k not in ("_id", "name_key")}
        return cls.model_validate(clean)

    def to_persistence(self) -> dict[str, Any]:
        """Serialize this `Patient` aggregate into a persistence dictionary."""
        return {
            "patient_id": self.patient_id,
            "name_key": self.name_key,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "born_name": self.born_name,
            "date_birth": self.date_birth,
            "gender": (
                self.gender.value
                if isinstance(self.gender, Gender)
                else str(self.gender)
            ),
            "files": list(self.files),
            "updated_at": self.updated_at or datetime.now(),
        }
