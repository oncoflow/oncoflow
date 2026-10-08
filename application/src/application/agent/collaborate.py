import json
import gc

from typing import Any
from pydantic import BaseModel


from src.application.config import AppConfig

# Legacy import to support existing patch-based unit tests
from src.application.reader import DocumentReader
from src.application.agent.agent import OncowflowAgent, DebateTurn
from src.domain.agents import Agents


def collaborative_debate(
    agents_classes: list[type[OncowflowAgent]],
    question: str,
    output_format: type[BaseModel],
    config: AppConfig,
    mtd: DocumentReader,
    logger: Any,
    coordinator_agent_cls: type["OncowflowAgent"] | None = None,
    callbacks: list | None = None,
) -> dict:
    if coordinator_agent_cls is None:
        coordinator_agent_cls = Agents.Coordinator_agent
    logger.info("Running collaborative debate mode...")
    # Step 0 : init agents, name them and assign resources to them
    agents = []
    for magent in agents_classes:
        a = magent(config=config, mtd=mtd, output_format=DebateTurn)
        agents.append(a)
    # Step 1: Initial Turn (Parallel Reasoning with DebateTurn format)
    opinions = {}
    for magent in agents:
        logger.info(f"Debate: Requesting initial analysis from {magent.agent_name}...")

        opinion_prompt = (
            f"Answer in {magent.response_language.capitalize()} language, not mention it in the answer.\n"
            f"As an expert in {magent.expert_type if hasattr(magent, 'expert_type') else magent.agent_name}, "
            f"analyze the patient file and provide your initial arguments regarding the following question:\n{question}"
        )
        try:
            res = magent.ask(opinion_prompt, DebateTurn, callbacks=callbacks)
            opinions[magent.agent_name] = res.response
        except Exception as e:
            logger.error(f"Error getting opinion from {magent.agent_name}: {e}")
            opinions[magent.agent_name] = "Erreur ou pas d'avis fourni."

    # Step 2: Cross-Review & Debate Turn
    compiled_opinions = "\n".join(
        f"- **{name}** : {text}" for name, text in opinions.items()
    )
    logger.debug(f"Debate: Compiled initial opinions:\n{compiled_opinions}")

    updated_opinions = {}
    for magent in agents:
        logger.info(f"Debate: Requesting cross-review from {magent.agent_name}...")

        debate_prompt = (
            f"Answer in {magent.response_language.capitalize()} language, not mention it in the answer.\n"
            f"We are conducting a multidisciplinary team (MDT/RCP) debate. Here are the initial opinions and arguments from all participating experts:\n\n"
            f"{compiled_opinions}\n\n"
            f"The overall question is: {question}\n\n"
            f"Please review the opinions of the other experts. Provide your final refined clinical assessment, addressing points of agreement or disagreement, to help reach a collective consensus."
        )
        try:
            res = magent.ask(debate_prompt, DebateTurn, callbacks=callbacks)
            updated_opinions[magent.agent_name] = res.response
        except Exception as e:
            logger.error(f"Error getting updated opinion from {magent.agent_name}: {e}")
            updated_opinions[magent.agent_name] = opinions.get(
                magent.agent_name, "No opinion provided."
            )

    for a in agents:
        del a
    del agents
    gc.collect()

    # Step 3: Synthesis & Final Structured Consensus
    final_compiled_opinions = "\n".join(
        f"- **{name}** : {text}" for name, text in updated_opinions.items()
    )
    logger.debug(f"Debate: Compiled final opinions:\n{final_compiled_opinions}")

    # Use the coordinator_agent_cls to generate final structured pydantic format
    coordinator = coordinator_agent_cls(
        config=config, mtd=mtd, output_format=output_format, reasoning=False
    )
    logger.info(
        f"Debate: Synthesizing final structured consensus using {coordinator.agent_name}..."
    )

    synthesis_prompt = (
        f"Answer in {coordinator.response_language.capitalize()} language, not mention it in the answer.\n"
        f"You are the coordinator of the multidisciplinary team (MDT/RCP). The experts have completed their debate. "
        f"Here is the summary of their final opinions:\n\n"
        f"{final_compiled_opinions}\n\n"
        f"The overall question is: {question}\n\n"
        f"Based only on the opinions of the experts, synthesize the entire discussion, resolve any disagreements to reach a single consensus, and fill out the expected structured response format."
        f"Do not add any additional information beyond what is provided in the opinions of the experts."
        f"Do not hallucinate any information that is not present in the opinions of the experts."
    )

    try:
        datas = json.loads(
            coordinator.ask(
                synthesis_prompt, output_format, callbacks=callbacks
            ).model_dump_json()
        )
        if isinstance(datas, dict):
            datas["reasoning_thinking"] = getattr(coordinator, "latest_thinking", None)
        return datas
    except Exception as e:
        logger.error(f"Error during debate synthesis: {e}")
        raise e
    finally:
        del coordinator
        gc.collect()
