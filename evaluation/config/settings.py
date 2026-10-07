"""Configuration BaseSettings pour le module d'évaluation Oncoflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
import yaml


class BaseEvalSettings(BaseSettings):
    """Classe de base assurant la priorité ENV > YAML/init pour les réglages d'évaluation."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return env_settings, init_settings, dotenv_settings, file_secret_settings


class MLflowEvalSettings(BaseEvalSettings):
    """Configuration du serveur MLflow et du tracking des évaluations.

    Variables d'environnement :
    - MLFLOW_TRACKING_URI
    - MLFLOW_EXPERIMENT_NAME
    """

    model_config = SettingsConfigDict(
        env_prefix="MLFLOW_",
        extra="ignore",
    )

    tracking_uri: str = Field(
        default="http://localhost:5000",
        description="URI du serveur MLflow de tracking",
    )
    experiment_name: str = Field(
        default="oncoflow-agents-evaluation",
        description="Nom de l'expérience MLflow pour stocker les évaluations",
    )


class JudgeSettings(BaseEvalSettings):
    """Configuration du LLM-as-a-Judge frontalier (MLflow AI Gateway / OpenAI-compatible).

    Variables d'environnement :
    - JUDGE_PROVIDER
    - JUDGE_BASE_URL
    - JUDGE_API_KEY
    - JUDGE_MODEL
    - JUDGE_TEMPERATURE
    - JUDGE_MAX_TOKENS
    - JUDGE_TIMEOUT
    """

    model_config = SettingsConfigDict(
        env_prefix="JUDGE_",
        extra="ignore",
    )

    provider: str = Field(
        default="mlflow",
        description="Provider du juge (ex: mlflow, openai)",
    )
    base_url: str = Field(
        default="http://127.0.0.1:5000/gateway/mlflow/v1",
        description="Base URL de l'API OpenAI compatible (MLflow AI Gateway)",
    )
    api_key: str = Field(
        default="not-needed",
        description="Clé d'API du client vers le proxy/gateway",
    )
    model: str = Field(
        default="oncoflow-evaluation",
        description="Nom du modèle ou de l'endpoint Gateway (ex: oncoflow-evaluation, gemini-3.8-flash)",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Température du juge (0.0 pour une évaluation déterministe)",
    )
    max_tokens: int = Field(
        default=4096,
        description="Nombre maximum de tokens générés par le juge",
    )
    timeout: int = Field(
        default=120,
        description="Timeout des requêtes en secondes",
    )
    max_retries: int = Field(
        default=5,
        description="Nombre maximum de tentatives de réessai en cas d'erreur 503/429 ou surcharge temporaire",
    )
    retry_delay: float = Field(
        default=2.0,
        description="Délai initial de backoff en secondes pour les réessais du juge",
    )
    retry_backoff: float = Field(
        default=2.0,
        description="Facteur multiplicateur de backoff exponentiel pour les réessais",
    )


class EvalExecutionSettings(BaseEvalSettings):
    """Options de contrôle des exécutions d'évaluation.

    Variables d'environnement :
    - EVAL_DEFAULT_DOMAIN
    - EVAL_DEFAULT_MODE
    - EVAL_MAX_RETRIES
    - EVAL_BATCH_SIZE
    - EVAL_SAVE_PROMPT_SUGGESTIONS
    - EVAL_EXPORT_MARKDOWN_REPORTS
    """

    model_config = SettingsConfigDict(
        env_prefix="EVAL_",
        extra="ignore",
    )

    default_domain: str = Field(
        default="oncology",
        description="Domaine médical par défaut (oncology, sma)",
    )
    default_mode: str = Field(
        default="auto",
        description="Mode d'exécution par défaut (auto, debate, single_agent)",
    )
    max_retries: int = Field(
        default=3,
        description="Tentatives maximales de validation Pydantic",
    )
    batch_size: int = Field(
        default=1,
        description="Taille de batch pour l'évaluation",
    )
    save_prompt_suggestions: bool = Field(
        default=True,
        description="Sauvegarder les propositions de prompts révisés",
    )
    export_markdown_reports: bool = Field(
        default=True,
        description="Exporter les synthèses en Markdown",
    )
    target_class: str | None = Field(
        default=None,
        description="Nom de la classe de formulaire Pydantic à évaluer spécifiquement (ex: PatientAdministrative, RadiologicExams, RadiologicExamType)",
    )


class EvaluationSettings(BaseSettings):
    """Configuration unifiée pour l'évaluation Oncoflow."""

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    mlflow: MLflowEvalSettings = Field(default_factory=MLflowEvalSettings)
    judge: JudgeSettings = Field(default_factory=JudgeSettings)
    execution: EvalExecutionSettings = Field(default_factory=EvalExecutionSettings)

    @classmethod
    def from_yaml(cls, path: Path | str | None = None) -> EvaluationSettings:
        """Charge la configuration depuis un fichier YAML avec surcharge automatique par BaseSettings (ENV)."""
        yaml_data: dict[str, Any] = {}
        config_file = (
            Path(path)
            if path
            else Path(__file__).resolve().parent.parent / "config/eval_config.yaml"
        )

        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    yaml_data = loaded

        mlflow_data = dict(yaml_data.get("mlflow") or {})
        judge_data = dict(yaml_data.get("judge") or {})
        onco_data = yaml_data.get("oncoflow") or {}
        eval_data = yaml_data.get("evaluation") or {}
        exec_data = {**onco_data, **eval_data}

        return cls(
            mlflow=MLflowEvalSettings(**mlflow_data),
            judge=JudgeSettings(**judge_data),
            execution=EvalExecutionSettings(**exec_data),
        )
