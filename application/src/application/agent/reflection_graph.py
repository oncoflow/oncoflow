import json

from pydantic import BaseModel

from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.domain.common_ressources import ExpertIntermediateResponse
from src.domain.agents import Agents


def run_reflection_graph(
    config: AppConfig,
    mtd: DocumentReader,
    model: BaseModel,
    logger,
) -> dict:
    """
    Orchestrates the multi-agent reflection workflow using LangGraph.
    Executes expert agents and passes their responses to a Synthesizer agent.
    """
    try:
        from langgraph.graph import StateGraph, START, END
        from typing import TypedDict
    except ImportError:
        logger.error("LangGraph is not installed. Please install it.")
        return {}

    # The experts output an intermediate response
    expert_agents = [
        magent(config=config, mtd=mtd, output_format=ExpertIntermediateResponse)
        for magent in model.agents
    ]

    # The synthesizer outputs the final required model
    synthesizer = Agents.Synthesizer_agent(config=config, mtd=mtd, output_format=model)

    class State(TypedDict):
        question: str
        expert_responses: dict
        final_result: dict

    def run_experts(state: State):
        responses = {}
        for agent in expert_agents:
            try:
                # Collect intermediate insights from each expert
                datas = json.loads(agent.ask(state["question"]).json())
                responses[agent.agent_name] = datas
            except Exception as e:
                logger.error(f"Error calling agent {agent.agent_name}: {e}")
        return {"expert_responses": responses}

    def synthesize(state: State):
        # Synthesize expert findings into the final response format
        experts_output_str = json.dumps(state["expert_responses"], indent=2)
        expected_keys = list(model.model_fields.keys())
        keys_str = ", ".join([f'"{k}"' for k in expected_keys])

        synth_question = f"""
        Original Question: {state["question"]}
        
        Experts' Findings:
        {experts_output_str}
        
        Please synthesize these findings and provide the definitive response conforming exactly to the requested output format.
        
        CRITICAL OUTPUT FORMAT INSTRUCTION:
        Your JSON output MUST be a dictionary containing exactly these top-level key(s): {keys_str}.
        Do not output the inner fields directly at the root. You must wrap them inside the required top-level key(s).

        IMPORTANT INSTRUCTION FOR EXPERT OPINIONS:
        You MUST fill the 'expert_opinions' list with the detailed reasoning and conclusions provided by each expert in the 'Experts' Findings' section. 
        For each expert, create an entry where:
        - name: The name of the expert (e.g., 'pancreas expert')
        - page: 0
        - position: 'Expert Opinion'
        - excerpt: A summary of what this expert said, their reasoning, and what they found missing.
        
        Use the 'references' list ONLY for actual document references (like TNCD) that the experts mentioned.
        """
        try:
            final_datas = json.loads(synthesizer.ask(synth_question).json())
        except Exception as e:
            logger.error(f"Error calling synthesizer: {e}")
            final_datas = {}
        return {"final_result": final_datas}

    # Build the graph
    workflow = StateGraph(State)
    workflow.add_node("run_experts", run_experts)
    workflow.add_node("synthesize", synthesize)

    workflow.add_edge(START, "run_experts")
    workflow.add_edge("run_experts", "synthesize")
    workflow.add_edge("synthesize", END)

    app = workflow.compile()

    initial_state = {
        "question": model.question,
        "expert_responses": {},
        "final_result": {},
    }
    final_state = app.invoke(initial_state)

    return final_state.get("final_result", {})
