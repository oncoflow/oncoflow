import os
import inspect
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.application.config import AppConfig
from src.application.app_functions import (
    delete_document,
    delete_patient_dossier,
    enqueue_rcp_batch,
    enqueue_rcp_rerun,
    full_read_mtd_agents,
    ingest_and_associate_rcp,
    resolve_rcp_upload,
)
from src.application.patient import (
    extract_card_metrics as extract_rcp_card_dict,
    is_rcp_visible_in_cards,
    select_latest_analyzed_rcp as select_latest_rcp_doc,
    to_naive,
)
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.documents.db_interface import get_db
from src.domain.patient import Patient
from src.domain.patient_mdt_form import PatientMDTForm
from src.domain.agents import Agents
from src.models.rcp import (
    ProcessRequest,
    ChatRequest,
    RCPCardResponse,
    PatientCardResponse,
    PatientDetailResponse,
    ChatResponse,
)

app_conf = AppConfig()

router = APIRouter(prefix="/rcp", tags=["rcp"])

# --- Helpers ---


def serialize_mongo_doc(doc: dict) -> dict:
    """Sert à rendre un document MongoDB sérialisable en JSON."""
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))

    for k, v in doc.items():
        if isinstance(v, dict):
            doc[k] = serialize_mongo_doc(v)
        elif isinstance(v, list):
            doc[k] = [
                serialize_mongo_doc(item) if isinstance(item, dict) else item
                for item in v
            ]
    return doc


def get_form_models():
    """Récupère dynamiquement les classes de modèles définies dans PatientMDTForm"""
    models = []
    for name, obj in inspect.getmembers(PatientMDTForm):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name != "default_model"
        ):
            models.append(obj)
    return models


# --- Endpoints ---


@router.get("", response_model=List[RCPCardResponse])
def get_rcp_cards(db=Depends(get_db)):
    """Récupère la liste synthétique de tous les dossiers RCP."""
    if db is None or not hasattr(db, "database"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La base de données MongoDB n'est pas configurée ou accessible.",
        )

    db_datas = [d for d in db.database["rcp_info"].find() if is_rcp_visible_in_cards(d)]
    cards_data = [extract_rcp_card_dict(d) for d in db_datas]
    cards_data.sort(
        key=lambda x: x.get("date_refresh") or datetime.min,
        reverse=True,
    )
    return cards_data


@router.get("/patients", response_model=List[PatientCardResponse])
def get_patient_cards(db=Depends(get_db)):
    """Récupère la liste des dossiers patients synthétisés sur leur dernière RCP analysée."""
    if db is None or not hasattr(db, "database"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La base de données MongoDB n'est pas configurée ou accessible.",
        )

    all_rcps = list(db.database["rcp_info"].find())
    rcps_by_file = {d["file"]: d for d in all_rcps if "file" in d}
    raw_patients = db.get_all_patients() if hasattr(db, "get_all_patients") else []

    patient_cards: list[dict] = []
    for raw_p in raw_patients:
        try:
            patient = Patient.model_validate(raw_p)
        except Exception:
            continue

        patient_rcps_map: dict[str, dict] = {}
        for f in patient.files:
            if f in rcps_by_file:
                patient_rcps_map[f] = rcps_by_file[f]
        for d in all_rcps:
            if d.get("patient_id") == patient.patient_id and "file" in d:
                patient_rcps_map[d["file"]] = d

        patient_rcps = list(patient_rcps_map.values())
        if not patient_rcps:
            continue

        latest_doc = select_latest_rcp_doc(patient_rcps)
        if latest_doc is None:
            continue

        card = extract_rcp_card_dict(latest_doc)
        patient_cards.append(
            {
                "patient_id": patient.patient_id,
                "patient": patient.full_name,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "date_birth": to_naive(patient.date_birth),
                "rcp_count": len(patient_rcps),
                "latest_file": latest_doc["file"],
                "date_refresh": card["date_refresh"],
                "date": card["date"],
                "experts": card["experts"],
                "missing": card["missing"],
                "urgency": card["urgency"],
                "urgency_score": card["urgency_score"],
                "intervention_required": card["intervention_required"],
                "intervention_type": card["intervention_type"],
            }
        )

    return patient_cards


@router.get("/patients/{patient_id}", response_model=PatientDetailResponse)
def get_patient_detail(patient_id: str, db=Depends(get_db)):
    """Récupère un dossier patient et l'historique chronologique de toutes ses fiches RCP."""
    if db is None or not hasattr(db, "database"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La base de données MongoDB n'est pas configurée ou accessible.",
        )

    raw_patient = db.get_patient(patient_id)
    if not raw_patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier patient '{patient_id}' n'a pas été trouvé.",
        )

    patient = Patient.model_validate(raw_patient)
    rcps_map: dict[str, dict] = {}
    for f in patient.files:
        doc = db.database["rcp_info"].find_one({"file": f})
        if doc:
            rcps_map[f] = doc
    for doc in db.database["rcp_info"].find({"patient_id": patient_id}):
        if "file" in doc:
            rcps_map[doc["file"]] = doc

    rcps_list = list(rcps_map.values())
    rcps_list.sort(
        key=lambda d: (
            extract_rcp_card_dict(d).get("date")
            or extract_rcp_card_dict(d).get("date_refresh")
            or datetime.min
        ),
        reverse=True,
    )
    latest_doc = select_latest_rcp_doc(rcps_list)

    return {
        "patient": serialize_mongo_doc(raw_patient),
        "latest_file": latest_doc["file"] if latest_doc else None,
        "rcps": [serialize_mongo_doc(d) for d in rcps_list],
    }


@router.delete("/patients/{patient_id}")
def delete_patient(patient_id: str, db=Depends(get_db)):
    """Supprime un dossier patient et l'ensemble de ses fiches RCP."""
    if db is None or not hasattr(db, "database"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La base de données MongoDB n'est pas configurée ou accessible.",
        )

    raw_patient = db.get_patient(patient_id)
    if not raw_patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier patient '{patient_id}' n'existe pas.",
        )

    delete_patient_dossier(app_conf, patient_id)
    return {"message": f"Dossier patient '{patient_id}' supprimé avec succès."}


@router.post("/patients/{patient_id}/chat", response_model=ChatResponse)
def chat_with_patient_dossier(
    patient_id: str, request: ChatRequest, db=Depends(get_db)
):
    """Dialogue avec un agent expert sur l'intégralité du dossier patient (toutes ses fiches RCP)."""
    if db is None or not hasattr(db, "database"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La base de données MongoDB n'est pas configurée ou accessible.",
        )

    raw_patient = db.get_patient(patient_id)
    if not raw_patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier patient '{patient_id}' n'existe pas.",
        )

    patient = Patient.model_validate(raw_patient)
    files = list(patient.files)
    for doc in db.database["rcp_info"].find({"patient_id": patient_id}):
        if "file" in doc and doc["file"] not in files:
            files.append(doc["file"])

    existing_files = [
        f for f in files if os.path.exists(os.path.join(app_conf.rcp.path, f))
    ]
    if not existing_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun fichier PDF RCP trouvé sur le disque pour le patient '{patient_id}'.",
        )

    agents = Agents()
    available_agents = agents.list
    if request.agent_name not in available_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{request.agent_name}' non reconnu. Agents valides : {list(available_agents.keys())}",
        )

    try:
        patient_readers = [
            PatientMDTForm(config=app_conf, document=f) for f in existing_files
        ]
        agent_cls = available_agents[request.agent_name]
        agent = agent_cls(config=app_conf, patient_readers=patient_readers)
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur de communication avec l'agent : {e}",
        )


@router.get("/{filename}")
def get_rcp_detail(filename: str, db=Depends(get_db)):
    """Récupère les détails complets d'un dossier RCP."""
    if db is None or not hasattr(db, "database"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La base de données MongoDB n'est pas configurée ou accessible.",
        )

    data = db.database["rcp_info"].find_one({"file": filename})
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier RCP '{filename}' n'a pas été trouvé.",
        )

    return serialize_mongo_doc(data)


@router.delete("/{filename}")
def delete_rcp(filename: str):
    """Supprime un dossier RCP de la base et du disque."""
    file_path = os.path.join(app_conf.rcp.path, filename)
    if not os.path.exists(file_path):
        db = Mongodb(app_conf)
        exists_in_db = db.database["rcp_info"].find_one({"file": filename}) is not None
        db.close()
        if not exists_in_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Le dossier RCP '{filename}' n'existe pas.",
            )

    delete_document(app_conf, filename)
    return {"message": f"Dossier '{filename}' supprimé avec succès."}


@router.post("/upload")
def upload_rcp_file(
    file: UploadFile = File(...),
    patient_id: Optional[str] = Form(default=None),
    run_full_ai: bool = Form(default=True),
):
    """
    Upload un fichier PDF RCP, vérifie l'absence de doublon par empreinte SHA-256,
    renomme systématiquement les nouveaux fichiers, et l'ajoute à la file de traitement
    (ou l'exécute directement si la file est désactivée).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seuls les fichiers PDF sont acceptés.",
        )

    try:
        file_bytes = file.file.read()
        filename, is_duplicate = resolve_rcp_upload(app_conf, file_bytes, file.filename)

        if is_duplicate:
            return {
                "filename": filename,
                "is_duplicate": True,
                "link": f"datas?file={filename}",
                "message": f"Attention : ce fichier existe déjà ('{filename}').",
            }

        target_path = os.path.join(app_conf.rcp.path, filename)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as buffer:
            buffer.write(file_bytes)

        if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
            enqueue_res = enqueue_rcp_batch(
                app_conf=app_conf,
                files_payload=[{"filename": filename, "patient_id": patient_id}],
                run_full_ai=run_full_ai,
            )
            return {
                "filename": filename,
                "patient_id": patient_id,
                "batch_id": enqueue_res["batch_id"],
                "enqueued_count": enqueue_res["enqueued_count"],
                "already_queued_count": enqueue_res["already_queued_count"],
                "results": [serialize_mongo_doc(r) for r in enqueue_res["results"]],
                "message": "Fichier téléversé et ajouté à la file de traitement.",
            }

        _, patient_dict = ingest_and_associate_rcp(
            app_conf=app_conf,
            filename=filename,
            patient_id=patient_id,
        )

        return {
            "filename": filename,
            "is_duplicate": False,
            "patient_id": patient_dict.get("patient_id")
            if patient_dict
            else patient_id,
            "patient": patient_dict,
            "message": "Fichier téléversé, indexé et associé au patient avec succès.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur interne lors de l'enregistrement du fichier : {e}",
        )


@router.post("/{filename}/process")
def process_rcp(filename: str, request: ProcessRequest):
    """Ajoute un retraitement de modèle spécifique ou de fiche complète dans la file de traitement."""
    file_path = os.path.join(app_conf.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'existe pas sur le disque.",
        )

    try:
        matched_model_name = None
        if request.model_name:
            models = get_form_models()
            matched_model = None
            for m in models:
                if m.__name__.lower() == request.model_name.lower():
                    matched_model = m
                    break

            if not matched_model:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Modèle '{request.model_name}' non reconnu. Modèles valides : {[m.__name__ for m in models]}",
                )
            matched_model_name = matched_model.__name__

        if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
            res = enqueue_rcp_rerun(
                app_conf=app_conf,
                filename=filename,
                model_name=matched_model_name,
            )
            return {
                "filename": filename,
                "model_name": matched_model_name,
                "queued": not res.get("already_queued"),
                "already_queued": res["already_queued"],
                "jobs": [serialize_mongo_doc(j) for j in res.get("jobs", [])],
                "message": (
                    "Tâche ajoutée à la file de traitement."
                    if not res.get("already_queued")
                    else "Une tâche est déjà active dans la file de traitement."
                ),
            }

        if matched_model_name:
            reader = PatientMDTForm(config=app_conf, document=filename)
            reader.read_model(matched_model, upsert=True)
            return {
                "message": f"Modèle '{matched_model_name}' retraité avec succès pour '{filename}'."
            }
        else:
            full_read_mtd_agents(
                app_conf=app_conf,
                filename=filename,
                logger=app_conf.set_logger("oncoflow.api"),
            )
            return {"message": f"Dossier complet '{filename}' retraité avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du traitement : {e}",
        )


@router.post("/{filename}/chat", response_model=ChatResponse)
def chat_with_patient_agent(filename: str, request: ChatRequest):
    """Dialogue avec un agent expert pour un dossier patient donné."""
    file_path = os.path.join(app_conf.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'existe pas.",
        )

    agents = Agents()
    available_agents = agents.list
    if request.agent_name not in available_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{request.agent_name}' non reconnu. Agents valides : {list(available_agents.keys())}",
        )

    try:
        reader = PatientMDTForm(config=app_conf, document=filename)
        agent_cls = available_agents[request.agent_name]
        agent = agent_cls(config=app_conf, mtd=reader)
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur de communication avec l'agent : {e}",
        )


@router.get("/{filename}/pdf")
def download_rcp_pdf(filename: str):
    """Télécharge le fichier PDF original pour un dossier donné."""
    file_path = os.path.join(app_conf.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'a pas été trouvé.",
        )
    return FileResponse(file_path, media_type="application/pdf", filename=filename)
