from typing import List
from fastapi import APIRouter, HTTPException, status

from src.application.config import AppConfig
from src.domain.agents import Agents
from src.models.agents import AgentDetailResponse

app_conf = AppConfig()

router = APIRouter(prefix="/agents", tags=["agents"])


def _extract_agent_metadata(name: str, a_cls: type, config: AppConfig) -> dict:
    system_prompt = (
        a_cls.get_system_prompt()
        if hasattr(a_cls, "get_system_prompt")
        else getattr(a_cls, "system_prompt", "")
    )
    models = (
        a_cls.get_models(config)
        if hasattr(a_cls, "get_models")
        else (
            getattr(a_cls, "models", None)
            or [m.strip() for m in config.llm.models.split(",") if m.strip()]
        )
    )
    ressources = getattr(a_cls, "ressources", [])

    return {
        "name": name,
        "system_prompt": system_prompt,
        "models": models,
        "resources": ressources,
    }


@router.get("", response_model=List[AgentDetailResponse])
def list_agents():
    """Liste tous les agents configurés et leurs caractéristiques."""
    agents = Agents()
    return [
        _extract_agent_metadata(name, a_cls, app_conf)
        for name, a_cls in agents.list.items()
    ]


@router.get("/{agent_name}", response_model=AgentDetailResponse)
def get_agent_detail(agent_name: str):
    """Récupère les détails de configuration d'un agent spécifique."""
    agents = Agents()
    available_agents = agents.list

    if agent_name not in available_agents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' non trouvé. Agents valides : {list(available_agents.keys())}",
        )

    a_cls = available_agents[agent_name]
    return _extract_agent_metadata(agent_name, a_cls, app_conf)
