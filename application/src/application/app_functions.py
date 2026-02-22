import os
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.patient_mdt_oncologic_form import PatientMDTOncologicForm


def full_read_mtd_agents(app_conf, filename: str, logger, replace: bool = True):
    logger.info(f"Start reading {filename} ...")
    fiche_rcp = PatientMDTOncologicForm(config=app_conf, document=filename)
    fiche_rcp.read_all_models()
    fiche_rcp.insert_datas_in_db()


def delete_document(app_conf, filename, delete_file: bool = True):
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        client.delete_docs(
            collections=["rcp_info", "rcp_metadata"], filter={"file": filename}
        )
        if delete_file:
            if os.path.exists(f"{app_conf.rcp.path}/{filename}"):
                os.remove(f"{app_conf.rcp.path}/{filename}")
        client.close()
