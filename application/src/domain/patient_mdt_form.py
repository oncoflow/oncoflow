from src.domain.common.patient_mdt_common_form import (
    NonPatientMDTFormError,
    PatientMDTForm as BasePatientMDTForm,
)
from src.domain.oncology.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.domain.sma.patient_mdt_sma_form import PatientMDTSmaForm

_DOMAIN_MDT_FORM_MAP: dict[str, type[BasePatientMDTForm]] = {
    "oncology": PatientMDTOncologicForm,
    "sma": PatientMDTSmaForm,
}


def get_domain_mdt_form_cls(
    domain: str | None = None,
) -> type[BasePatientMDTForm]:
    """Return the domain-specific `PatientMDTForm` aggregate class."""
    target = (domain or "oncology").strip().lower()
    if target not in _DOMAIN_MDT_FORM_MAP:
        raise ValueError(
            f"Domain '{target}' not found. Available domains: {list(_DOMAIN_MDT_FORM_MAP.keys())}"
        )
    return _DOMAIN_MDT_FORM_MAP[target]


PatientMDTForm = PatientMDTOncologicForm

__all__ = [
    "BasePatientMDTForm",
    "NonPatientMDTFormError",
    "PatientMDTForm",
    "PatientMDTOncologicForm",
    "PatientMDTSmaForm",
    "get_domain_mdt_form_cls",
]
