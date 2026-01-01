import json

from typing import ClassVar
from pydantic import ValidationError

from langchain.agents import create_agent

from src.application.config import AppConfig
from src.application.tools import timed
from src.infrastructure.llm.ollama import OllamaConnect
from src.application.reader import DocumentReader
from src.application.agent.tools import search_on_mtd, search_on_ressources, Context
from langchain.agents.structured_output import ToolStrategy


class OncowflowAgent:
    model: ClassVar[str] = None
    system_prompt: ClassVar[str] = ""
    question: ClassVar[str] = "Nothing"
    models: ClassVar[list[str]] = None
    ressources: ClassVar[str] = []

    def __init__(
        self,
        config: AppConfig,
        mtd: DocumentReader,
        output_format: any = None,
    ):
        self.output_format = output_format

        if config.llm.type.lower() == "ollama":
            llm_client = OllamaConnect(config)
        else:
            raise ValueError(f"{config.llm.type} not yet supported")

        if self.models is None:
            list_models = config.llm.models.split(",")
        else:
            list_models = self.models

        self.agent = create_agent(
            model=llm_client.chat(list_models[0], output=output_format),
            tools=[search_on_mtd, search_on_ressources],
            # middleware=[self.dynamic_model_selection],
            # response_format=ToolStrategy(
            #     schema=output_format, handle_errors=True
            # ),
            context_schema=Context,
            system_prompt=self.system_prompt,
        )

        self.reader = mtd
        self.additionnal_readers = [
            DocumentReader(config, ressource, document_type="ressource")
            for ressource in self.ressources
        ]

        self.logger = config.set_logger(
            "OncowAgent",
            default_context={
                "model": list_models[0],
                "system_prompt": self.system_prompt,
                "output_format": self.output_format,
            },
        )
        self.logger.info("Agent succefully created")

    def ask(self, question: str = None, structuredResponse: bool = True) -> dict:
        self.logger.info('Ask "%s" to agent ...', question)

        if question is None:
            question = self.question

        result = self.agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            context=Context(
                reader=self.reader, additionnal_readers=self.additionnal_readers
            ),
        )
        for msg in result["messages"]:
            try:
                if type(msg).__name__ == "AIMessage":
                    self.logger.info(f"AI response : {result['messages']}")
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
