from src.application.config import AppConfig

config = AppConfig()

if config.domain == "oncology":
    from src.domain.oncology.patient_mdt_oncologic_form import (
        PatientMDTOncologicForm as PatientMDTForm,
    )
elif config.domain == "sma":
    from src.domain.sma.patient_mdt_sma_form import PatientMDTSmaForm as PatientMDTForm
else:
    raise ValueError(f"Domain {config.domain} not found")
PatientMDTForm = PatientMDTForm
