"""
Simple review questions asked on an RCP (MDT) record, before the meeting.

Each model below answers one question of the RCP secretary / surgeon:
    - SurgicalResectionDiscussion : must the record be discussed for a surgical resection?
    - MissingDataForResection     : are data missing to discuss the surgical resection?
    - RecordInconsistencies       : does the RCP form contain internal inconsistencies?
    - AnnexDiscordance            : are the annex documents discordant with the RCP form?

They are asked by `RCPReviewerAgent`, which reads the whole record (RCP form + annexes)
with the `get_mtd_markdown` tool and does not need any vector database.
"""

from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, Field

from src.application.agent.agent import OncowflowAgent


class ResectabilityStatus(str, Enum):
    resectable = "resectable"
    borderline = "borderline"
    locally_advanced = "locally_advanced"
    metastatic = "metastatic"
    non_resectable = "non_resectable"
    unknown = "unknown"


class RCPReviewQuestion(BaseModel):
    question: ClassVar[str] = ""


class SurgicalResectionDiscussion(RCPReviewQuestion):
    """
    Must the record be discussed for a surgical resection?
    """

    discuss_resection: bool = Field(
        description="True if a surgical resection of the tumor must be discussed during this RCP"
    )
    resectability: ResectabilityStatus = Field(
        description="Resectability status of the tumor according to the record"
    )
    justification: str = Field(
        description="Clinical justification based on the elements of the record"
    )

    question: ClassVar[str] = """
        Read the whole patient record (RCP form and annex documents).
        Must this record be discussed in RCP for a surgical resection of the tumor?
        Give the resectability status of the tumor (resectable, borderline, locally_advanced,
        metastatic, non_resectable, or unknown if the staging does not allow to conclude).
        A metastatic disease or a patient unfit for surgery does not justify a resection discussion.
        Justify your answer with the elements of the record.
        """


class MissingItem(BaseModel):
    item: str = Field(description="Missing data or document")
    why_needed: str = Field(
        description="Why this element is needed to discuss the surgical resection"
    )


class MissingDataForResection(RCPReviewQuestion):
    """
    Are data missing to discuss the surgical resection?
    """

    data_missing: bool = Field(
        description="True if data required to discuss a surgical resection are missing"
    )
    missing_items: list[MissingItem] = Field(
        default=[], description="List of missing elements, empty if nothing is missing"
    )

    question: ClassVar[str] = """
        Read the whole patient record (RCP form and annex documents).
        Are there missing data to discuss a surgical resection of the tumor?
        Check at least: histological proof, complete staging imaging (thorax, abdomen, pelvis),
        tumor markers relevant for the organ, WHO performance status, and the relation
        between the tumor and vessels when relevant.
        Only report elements that are really absent from the record.
        If the disease is metastatic and no resection is discussed, nothing is missing for resection.
        """


class Inconsistency(BaseModel):
    field: str = Field(description="Data concerned by the inconsistency (e.g. age)")
    description: str = Field(
        description="Description of the inconsistency, quoting both contradictory values"
    )


class RecordInconsistencies(RCPReviewQuestion):
    """
    Does the RCP form contain internal inconsistencies?
    """

    has_inconsistencies: bool = Field(
        description="True if the RCP form contains contradictory information"
    )
    inconsistencies: list[Inconsistency] = Field(
        default=[], description="List of inconsistencies, empty if none"
    )

    question: ClassVar[str] = """
        Read the RCP form of the patient record.
        Does the RCP form contain internal inconsistencies, i.e. contradictory information
        inside the form itself (age versus date of birth, gender, histology, WHO performance status,
        TNM staging, dates, laterality, organ...)?
        Do not report differences between the RCP form and the annex documents here.
        """


class Discordance(BaseModel):
    document: str = Field(description="Annex document concerned")
    rcp_form_value: str = Field(description="Information given by the RCP form")
    annex_value: str = Field(description="Information given by the annex document")
    clinical_impact: str = Field(
        description="Impact of the discordance on the therapeutic decision"
    )


class AnnexDiscordance(RCPReviewQuestion):
    """
    Are the annex documents discordant with the RCP form?
    """

    has_discordance: bool = Field(
        description="True if at least one annex document contradicts the RCP form"
    )
    discordances: list[Discordance] = Field(
        default=[], description="List of discordances, empty if none"
    )

    question: ClassVar[str] = """
        Read the whole patient record: the RCP form and each annex document
        (imaging reports, pathology reports, biology...).
        Is any annex document discordant with the content of the RCP form
        (number or size of lesions, vascular involvement, histology, biology, scores...)?
        For each discordance, quote the value of the RCP form and the value of the annex document,
        and explain its impact on the therapeutic decision.
        """


RCP_REVIEW_QUESTIONS: dict[str, type[RCPReviewQuestion]] = {
    model.__name__: model
    for model in (
        SurgicalResectionDiscussion,
        MissingDataForResection,
        RecordInconsistencies,
        AnnexDiscordance,
    )
}


class RCPReviewerAgent(OncowflowAgent):
    agent_name: str = "RCP reviewer"
    system_prompt: ClassVar[str] = """
    You are a digestive oncology surgeon preparing a multidisciplinary team meeting (RCP).
    Your goal is to review a patient record before the meeting.

    Instructions:
    1. Use the `get_mtd_markdown` tool to read the whole patient record. It contains the RCP form
       followed by the annex documents, each one introduced by a "Document annexe" title.
    2. Answer the user's question strictly using the information of the record.
    3. Do not invent data. If an information is absent, consider it as missing.
    4. Respect strictly the response output format.
    """
