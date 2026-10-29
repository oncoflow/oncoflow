from typing import List

from fastapi import APIRouter, HTTPException, status

from src.application.paths import UnsafePathError, safe_path
from src.application.reader import DocumentReader
from src.application.ressources import Ressources
from src.domain.agents import get_domain_agents
from src.models.rcp import ChatResponse
from src.models.resources import (
    ResourceChatRequest,
    ResourceIndexedResponse,
    ResourceIndexResponse,
)
from src.routers.dependencies import DomainConfigDep

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=List[ResourceIndexResponse])
def list_resources(config: DomainConfigDep):
    """Liste les ressources de référence clinique du domaine et leur état d'indexation vectorielle."""
    manager = Ressources(config)
    try:
        files = manager.list_ressources()
    except Exception as err:
        config.set_logger("oncoflow.api").exception("Failed to list resources")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de lister les ressources.",
        ) from err

    result = []
    for f in files:
        result.append({"filename": f, "is_indexed": manager.is_indexed(f)})
    return result


@router.post("/{filename}/index", response_model=ResourceIndexedResponse)
def index_resource(filename: str, config: DomainConfigDep):
    """Indexe une ressource scientifique de référence clinique dans la base vectorielle du domaine."""
    try:
        safe_path(config.rcp.additional_path, filename)
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err
    manager = Ressources(config)
    files = manager.list_ressources()
    if filename not in files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée dans le répertoire des ressources ({config.domain}).",
        )

    try:
        manager.index_ressource(filename)
        return {
            "filename": filename,
            "domain": config.domain,
            "message": "Ressource indexée avec succès.",
        }
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Failed to index resource %s", filename
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de l'indexation de la ressource.",
        ) from err


@router.post("/{filename}/chat", response_model=ChatResponse)
def chat_with_resource_agent(
    filename: str, request: ResourceChatRequest, config: DomainConfigDep
):
    """Dialogue avec l'agent Ressource Assistant pour interroger une ressource spécifique du domaine."""
    try:
        safe_path(config.rcp.additional_path, filename)
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err
    manager = Ressources(config)
    files = manager.list_ressources()
    if filename not in files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée ({config.domain}).",
        )

    if not manager.is_indexed(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La ressource '{filename}' doit d'abord être indexée.",
        )

    try:
        reader = DocumentReader(config, document=filename, document_type="ressource")
        agents = get_domain_agents(config.domain)
        agent_cls = agents.list["Ressource Assistant"]
        agent = agent_cls(config=config, additionnal_readers=[reader])
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Resource agent error on %s", filename
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la génération de la réponse.",
        ) from err
