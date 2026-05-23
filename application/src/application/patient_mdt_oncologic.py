import inspect
import json
import os

from src.domain.common_ressources import *  # noqa: F403

from pydantic import BaseModel
from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.infrastructure.documents.mongodb import Mongodb


class PatientMDTOncologic(DocumentReader):
    """
    This class contains all patient and oncological disease information for the report.
    """

    mtd_datas: dict = {}
    mtd_datas_json: dict = {}
    db_client = None

    def __init__(self, config: AppConfig, document: str) -> None:
        super(PatientMDTOncologic, self).__init__(config=config, document=document)

        self.mtd_datas["file"] = document

        self.basemodel_list = [
            cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute)
            and issubclass(cls_attribute, self.default_model)
            and cls_attribute.__name__ != "default_model"
        ]

        self.read_document()

        if config.rcp.display_type == "mongodb":
            self.db_client = Mongodb(config)
        else:
            self.logger.info(
                "DB Type %s not known, fallback to stdout", config.rcp.display_type
            )

        self.db_client.set_uniq_index(collection="rcp_info", field="file")
        db_document = self.db_client.get_or_create_document(
            collection="rcp_info", document={"file": document}
        )
        self.mtd_datas["id"] = db_document["_id"]
        self.dict_to_models(db_document)

    def dict_to_models(self, dic: dict, subkey=None):
        for key, value in dic.items():
            for m in self.basemodel_list:
                if m.__name__ == key:
                    if len(m.agents) > 1:
                        agent_names = [a.agent_name for a in m.agents]
                        is_old_format = any(aname in value for aname in agent_names)

                        if is_old_format:
                            self.mtd_datas[key] = {}
                            for a in m.agents:
                                if a.agent_name in value:
                                    self.mtd_datas[key][a.agent_name] = (
                                        m.model_validate(value[a.agent_name])
                                    )
                        else:
                            # Format Synthesizer plat
                            self.mtd_datas[key] = m.model_validate(value)
                    else:
                        self.mtd_datas[key] = m.model_validate(value)

    def read_all_models(self) -> dict:
        for model in self.basemodel_list:
            self.read_model(model)
        return self.mtd_datas

    def read_model(self, model: BaseModel, upsert: bool = False):
        if getattr(model, "multi_agent_reflection", False):
            if upsert:
                self.db_client = Mongodb(self.config)

            from src.application.agent.reflection_graph import run_reflection_graph

            final_datas = run_reflection_graph(
                config=self.config, mtd=self, model=model, logger=self.logger
            )

            if final_datas:
                self.mtd_datas[model.__name__] = final_datas

            if upsert:
                self.logger.info(self.mtd_datas)
                self.db_client.update_doc(
                    collection="rcp_info",
                    filter={"file": self.mtd_datas["file"]},
                    upsertable_data={
                        model.__name__: self.mtd_datas.get(model.__name__, {})
                    },
                )
                self.db_client.close()
            return

        if upsert:
            self.db_client = Mongodb(self.config)
        agents = [
            magent(config=self.config, mtd=self, output_format=model)
            for magent in model.agents
        ]
        memory = {}
        for a in agents:
            if memory and model.agents_memory:
                model.question = f"""
                Agents memory datas :
                {memory}
                {model.question}
                """
            datas = json.loads(a.ask(model.question).json())
            self.logger.debug(f"DATAS : {datas} ...")
            if datas:
                if model.agents_memory:
                    memory = memory | datas
                if model.__name__ not in self.mtd_datas:
                    self.mtd_datas[model.__name__] = {}
                if len(agents) > 1:
                    self.mtd_datas[model.__name__][a.agent_name] = datas
                else:
                    self.mtd_datas[model.__name__] = datas
            del a
        del agents
        if upsert:
            self.logger.info(self.mtd_datas)
            self.db_client.update_doc(
                collection="rcp_info",
                filter={"file": self.mtd_datas["file"]},
                upsertable_data={model.__name__: self.mtd_datas[model.__name__]},
            )
            self.db_client.close()

    def delete(self):
        self.db_clientclient.delete_docs(
            collections=["rcp_info", "rcp_metadata"],
            filter={"file": self.mtd_datas["file"]},
        )
        if os.path.exists(self.document_path):
            os.remove(self.document_path)
        self.db_client.close()

    def insert_datas_in_db(self, replace: bool = True):
        if self.db_client is not None:
            if replace:
                self.db_client.delete_docs(
                    collections=["rcp_info", "rcp_metadata"],
                    filter={"file": self.mtd_datas["file"]},
                )
            self.db_client.prepare_insert_doc(
                collection="rcp_info", document=self.mtd_datas
            )
            self.db_client.insert_docs()
            self.db_client.close()

    @classmethod
    def parse_raw(cls, value):
        if isinstance(value, dict):
            return cls(**value)
        elif isinstance(value, str):
            return cls.parse_raw(json.loads(value))
        else:
            raise ValueError("Invalid input")
