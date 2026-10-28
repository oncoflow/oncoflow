import os

from src.infrastructure.documents.mongodb import Mongodb


def delete_patient_dossier(
    app_conf, patient_id: str, delete_files: bool = True
) -> None:
    """
    Deletes a patient dossier and all its associated RCP documents from MongoDB and disk.
    """
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        patient_doc = client.get_patient(patient_id)
        files_to_delete = set()
        if patient_doc and isinstance(patient_doc.get("files"), list):
            files_to_delete.update(patient_doc["files"])

        rcp_docs = list(
            client.database["rcp_info"].find({"patient_id": patient_id}, {"file": 1})
        )
        for doc in rcp_docs:
            if doc.get("file"):
                files_to_delete.add(doc["file"])

        for fname in files_to_delete:
            client.delete_docs(
                collections=["rcp_info", "rcp_metadata", "document_cache"],
                filter={"file": fname},
            )
            if delete_files and os.path.exists(f"{app_conf.rcp.path}/{fname}"):
                os.remove(f"{app_conf.rcp.path}/{fname}")

        client.delete_docs(collections=["patients"], filter={"patient_id": patient_id})
        client.close()
