from src.application.config import AppConfig
from src.domain.oncology.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.domain.sma.patient_mdt_sma_form import PatientMDTSmaForm

_DOMAIN_MDT_FORM_MAP = {
    "oncology": PatientMDTOncologicForm,
    "sma": PatientMDTSmaForm,
}


def get_domain_mdt_form_cls(domain: str | None = None):
    target = (domain or AppConfig().domain).strip().lower()
    if target not in _DOMAIN_MDT_FORM_MAP:
        raise ValueError(
            f"Domain '{target}' not found. Available domains: {list(_DOMAIN_MDT_FORM_MAP.keys())}"
        )
    return _DOMAIN_MDT_FORM_MAP[target]


config = AppConfig()
PatientMDTForm = get_domain_mdt_form_cls(config.domain)
