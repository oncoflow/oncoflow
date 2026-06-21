from src.domain.common.agents import Agents as AgentsCommon


class Agents(AgentsCommon):
    class Endocrine_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "endocrine expert"
        expert_type = "endocrine diseases"

        ressources = [""]
