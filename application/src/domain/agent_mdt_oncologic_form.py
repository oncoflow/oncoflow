from src.application.agent import OncowflowAgent
from src.application.config import AppConfig
from src.application.reader import DocumentReader


class AgentsMDTOncologicForm:

    agents = dict[str, OncowflowAgent]
    
    def __init__(self, reader: DocumentReader, config=AppConfig,):
        self.logger = config.set_logger(
                "AgentsMDTOncologicForm"
            )
        self.reader = reader
        self.config = config
        

    def administrativeAgent(self):
        if "administrativeAgent" not in self.agents:
            agents["administrativeAgent"] = OncowflowAgent(self.reader, self.config)

    