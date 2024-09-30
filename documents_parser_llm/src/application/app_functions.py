import os
from src.infrastructure.documents.mongodb import Mongodb
from src.domain.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.application.reader import DocumentReader

def full_read_file(app_conf, filename: str,logger, replace: bool = True):
    logger.info(f"Start reading {filename} ...")
    rag = DocumentReader(app_conf, document=filename)
    fiche_rcp = PatientMDTOncologicForm()
    metadatas= {}
    for cl in fiche_rcp.basemodel_list:
        cl_prompt = fiche_rcp.base_prompt.copy()
        cl_prompt.extend(cl.base_prompt)
        rag.set_prompt(prompt=cl_prompt)
        rag.read_additionnal_document(docs_pdf=cl.ressources)
        
        logger.debug(f"Process {cl.__name__}")
        logger.debug(f"Question : {cl.question}")

        datas = rag.ask_in_document(
            query=cl.question, class_type=cl, models=cl.models
        )
        metadatas[cl.__name__] = rag.metadata
        if datas:
            # Set first response
            fiche_rcp.set_datas(cl, datas)
    del rag
    data = fiche_rcp.get_datas()
    data["file"] = filename
    metadatas["file"] = filename
    
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        if replace:
            delete_document(app_conf, filename, delete_file = False)
        client.prepare_insert_doc(collection="rcp_info", document=data)
        client.prepare_insert_doc(collection="rcp_metadata", document=metadatas)
        client.insert_docs()
        client.close()
    else:
        logger.info("Type %s not known, fallback to stdout", app_conf.rcp.display_type )
        
def delete_document(app_conf, filename, delete_file: bool = True):
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        client.delete_docs(collections=["rcp_info", "rcp_metadata"], filter={"file": filename})
        if delete_file:
            if os.path.exists(f"{app_conf.rcp.path}/{filename}"):
                os.remove(f"{app_conf.rcp.path}/{filename}")
        client.close()