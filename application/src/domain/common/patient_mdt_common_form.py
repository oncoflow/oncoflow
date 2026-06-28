import inspect
import json
import os

from typing import Optional, ClassVar
from datetime import datetime

from pydantic import BaseModel, Field, PastDatetime, model_validator

from src.domain.common.common_ressources import *  # noqa: F403

from src.application.config import AppConfig
from src.application.agent.agent import OncowflowAgent
from src.application.reader import DocumentReader
from src.infrastructure.documents.mongodb import Mongodb
from src.application.agent.collaborate import collaborative_debate
from src.domain.common.agents import Agents as Agents


class PatientMDTForm(DocumentReader):
    """
    This class contains all patient and oncological disease information for the report.
    """

    mtd_datas: dict = {}
    mtd_datas_json: dict = {}
    db_client: Mongodb

    def __init__(self, config: AppConfig, document: str) -> None:
        super(PatientMDTForm, self).__init__(config=config, document=document)

        self.mtd_datas["file"] = document
        self.mtd_datas["execution_times"] = {}

        self.basemodel_list = [
            cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute)
            and issubclass(cls_attribute, self.default_model)
            and cls_attribute.__name__ != "default_model"
        ]

        self.read_document()

        self.db_client = None
        if config.rcp.display_type == "mongodb":
            self.db_client = Mongodb(config)
        else:
            self.logger.info(
                "DB Type %s not known, fallback to stdout", config.rcp.display_type
            )

        if self.db_client is not None:
            self.db_client.set_uniq_index(collection="rcp_info", field="file")
            db_document = self.db_client.get_or_create_document(
                collection="rcp_info", document={"file": document}
            )
            if db_document is not None:
                self.mtd_datas["id"] = db_document.get("_id")
                if "execution_times" in db_document:
                    self.mtd_datas["execution_times"] = db_document["execution_times"]
                self.dict_to_models(db_document)
            else:
                self.logger.warning(
                    "No database document found or created for %s", document
                )
                self.mtd_datas["id"] = None
        else:
            self.mtd_datas["id"] = None

    def dict_to_models(self, dic: dict, subkey=None):
        for key, value in dic.items():
            for m in self.basemodel_list:
                if m.__name__ == key:
                    if len(m.agents) > 1 and not getattr(m, "collaborative", False):
                        for a in m.agents:
                            if isinstance(value, dict) and a.agent_name in value:
                                self.mtd_datas[key] = {
                                    a.agent_name: m.model_validate(value[a.agent_name])
                                }
                    else:
                        if (
                            getattr(m, "collaborative", False)
                            and len(m.agents) > 1
                            and isinstance(value, dict)
                        ):
                            # Backward compatibility: extract nested data if saved in old agent-keyed format
                            has_any_field = any(
                                field in value for field in m.model_fields
                            )
                            if not has_any_field:
                                for a in m.agents:
                                    if a.agent_name in value:
                                        value = value[a.agent_name]
                                        break
                        self.mtd_datas[key] = m.model_validate(value)

    def read_all_models(self) -> dict:
        for model in self.basemodel_list:
            self.read_model(model)
        return self.mtd_datas

    def read_model(
        self,
        model: "type[PatientMDTForm.default_model]",
        upsert: bool = False,
        callbacks: list | None = None,
    ):
        import time

        if upsert and self.config.rcp.display_type == "mongodb":
            self.db_client = Mongodb(self.config)

        start_time = time.time()

        if getattr(model, "collaborative", False) and len(model.agents) > 1:
            datas = collaborative_debate(
                agents_classes=model.agents,
                question=model.question,
                output_format=model,
                config=self.config,
                mtd=self,
                logger=self.logger,
                callbacks=callbacks,
            )
            self.mtd_datas[model.__name__] = datas
        else:
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
                datas = json.loads(a.ask(model.question, callbacks=callbacks).json())
                self.logger.debug(f"DATAS : {datas} ...")
                if datas:
                    if isinstance(datas, dict):
                        datas["reasoning_thinking"] = getattr(
                            a, "latest_thinking", None
                        )
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

        duration = time.time() - start_time
        if "execution_times" not in self.mtd_datas:
            self.mtd_datas["execution_times"] = {}
        self.mtd_datas["execution_times"][model.__name__] = duration

        if upsert and self.db_client is not None:
            self.logger.debug(
                f"Document final inserted: {json.dumps(self.mtd_datas, default=str)}"
            )
            self.db_client.update_doc(
                collection="rcp_info",
                filter={"file": self.mtd_datas["file"]},
                upsertable_data={
                    model.__name__: self.mtd_datas[model.__name__],
                    "execution_times": self.mtd_datas["execution_times"],
                },
            )
            self.db_client.close()
            self.db_client = None

    def delete(self):
        if self.db_client is not None:
            self.db_client.delete_docs(
                collections=["rcp_info", "rcp_metadata"],
                filter={"file": self.mtd_datas["file"]},
            )
        if os.path.exists(self.document_path):
            os.remove(self.document_path)
        if self.db_client is not None:
            self.db_client.close()
            self.db_client = None

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
            self.db_client = None

    @classmethod
    def parse_raw(cls, value):
        if isinstance(value, dict):
            return cls(**value)
        elif isinstance(value, str):
            return cls.parse_raw(json.loads(value))
        else:
            raise ValueError("Invalid input")

    class default_model(BaseModel):
        question: ClassVar[str] = ""
        agents: ClassVar[list[type[OncowflowAgent]]] = [Agents.Administratives_agent]
        agents_memory: ClassVar[bool] = False
        collaborative: ClassVar[bool] = False
        collaborative_agent: ClassVar[type[OncowflowAgent] | None] = None
        reasoning_thinking: ClassVar[str | None] = None
        time_execution: ClassVar[int | None] = None

    #  // // // // // Tested and Working classes // // // // //

    class PatientAdministrative(default_model):
        """
        Patient administrative informations
        """

        first_name: str = Field(description="First name of the patient")
        last_name: str = Field(description="Last name of the patient")
        born_name: Optional[str] = Field(
            description="Name of the patient at birth", default=None
        )

        age: int = Field(description="Age of the patient")
        date_birth: Optional[PastDatetime] = Field(
            description="Date of birth of the patient (Format: YYYY-MM-DD)"
        )
        date_rcp: Optional[datetime] = Field(
            description="Date of the MTD (Format: YYYY-MM-DD)"
        )
        gender: Gender = Field(description="Gender of the patient")  # noqa: F405

        @model_validator(mode="after")
        def check_dates_coherence(self):
            now = datetime.now()
            if self.date_birth and self.date_birth.year < (now.year - 150):
                self.date_birth = None

            if self.date_rcp and self.date_rcp.year < (now.year - 5):
                self.date_rcp = None

            if self.date_birth and self.date_rcp:
                if self.date_birth.replace(tzinfo=None) > self.date_rcp.replace(
                    tzinfo=None
                ):
                    raise ValueError("Date of birth must be before Date of RCP")
            return self

        question: ClassVar[
            str
        ] = """Search and Extract the patient's administrative details from MTD.
            1. Find the patient's First Name, Last Name, Age AND Date of birth. Note that age is often written as 'XX ans'. If age is missing but Date of birth is present, you can deduce the age based on the Date of RCP.
            2. Find the date of the MTD (RCP).
            3. Find the gender of the patient.
            If a value is not found, state it clearly.
            You can use tools multiple time for each element.
            Format all dates strictly as YYYY-MM-DD (e.g. 1956-06-04).
            Ensure dates are coherent:
            1. Date of birth must be less than 150 years ago.
            2. Date of RCP must be less than 5 years ago.
            3. Date of birth must be strictly before Date of RCP.
            """

    class MTDCompleted(default_model):
        agents: ClassVar[list[type[OncowflowAgent]]] = Agents().expert_agents
        mtd_complete: MTDComplete = Field(description="Is the MDT file complete?")  # noqa: F405

        collaborative = True

        question: ClassVar[str] = """
            As an expert, determine if the MDT (Multidisciplinary Team) file is complete.
            Are there missing elements required for a treatment decision?
            You can use search_on_ressources tool what type of elements/documents is needed.
            You can use tools multiple times for each element
            """
