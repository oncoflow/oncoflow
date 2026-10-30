import os

from src.domain.oncology.agents import Agents as OncologyAgents
from src.domain.sma.agents import Agents as SmaAgents

_DOMAIN_AGENTS_MAP = {
    "oncology": OncologyAgents,
    "sma": SmaAgents,
}


def get_domain_agents_cls(domain: str | None = None):
    target = (domain or os.environ.get("APP_DOMAIN") or "oncology").strip().lower()
    if target not in _DOMAIN_AGENTS_MAP:
        raise ValueError(
            f"Domain '{target}' not found. Available domains: {list(_DOMAIN_AGENTS_MAP.keys())}"
        )
    return _DOMAIN_AGENTS_MAP[target]


def get_domain_agents(domain: str | None = None):
    cls = get_domain_agents_cls(domain)
    return cls()


Agents = get_domain_agents_cls()
