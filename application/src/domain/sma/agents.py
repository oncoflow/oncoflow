from src.domain.common.agents import Agents as AgentsCommon


class Agents(AgentsCommon):
    class Neurologist_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "neurologist expert"
        expert_type = "neurological diseases / spinal muscular atrophy"

        ressources = [""]

    class Geneticist_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "geneticist expert"
        expert_type = "genetics / genetic mutations"

        ressources = [""]

    class Pulmonologist_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "pulmonologist expert"
        expert_type = "respiratory diseases / pulmonology"

        ressources = [""]

    class Physiotherapy_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "physiotherapy expert"
        expert_type = "physical medicine and rehabilitation"

        ressources = [""]

    class Orthopedist_expert_agent(AgentsCommon.Expert_model):
        agent_name: str = "orthopedist expert"
        expert_type = "orthopedic diseases and spine deformities"

        ressources = [""]
