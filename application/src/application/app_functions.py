import os
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.application.reader import DocumentReader
from src.application.agent.agent import OncowflowAgent
from langchain_core.output_parsers import PydanticOutputParser


def full_read_mtd_agents(app_conf, filename: str, logger, replace: bool = True):
    logger.info(f"Start reading {filename} ...")
    fiche_rcp = PatientMDTOncologicForm(config=app_conf, document=filename)
    data = fiche_rcp.read_all_models()

    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        if replace:
            delete_document(app_conf, filename, delete_file=False)
        client.prepare_insert_doc(collection="rcp_info", document=data)
        client.insert_docs()
        client.close()
    else:
        logger.info("Type %s not known, fallback to stdout", app_conf.rcp.display_type)


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
