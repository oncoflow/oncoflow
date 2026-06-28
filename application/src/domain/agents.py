from src.application.config import AppConfig

config = AppConfig()

if config.domain == "oncology":
    from src.domain.oncology.agents import Agents
elif config.domain == "sma":
    from src.domain.sma.agents import Agents
else:
    raise ValueError(f"Domain {config.domain} not found")

Agents = Agents
