import inspect
import os
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

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
from src.domain.agents import get_domain_agents
from src.domain.patient import Patient
from src.domain.patient_mdt_form import get_domain_mdt_form_cls
from src.application.paths import UnsafePathError, safe_path
from src.infrastructure.documents.mongodb import Mongodb
from src.routers.dependencies import DomainConfigDep, require_db
from src.models.rcp import (
    ChatRequest,
    ChatResponse,
    MessageResponse,
    PatientCardResponse,
    PatientDetailResponse,
    ProcessRequest,
    ProcessResponse,
    RCPCardResponse,
    UploadResponse,
)

router = APIRouter(prefix="/rcp", tags=["rcp"])

# --- Helpers ---

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _safe_rcp_path(base_dir, filename: str) -> str:
    """Resolve `filename` inside `base_dir` or raise HTTP 400."""
    try:
        return str(safe_path(base_dir, filename))
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err


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


def get_form_models(domain: str | None = None):
    """Récupère dynamiquement les classes de modèles définies dans le PatientMDTForm du domaine."""
    form_cls = get_domain_mdt_form_cls(domain)
    models = []
    for name, obj in inspect.getmembers(form_cls):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and name != "default_model"
        ):
            models.append(obj)
    return models


# --- Endpoints ---


@router.get("", response_model=List[RCPCardResponse])
def get_rcp_cards(db=Depends(require_db)):
    """Récupère la liste synthétique de tous les dossiers RCP du domaine."""
    db_datas = [d for d in db.database["rcp_info"].find() if is_rcp_visible_in_cards(d)]
    cards_data = [extract_rcp_card_dict(d) for d in db_datas]
    cards_data.sort(
        key=lambda x: x.get("date_refresh") or datetime.min,
        reverse=True,
    )
    return cards_data


@router.get("/patients", response_model=List[PatientCardResponse])
def get_patient_cards(db=Depends(require_db)):
    """Récupère la liste des dossiers patients synthétisés sur leur dernière RCP analysée."""
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
def get_patient_detail(patient_id: str, db=Depends(require_db)):
    """Récupère un dossier patient et l'historique chronologique de toutes ses fiches RCP."""
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
        "patient": patient.model_dump(mode="json"),
        "latest_file": latest_doc["file"] if latest_doc else None,
        "rcps": [serialize_mongo_doc(d) for d in rcps_list],
    }


@router.delete("/patients/{patient_id}", response_model=MessageResponse)
def delete_patient(patient_id: str, config: DomainConfigDep, db=Depends(require_db)):
    """Supprime un dossier patient et l'ensemble de ses fiches RCP."""
    raw_patient = db.get_patient(patient_id)
    if not raw_patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier patient '{patient_id}' n'existe pas.",
        )

    delete_patient_dossier(config, patient_id)
    return {"message": f"Dossier patient '{patient_id}' supprimé avec succès."}


@router.post("/patients/{patient_id}/chat", response_model=ChatResponse)
def chat_with_patient_dossier(
    patient_id: str,
    request: ChatRequest,
    config: DomainConfigDep,
    db=Depends(require_db),
):
    """Dialogue avec un agent expert sur l'intégralité du dossier patient (toutes ses fiches RCP)."""
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

    existing_files = []
    for f in files:
        try:
            candidate = safe_path(config.rcp.path, f)
        except UnsafePathError:
            continue
        if os.path.exists(candidate):
            existing_files.append(f)
    if not existing_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun fichier PDF RCP trouvé sur le disque pour le patient '{patient_id}'.",
        )

    agents = get_domain_agents(config.domain)
    available_agents = agents.list
    if request.agent_name not in available_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{request.agent_name}' non reconnu. Agents valides : {list(available_agents.keys())}",
        )

    try:
        form_cls = get_domain_mdt_form_cls(config.domain)
        patient_readers = [form_cls(config=config, document=f) for f in existing_files]
        agent_cls = available_agents[request.agent_name]
        agent = agent_cls(config=config, patient_readers=patient_readers)
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Agent error on patient dossier %s", patient_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la communication avec l'agent.",
        ) from err


@router.get("/{filename}", response_model=dict[str, Any])
def get_rcp_detail(filename: str, config: DomainConfigDep, db=Depends(require_db)):
    """Récupère les détails complets d'un dossier RCP."""
    _safe_rcp_path(config.rcp.path, filename)
    data = db.database["rcp_info"].find_one({"file": filename})
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier RCP '{filename}' n'a pas été trouvé.",
        )

    return serialize_mongo_doc(data)


@router.delete("/{filename}", response_model=MessageResponse)
def delete_rcp(filename: str, config: DomainConfigDep):
    """Supprime un dossier RCP de la base et du disque."""
    file_path = _safe_rcp_path(config.rcp.path, filename)
    if not os.path.exists(file_path):
        db = Mongodb(config)
        exists_in_db = db.database["rcp_info"].find_one({"file": filename}) is not None
        db.close()
        if not exists_in_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Le dossier RCP '{filename}' n'existe pas.",
            )

    delete_document(config, filename)
    return {"message": f"Dossier '{filename}' supprimé avec succès."}


@router.post("/upload", response_model=UploadResponse)
def upload_rcp_file(
    config: DomainConfigDep,
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
        chunks: list[bytes] = []
        total_read = 0
        while True:
            chunk = file.file.read(65536)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Fichier trop volumineux (limite : 50 Mo).",
                )
            chunks.append(chunk)
        file_bytes = b"".join(chunks)
        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le contenu du fichier n'est pas un PDF valide.",
            )
        filename, is_duplicate = resolve_rcp_upload(config, file_bytes, file.filename)

        if is_duplicate:
            return {
                "filename": filename,
                "domain": config.domain,
                "is_duplicate": True,
                "link": f"datas?file={filename}",
                "message": f"Attention : ce fichier existe déjà ('{filename}').",
            }

        target_path = os.path.join(config.rcp.path, filename)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as buffer:
            buffer.write(file_bytes)

        if config.queue.enabled and config.rcp.display_type == "mongodb":
            enqueue_res = enqueue_rcp_batch(
                app_conf=config,
                files_payload=[{"filename": filename, "patient_id": patient_id}],
                run_full_ai=run_full_ai,
            )
            return {
                "filename": filename,
                "domain": config.domain,
                "patient_id": patient_id,
                "batch_id": enqueue_res["batch_id"],
                "enqueued_count": enqueue_res["enqueued_count"],
                "already_queued_count": enqueue_res["already_queued_count"],
                "results": [serialize_mongo_doc(r) for r in enqueue_res["results"]],
                "message": "Fichier téléversé et ajouté à la file de traitement.",
            }

        _, patient_dict = ingest_and_associate_rcp(
            app_conf=config,
            filename=filename,
            patient_id=patient_id,
        )

        return {
            "filename": filename,
            "domain": config.domain,
            "is_duplicate": False,
            "patient_id": patient_dict.get("patient_id")
            if patient_dict
            else patient_id,
            "patient": patient_dict,
            "message": "Fichier téléversé, indexé et associé au patient avec succès.",
        }
    except HTTPException:
        raise
    except Exception as err:
        config.set_logger("oncoflow.api").exception("Failed to upload RCP file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de l'enregistrement du fichier.",
        ) from err


@router.post("/{filename}/process", response_model=ProcessResponse)
def process_rcp(filename: str, request: ProcessRequest, config: DomainConfigDep):
    """Ajoute un retraitement de modèle spécifique ou de fiche complète dans la file de traitement."""
    file_path = _safe_rcp_path(config.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'existe pas sur le disque ({config.domain}).",
        )

    try:
        matched_model_name = None
        matched_model = None
        if request.model_name:
            models = get_form_models(config.domain)
            for m in models:
                if m.__name__.lower() == request.model_name.lower():
                    matched_model = m
                    break

            if not matched_model:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Modèle '{request.model_name}' non reconnu pour le domaine '{config.domain}'. Modèles valides : {[m.__name__ for m in models]}",
                )
            matched_model_name = matched_model.__name__

        if config.queue.enabled and config.rcp.display_type == "mongodb":
            res = enqueue_rcp_rerun(
                app_conf=config,
                filename=filename,
                model_name=matched_model_name,
            )
            return {
                "filename": filename,
                "domain": config.domain,
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

        form_cls = get_domain_mdt_form_cls(config.domain)
        if matched_model_name and matched_model:
            reader = form_cls(config=config, document=filename)
            reader.read_model(matched_model, upsert=True)
            return {
                "message": f"Modèle '{matched_model_name}' retraité avec succès pour '{filename}'."
            }
        else:
            full_read_mtd_agents(
                app_conf=config,
                filename=filename,
                logger=config.set_logger("oncoflow.api"),
            )
            return {"message": f"Dossier complet '{filename}' retraité avec succès."}
    except HTTPException:
        raise
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Failed to process RCP %s", filename
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors du traitement du dossier.",
        ) from err


@router.post("/{filename}/chat", response_model=ChatResponse)
def chat_with_patient_agent(
    filename: str, request: ChatRequest, config: DomainConfigDep
):
    """Dialogue avec un agent expert pour un dossier patient donné."""
    file_path = _safe_rcp_path(config.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'existe pas ({config.domain}).",
        )

    agents = get_domain_agents(config.domain)
    available_agents = agents.list
    if request.agent_name not in available_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{request.agent_name}' non reconnu. Agents valides : {list(available_agents.keys())}",
        )

    try:
        form_cls = get_domain_mdt_form_cls(config.domain)
        reader = form_cls(config=config, document=filename)
        agent_cls = available_agents[request.agent_name]
        agent = agent_cls(config=config, mtd=reader)
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as err:
        config.set_logger("oncoflow.api").exception("Agent error on RCP %s", filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la communication avec l'agent.",
        ) from err


@router.get(
    "/{filename}/pdf",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_rcp_pdf(filename: str, config: DomainConfigDep):
    """Télécharge le fichier PDF original pour un dossier donné."""
    file_path = _safe_rcp_path(config.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'a pas été trouvé ({config.domain}).",
        )
    return FileResponse(file_path, media_type="application/pdf", filename=filename)
