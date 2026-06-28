from src.domain.common.agents import Agents as AgentsCommon


class Agents(AgentsCommon):
    class Pancreas_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "pancreas expert"
        expert_type = "pancreas diseases"

        ressources = ["TNCDPANCREAS.pdf"]

    class Oesophagus_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "oesophagus expert"
        expert_type = "oesophagus diseases"

        ressources = ["TNCDOESOPHAGE.pdf"]

    class Hepatocellular_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "hepatocellular expert"
        expert_type = "hepatocellular diseases"

        ressources = ["TNCDCHC.pdf"]
