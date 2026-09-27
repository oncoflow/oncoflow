from typing import List
from fastapi import APIRouter, HTTPException, status

from src.application.config import AppConfig
from src.domain.agents import Agents
from src.models.agents import AgentDetailResponse

app_conf = AppConfig()

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=List[AgentDetailResponse])
def list_agents():
    """Liste tous les agents configurés et leurs caractéristiques."""
    agents = Agents()
    result = []

    for name, a_cls in agents.list.items():
        try:
            ag = a_cls(app_conf)
            system_prompt = ag.system_prompt
            models = ag.models
            ressources = getattr(ag, "ressources", [])
        except Exception:
            system_prompt = getattr(a_cls, "system_prompt", "")
            models = []
            ressources = getattr(a_cls, "ressources", [])

        result.append(
            {
                "name": name,
                "system_prompt": system_prompt,
                "models": models,
                "resources": ressources,
            }
        )
    return result


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
    try:
        ag = a_cls(app_conf)
        system_prompt = ag.system_prompt
        models = ag.models
        ressources = getattr(ag, "ressources", [])
    except Exception:
        system_prompt = getattr(a_cls, "system_prompt", "")
        models = []
        ressources = getattr(a_cls, "ressources", [])

    return {
        "name": agent_name,
        "system_prompt": system_prompt,
        "models": models,
        "resources": ressources,
    }
