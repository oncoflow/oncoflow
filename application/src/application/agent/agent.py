import json

from pydantic import ValidationError

from langchain.agents import create_agent

from src.application.config import AppConfig
from src.application.tools import timed
from src.infrastructure.llm.ollama import OllamaConnect
from src.application.reader import DocumentReader
from src.application.agent.tools import search_on_mtd, search_on_ressources, Context
from langchain.agents.structured_output import ToolStrategy


class OncowflowAgent:
    model: str

    def __init__(
        self,
        models: list[str],
        reader: DocumentReader,
        config: AppConfig,
        output_format: any = None,
        system_prompt: str = None,
    ):
        self.reader = reader
        self.output_format = output_format

        if config.llm.type.lower() == "ollama":
            llm_client = OllamaConnect(config)
        else:
            raise ValueError(f"{config.llm.type} not yet supported")

        if models is None or not models:
            list_models = config.llm.models.split(",")
        else:
            list_models = models

        self.agent = create_agent(
            model=llm_client.chat(list_models[0], output=output_format),
            tools=[search_on_mtd, search_on_ressources],
            # middleware=[self.dynamic_model_selection],
            # response_format=ToolStrategy(
            #     schema=output_format, handle_errors=True
            # ),
            context_schema=Context,
            system_prompt=system_prompt,
        )

        self.logger = config.set_logger(
            "OncowAgent",
            default_context={
                "model": list_models[0],
                "system_prompt": system_prompt,
                "output_format": output_format,
            },
        )
        self.logger.info("Agent succefully created")

    def ask(self, question, structuredResponse: bool = True) -> dict:
        self.logger.info('Ask "%s" to agent ...', question)

        result = self.agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            context=Context(reader=self.reader),
        )
        for msg in result["messages"]:
            try:
                if type(msg).__name__ == "AIMessage":
                    self.output_format.model_validate_json(msg.content)
                    return json.loads(msg.content)
            except ValidationError:
                continue

        # for msg in result['messages']:
        #     if type(msg).__name__ == "ToolMessage":
        #         return msg.content
        #     elif isinstance(msg, dict) and msg.get('tool_call_id'):
        #         return msg['content']
        raise ValueError(f"AI response {result['messages']}")
