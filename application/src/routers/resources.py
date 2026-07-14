from typing import List
from fastapi import APIRouter, HTTPException, status

from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.application.ressources import Ressources
from src.domain.agents import Agents
from src.models.rcp import ChatResponse
from src.models.resources import ResourceChatRequest, ResourceIndexResponse

app_conf = AppConfig()

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=List[ResourceIndexResponse])
def list_resources():
    """Liste les ressources de référence clinique et leur état d'indexation vectorielle."""
    manager = Ressources(app_conf)
    try:
        files = manager.list_ressources()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impossible de lister les ressources : {e}",
        )

    result = []
    for f in files:
        result.append({"filename": f, "is_indexed": manager.is_indexed(f)})
    return result


@router.post("/{filename}/index")
def index_resource(filename: str):
    """Indexe une ressource scientifique de référence clinique dans la base vectorielle."""
    manager = Ressources(app_conf)
    files = manager.list_ressources()
    if filename not in files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée dans le répertoire des ressources.",
        )

    try:
        manager.index_ressource(filename)
        return {"filename": filename, "message": "Ressource indexée avec succès."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur d'indexation : {e}",
        )


@router.post("/{filename}/chat", response_model=ChatResponse)
def chat_with_resource_agent(filename: str, request: ResourceChatRequest):
    """Dialogue avec l'agent Ressource Assistant pour interroger une ressource spécifique."""
    manager = Ressources(app_conf)
    files = manager.list_ressources()
    if filename not in files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée.",
        )

    if not manager.is_indexed(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La ressource '{filename}' doit d'abord être indexée.",
        )

    try:
        reader = DocumentReader(app_conf, document=filename, document_type="ressource")
        agents = Agents()
        agent_cls = agents.list["Ressource Assistant"]
        agent = agent_cls(config=app_conf, additionnal_readers=[reader])
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération de la réponse : {e}",
        )
