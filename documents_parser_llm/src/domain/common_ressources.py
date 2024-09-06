from enum import Enum
from datetime import date

from typing import List, Optional, ClassVar

from langchain_core.pydantic_v1 import BaseModel, Field, PastDate

class RadiologicExamType(str, Enum):
    CT = 'CT'
    MRI = 'MRI'
    PET = 'PET'


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    not_given = "not_given"
    
class LabTestEnum(str, Enum):
    bilirubin = "bilirubin"
    ca19_9 = "Ca19-9"
    ace = "ACE"
    
class LabTest(BaseModel):
    lab_type: LabTestEnum = Field(description="Type of laboratory test")
    value: float
    date: Optional[PastDate] = Field(description="Date of the lab test")


class RevealingMode(str, Enum):
    '''
    This class lists the ways in which the tumor can be revealed 
    '''
    symptoms = 'symptoms'
    incidental_radiologic = 'incidental radiologic finding'
    incidental_biologic = 'incidental biologic finding'
    follow_up = 'follow up'
    unknown = 'unknown'


class MetastaticLocationsEnum(str, Enum):
    '''
    This class lists possible metastatic sites
    '''
    liver = 'liver'
    lung = 'lung'
    peritoneal = 'peritoneal'
    bone = 'bone'
    brain = 'brain'
    other = 'other'


class WHOPerformanceStatus(int, Enum):
    _0 = 0
    _1 = 1
    _2 = 2
    _3 = 3
    _4 = 4

    @classmethod
    def labels(cls) -> dict:
        return {
            cls._0: "No limitation of activities (none)",
            cls._1: "Limitation in strenuous activities, but able to do light work or other activities",
            cls._2: "Considerable limitation in activities; some assistance occasionally needed",
            cls._3: "Severe limitation in activities; frequent assistance required",
            cls._4: "Complete limitation of activities; unable to perform any activity"
        }


class PrimaryOrganEnum(str, Enum):

    pancreas = 'Pancreas'
    colon = "Colon "
    liver = "Liver"
    stomach = "Stomach"
    oesophagus = "Oesophagus"
    rectum = "Rectum"
    intra_hepatic_bile_duct = "Intra-hepatic bile duct"
    extra_hepatic_bile_duct = "Extra-hepatic bile duct"
    unknown = "unknown"


class TNCDCancerTypesEnum(str, Enum):

    ampulloma = 'tumor of the ampulla of Vater'
    localized_colon_cancer = 'localized colon cancer, without distant metastasis'
    metastatic_colorectal = 'metastatic colorectal cancer'
    rectum = 'rectal cancer'
    anal_canal = 'anal canal cancer'
    liverhcc = 'hepatocellular carcinoma (primary liver cancer)'
    biliary_tract = 'biliary tract cancer'
    pancreas = 'pancreatic cancer'
    gastric = 'gastric cancer'
    oesophagus_junction = 'oesophagus and esophagogastric junction cancer'
    unknown = 'unknown cancer type'


class CancerTypesEnum(str, Enum):

    colorectal_cancer = 'rectum and colon primitive cancer'
    liver_primary_cancer = 'hepatocellular carcinoma (primary liver cancer)'
    biliary_tract_cancer = 'biliary tract cancer'
    pancreatic_cancer = 'pancreatic cancer'
    gastric_cancer = 'gastric cancer'
    oesophagus_junction_cancer = 'oesophagus and esophagogastric junction cancer'
    unknown = 'unknown cancer type'


class TreatmentEnum(str, Enum):

    surgery = "Surgery"
    chemotherapy = "Chemotherapy"
    radiotherapy = "Radiotherapy"
    immunotherapy = "Immunotherapy"


class TreatmentStatusEnum(str, Enum):

    curative = "Curative"
    palliative = "Palliative"
    adjuvant = "Adjuvant"
    neo_adjuvant = "Neo-adjuvant"


class TreatmentToleranceEnum(str, Enum):
    good = "Good"
    medium = "Medium"
    poor = "Poor"
    not_given = "Not given"


class ChemotherapyData(BaseModel):

    chemotherapy_name: str = Field(description="Name of the chemotherapy")
    chemotherapy_start_date: Optional[date] = Field(
        description="Date of the beginning of the chemotherapy")
    chemotherapy_end_date: Optional[date] = Field(
        description="Date of the end of the chemotherapy")
    chemotherapy_tolerance: TreatmentToleranceEnum = Field(
        description="Tolerance of the chemotherapy")

# class CurativeSurgery(BaseModel):

#     surgery_date: date = Field(description="Date of the surgery")
#     surgeon_name: Optional[str] = Field(description="Name of the surgeon")
#     surgery_name: Optional[str] = Field(description="Name of the surgery")


class PreviousTreatmentData(BaseModel):

    treatment_date: PastDate = Field(deacription="Date of the treatment")
    treatment_name: TreatmentEnum = Field(description="Name of the treatment")
    treatment_status: TreatmentStatusEnum = Field(
        description="Status of the treatment on the deasise")


# class CurativeSurgery(BaseModel):

#     surgery_date: date = Field(description="Date of the surgery")
#     surgeon_name: Optional[str] = Field(description="Name of the surgeon")
#     surgery_name: Optional[str] = Field(description="Name of the surgery")


class PancreaticTumorEnum(str, Enum):
    adenocarcinoma = 'adenocarcinoma'
    neuroendocrin = 'neuroendocrine tumor'
    unknown = 'unknow'


class PancreaticSymptomsEnum(str, Enum):
    pain = 'pain'
    jaundice = 'jaundice'
    mass = 'mass'
    weight_loss = 'weight loss'


class LiverSymptomsEnum(str, Enum):
    ascite = 'ascite'
    jaundice = 'jaundice'
    digestive_bleeding = 'digestive bleeding'
    encephalopathy = 'encephalopathy'


class ChildPugh(BaseModel):
    """
    Evaluation of the Child-Pugh score.

    Attributes:
        bilirubine: Bilirubin level in blood.
        albumine: Albumin level in blood.
        prothrombine: Prothrombin time.
        ascite: Presence of ascites.
        encephalopathie: Presence of encephalopathy.

    Examples:
        >>> child_pugh = ChildPugh(
                bilirubine=2,
                albumine=3,
                prothrombine=50,
                ascite=False,
                encephalopathie=False
            )
    """
 
    bilirubin: int = Field(description="Bilirubin level in blood")
    albumine: int = Field(description="Albumin level in blood")
    prothrombine: int = Field(description="Prothrombin time")
    ascite: bool = Field(description="Presence of ascites")
    encephalopathie: bool = Field(description="Presence of encephalopathy")

    question: ClassVar[str] = "Tell me the Child-Pugh score."


class RadiologicalExamination(BaseModel):
    '''
    This class contains all possible informations about one imagery exam
    '''
    exam_name: str = Field(description="The name of the radiological exam")
    exam_date: date = Field(
        description="The date when the radiological examination was performed.")
    exam_type: RadiologicExamType = Field(
        description="The type of radiological examination performed (e.g., CT, MRI, X-ray).")
    exam_result: Optional[str] = Field(
        description='Result of the radiological exam')

class HistologicStateEnum(str,Enum):
    
    suspected = 'Suspected'
    histologicaly_proven = 'Histologicaly proven'
    unknown = 'Unknown'
    
class HistologicAnalysis(BaseModel):
    '''
    This class contains all informations related to a histological analysis.

    Attributes:
        date (datetime): Date when the biopsy or resection was performed.
        contributive (bool): Indicator of the importance of the results (conclusive or not).
        result (str): Complete result of the histological analysis.

    Examples:
        >>> analysis = HistologicAnalysis(
                date=datetime.date(2022, 1, 1),
                contributive=True,
                result="Result of a detailed histological analysis"
            )
    '''
    histology_date: date = Field(description="Date of biopsy or resection")
    contributive: bool = Field(
        description="Importance of results (conclusive or not)")
    result: str = Field(
        description='Complete result of the histological analysis')


class RadiologicalExaminations(BaseModel):
    """
    A container for a patient's radiology studies.

    Attributes:
        exams_all (list[RadiologicalExamination]): All of the patient's radiology studies.
        ct_scans (list[RadiologicalExamination]): The patient's computed tomography (CT) scans.
        mri_studies (list[RadiologicalExamination]): The patient's magnetic resonance imaging (MRI) studies.
        pet_scans (list[RadiologicalExamination]): The patient's positron emission tomography (PET) scans.

    Examples:
        >>> exams = RadiologicalExaminations(
                exams_all=[RadiologicalExamination(...)],
                ct_scans=[RadiologicalExamination(...)],
                mri_studies=[RadiologicalExamination(...)],
                pet_scans=[RadiologicalExamination(...)]
            )
    """
    exams_all: list[RadiologicalExamination] = Field(
        "All of the patient's radiology studies")
    ct_scans: list[RadiologicalExamination] = Field(
        "The patient's computed tomography (CT) scans")
    mri_studies: list[RadiologicalExamination] = Field(
        "The patient's magnetic resonance imaging (MRI) studies")
    pet_scans: list[RadiologicalExamination] = Field(
        "The patient's positron emission tomography (PET) scans")