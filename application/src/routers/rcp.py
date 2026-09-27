import os
import inspect
import shutil
from datetime import datetime
from typing import List

import pytz
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.application.config import AppConfig
from src.application.app_functions import delete_document, full_read_mtd_agents
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.documents.db_interface import get_db
from src.domain.common.common_ressources import PatientPriority
from src.domain.patient_mdt_form import PatientMDTForm
from src.domain.agents import Agents
from src.models.rcp import ProcessRequest, ChatRequest, RCPCardResponse, ChatResponse

app_conf = AppConfig()

router = APIRouter(prefix="/rcp", tags=["rcp"])

# --- Helpers ---


def to_naive(dt: datetime | None) -> datetime | None:
    """Convertit un datetime (aware ou naive) en datetime naive (Europe/Paris)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(pytz.timezone("Europe/Paris")).replace(tzinfo=None)
    return dt


def serialize_mongo_doc(doc: dict) -> dict:
    """Sert à rendre un document MongoDB sérialisable en JSON."""
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))

    # Recursively convert ObjectId and other non-serializable fields if any
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

    db_datas = list(db.database["rcp_info"].find())
    cards_data = []

    for d in db_datas:
        patient_name = "Inconnu"
        if "PatientAdministrative" in d:
            p = d["PatientAdministrative"]
            patient_name = f"{p.get('first_name', '')} {p.get('last_name', '')}"

        date_refresh = d.get(
            "ui_date",
            datetime.now(pytz.timezone("Europe/Paris")).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        date_refresh = to_naive(date_refresh)

        date_mcp = (
            d["PatientAdministrative"]["date_rcp"]
            if "PatientAdministrative" in d and "date_rcp" in d["PatientAdministrative"]
            else None
        )
        if isinstance(date_mcp, str):
            try:
                date_mcp = datetime.fromisoformat(date_mcp)
            except ValueError:
                date_mcp = None
        date_mcp = to_naive(date_mcp)

        relevant_experts = []
        urgency_level = "Indéfini"
        urgency_score = 0

        if "ExpertAnswer" in d and isinstance(d["ExpertAnswer"], dict):
            for agent_name, agent_data in d["ExpertAnswer"].items():
                if isinstance(agent_data, dict):
                    if agent_data.get("expert_relevant"):
                        relevant_experts.append(agent_name)

                    p_prio = str(agent_data.get("patient_priority", "")).lower()
                    for urgency in list(PatientPriority):
                        if p_prio == urgency.value.lower():
                            if urgency.name == "urgent":
                                if urgency_score < 2:
                                    urgency_score = 2
                                    urgency_level = "Urgent"
                            elif urgency.name == "medium":
                                if urgency_score < 1:
                                    urgency_score = 1
                                    urgency_level = "Semi-urgent"
                            elif urgency.name == "low":
                                urgency_level = "Standard"

        missing_data = []
        if "MTDCompleted" in d and isinstance(d["MTDCompleted"], dict):
            if "mtd_complete" in d["MTDCompleted"]:
                mtd_comp = d["MTDCompleted"].get("mtd_complete")
                if isinstance(mtd_comp, dict):
                    m = mtd_comp.get("what_missing", [])
                    if isinstance(m, list):
                        missing_data.extend(m)
            else:
                for agent_name, agent_data in d["MTDCompleted"].items():
                    if isinstance(agent_data, dict):
                        mtd_comp = agent_data.get("mtd_complete")
                        if isinstance(mtd_comp, dict):
                            m = mtd_comp.get("what_missing", [])
                            if isinstance(m, list):
                                missing_data.extend(m)
        else:
            missing_data.extend(["no data"])

        intervention_required = None
        intervention_type = None
        if "isInterventionRequiered" in d and isinstance(
            d["isInterventionRequiered"], dict
        ):
            int_data = d["isInterventionRequiered"]
            if "intervention_required" in int_data:
                intervention_required = int_data.get("intervention_required")
                intervention_type = int_data.get("intervention_type")
            else:
                for agent_data in int_data.values():
                    if (
                        isinstance(agent_data, dict)
                        and "intervention_required" in agent_data
                    ):
                        intervention_required = agent_data.get("intervention_required")
                        intervention_type = agent_data.get("intervention_type")
                        break

        cards_data.append(
            {
                "file": d["file"],
                "patient": patient_name,
                "date_refresh": date_refresh,
                "date": date_mcp,
                "experts": relevant_experts,
                "missing": list(set(missing_data)),
                "urgency": urgency_level,
                "urgency_score": urgency_score,
                "intervention_required": intervention_required,
                "intervention_type": intervention_type,
            }
        )

    return cards_data


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
def upload_rcp_file(file: UploadFile = File(...)):
    """Upload un fichier PDF RCP et initialise le formulaire associé."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seuls les fichiers PDF sont acceptés.",
        )

    filename = file.filename
    target_path = os.path.join(app_conf.rcp.path, filename)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        PatientMDTForm(config=app_conf, document=filename)

        return {
            "filename": filename,
            "message": "Fichier téléversé et initialisé avec succès.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur interne lors de l'enregistrement du fichier : {e}",
        )


@router.post("/{filename}/process")
def process_rcp(filename: str, request: ProcessRequest):
    """Lance ou relance le traitement IA pour un modèle spécifique ou tout le dossier."""
    file_path = os.path.join(app_conf.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'existe pas sur le disque.",
        )

    try:
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

            reader = PatientMDTForm(config=app_conf, document=filename)
            reader.read_model(matched_model, upsert=True)
            return {
                "message": f"Modèle '{matched_model.__name__}' retraité avec succès pour '{filename}'."
            }
        else:
            full_read_mtd_agents(
                app_conf=app_conf,
                filename=filename,
                logger=app_conf.set_logger("oncoflow.api"),
            )
            return {"message": f"Dossier complet '{filename}' retraité avec succès."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'exécution de l'IA : {e}",
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
