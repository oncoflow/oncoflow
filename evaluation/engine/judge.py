"""Client LLM-as-a-Judge utilisant LiteLLM avec sensibilisation aux limitations des SLM locaux (7B-14B)."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import yaml
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, Field

from evaluation.config.settings import EvaluationSettings

logger = logging.getLogger("OncoflowEval.Judge")


class MetricScore(BaseModel):
    score: int = Field(ge=1, le=5, description="Note de 1 a 5 sur le critere")
    justification: str = Field(
        description="Explication clinique ou technique de la note"
    )


class PromptOptimization(BaseModel):
    slm_failure_diagnostics: str = Field(
        description="Diagnostic du point de rupture cognitive du modele 7B-14B quantifie."
    )
    suggested_prompt: str = Field(
        description="Version complete du prompt revise, optimise pour les modeles 7B-14B Q4."
    )
    slm_optimizations_applied: list[str] = Field(
        description="Liste des ajustements adaptes aux SLM (directives positives, delimiteurs, concision, etc.)."
    )
    expected_gain: str = Field(
        description="Amelioration clinique ou syntaxique attendue sur le modele local."
    )


class JudgeEvaluation(BaseModel):
    domain: str
    agent_name: str
    evaluated_case_id: str
    scores: dict[str, MetricScore]
    identified_hallucinations: list[str] = Field(
        default_factory=list,
        description="Faits cliniques affirmes par l'agent mais absents du MTD.",
    )
    identified_missing_data_errors: list[str] = Field(
        default_factory=list,
        description="Donnees manquantes non signalees dans what_missing.",
    )
    prompt_optimization: PromptOptimization | None = None
    overall_clinical_summary: str = Field(
        description="Synthese de qualite globale de l'extraction."
    )


class LLMJudge:
    """Juge frontière pilote via LiteLLM pour evaluer les agents Oncoflow."""

    def __init__(
        self,
        config_path: Path | str | None = None,
        settings: EvaluationSettings | None = None,
    ):
        base_eval_dir = Path(__file__).resolve().parent.parent
        if config_path is None:
            config_path = base_eval_dir / "config/eval_config.yaml"

        self.settings = settings or EvaluationSettings.from_yaml(config_path)
        self.eval_config = {
            "judge": self.settings.judge.model_dump(),
            "mlflow": self.settings.mlflow.model_dump(),
            "execution": self.settings.execution.model_dump(),
        }

        profile_path = base_eval_dir / "config/target_model_profile.yaml"
        with open(profile_path, "r", encoding="utf-8") as f:
            self.target_model_profile = yaml.safe_load(f)

        self.rubrics_dir = base_eval_dir / "config/rubrics"

        self.model_name = self.settings.judge.model
        self.temperature = self.settings.judge.temperature

        self.max_retries = getattr(self.settings.judge, "max_retries", 5)
        self.retry_delay = getattr(self.settings.judge, "retry_delay", 2.0)
        self.retry_backoff = getattr(self.settings.judge, "retry_backoff", 2.0)

        self.client = OpenAI(
            base_url=self.settings.judge.base_url,
            api_key=self.settings.judge.api_key,
            timeout=self.settings.judge.timeout,
            max_retries=self.max_retries,
        )
        logger.info(
            "LLM Judge initialise via endpoint MLflow Gateway (%s) avec modele : %s (max_retries=%d)",
            self.settings.judge.base_url,
            self.model_name,
            self.max_retries,
        )

    def load_rubric(self, domain: str) -> dict[str, Any]:
        rubric_path = self.rubrics_dir / f"{domain}_rubrics.yaml"
        if not rubric_path.exists():
            rubric_path = self.rubrics_dir / "oncology_rubrics.yaml"
        with open(rubric_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def build_system_prompt(self, domain: str) -> str:
        rubric = self.load_rubric(domain)
        profile_yaml = yaml.dump(self.target_model_profile, allow_unicode=True)
        rubric_yaml = yaml.dump(rubric, allow_unicode=True)

        return f"""Tu es un medecin-expert et prompt engineer de niveau mondial, specialise dans l'audit clinique d'agents IA en oncologie et maladies rares.
Ton role est d'evaluer les reponses fournies par l'application Oncoflow, basee sur des agents utilisant des Small Language Models (SLM) locaux.

=========================================
PROFIL DU MODELE CIBLE EVALUE (A RESPECTER STRICTEMENT) :
=========================================
{profile_yaml}

=========================================
GRILLE D'EVALUATION CLINIQUE ET TECHNIQUE :
=========================================
{rubric_yaml}

DIRECTIVES CRITIQUES POUR L'EVALUATION :
1. Sois intransigeant sur l'ancrage clinique : le dossier medical (MTD) est la SEULE verite de reference. Si une donnee n'est pas dans le MTD, l'agent ne DOIT PAS la deviner.
2. Pour les recommandations de prompt : NE PROPOSE JAMAIS un prompt concu pour un LLM frontiere de 100B+. Ton prompt suggere DOIT etre :
   - Court et percutant (< 400 tokens)
   - Rempli de directives affirmatives claires (bannir les listes d'interdictions "Ne pas faire X")
   - Dote de delimiteurs markdown explicites (### CONTEXTE, ### TACHE, ### FORMAT)
   - Termine par la definition du schema de sortie en tout dernier.
3. Rends ton evaluation STRICTEMENT au format JSON structure conformement au schema attendu.
"""

    def evaluate(
        self,
        domain: str,
        agent_name: str,
        case_id: str,
        patient_mtd_text: str,
        agent_output: dict[str, Any] | str,
        current_prompt: str,
        reference_guidelines_text: str = "",
        session_id: str | None = None,
        experiment_id: str | None = None,
    ) -> JudgeEvaluation:
        """Evalue une sortie d'agent ou de debat multi-agents avec retry automatique et trace MLflow."""
        import mlflow
        from src.infrastructure.telemetry.tracing import ensure_tracing_destination

        eff_exp_id = str(experiment_id or os.environ.get("MLFLOW_EXPERIMENT_ID") or "1")
        ensure_tracing_destination(experiment_id=eff_exp_id)

        system_prompt = self.build_system_prompt(domain)

        agent_output_str = (
            json.dumps(agent_output, indent=2, ensure_ascii=False, default=str)
            if isinstance(agent_output, dict)
            else str(agent_output)
        )

        user_content = f"""Evalue l'extraction produite par l'agent '{agent_name}' pour le cas '{case_id}' ({domain}).

### DOSSIER PATIENT SOURCE (MTD) :
{patient_mtd_text[:12000]}

### REFERENTIELS MEDICAUX ASSOCIES (Extrait TNCD/PNDS si applicable) :
{reference_guidelines_text[:4000] if reference_guidelines_text else "Non specifie ou integre aux agents"}

### PROMPT ACTUELLEMENT UTILISE PAR L'AGENT :
{current_prompt}

### SORTIE PRODUITE PAR L'AGENT :
{agent_output_str}

Retourne ton evaluation au format JSON suivant :
{{
  "domain": "{domain}",
  "agent_name": "{agent_name}",
  "evaluated_case_id": "{case_id}",
  "scores": {{
    "clinical_faithfulness": {{ "score": 1-5, "justification": "..." }},
    "completeness_awareness": {{ "score": 1-5, "justification": "..." }},
    "tncd_or_pnds_conformance": {{ "score": 1-5, "justification": "..." }},
    "structural_robustness": {{ "score": 1-5, "justification": "..." }},
    "debate_consensus": {{ "score": 1-5, "justification": "..." }}
  }},
  "identified_hallucinations": ["..."],
  "identified_missing_data_errors": ["..."],
  "prompt_optimization": {{
    "slm_failure_diagnostics": "...",
    "suggested_prompt": "...",
    "slm_optimizations_applied": ["..."],
    "expected_gain": "..."
  }},
  "overall_clinical_summary": "..."
}}
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        span_kwargs: dict[str, Any] = {
            "name": f"llm_judge_{agent_name}",
            "span_type": "LLM",
        }
        try:
            from mlflow.entities.trace_location import MlflowExperimentLocation

            span_kwargs["trace_destination"] = MlflowExperimentLocation(eff_exp_id)
        except Exception:
            pass

        span_ctx = (
            mlflow.start_span(**span_kwargs)
            if hasattr(mlflow, "start_span")
            else nullcontext()
        )

        with span_ctx as span:
            if span is not None and hasattr(span, "set_attributes"):
                try:
                    attrs = {
                        "domain": domain,
                        "agent_name": agent_name,
                        "case_id": case_id,
                        "judge_model": self.model_name,
                        "experiment_id": eff_exp_id,
                    }
                    if session_id:
                        attrs["session_id"] = session_id
                        attrs["mlflow.trace.sessionId"] = session_id
                    span.set_attributes(attrs)
                    span.set_inputs(
                        {
                            "case_id": case_id,
                            "agent_name": agent_name,
                            "current_prompt_preview": current_prompt[:1000],
                            "patient_mtd_preview": patient_mtd_text[:1000],
                        }
                    )
                except Exception:
                    pass

            response = None
            last_exception = None

            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.info(
                        "Envoi de l'evaluation au juge via LiteLLM/Gateway (%s) [tentative %d/%d]...",
                        self.model_name,
                        attempt,
                        self.max_retries,
                    )
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        temperature=self.temperature,
                        response_format={"type": "json_object"},
                    )
                    break
                except (
                    InternalServerError,
                    RateLimitError,
                    APIConnectionError,
                    APITimeoutError,
                ) as exc:
                    last_exception = exc
                    if attempt >= self.max_retries:
                        logger.error(
                            "Echec definitif du juge apres %d tentatives suite a l'erreur: %s",
                            attempt,
                            exc,
                        )
                        if span is not None and hasattr(span, "record_exception"):
                            try:
                                span.record_exception(exc)
                                span.set_status("ERROR")
                            except Exception:
                                pass
                        raise
                    delay = min(
                        self.retry_delay * (self.retry_backoff ** (attempt - 1))
                        + random.uniform(0.5, 1.5),
                        60.0,
                    )
                    if (
                        isinstance(exc, RateLimitError)
                        or getattr(exc, "status_code", None) == 429
                    ):
                        delay = max(5.0, delay)
                    logger.warning(
                        "Erreur temporaire du juge (%s): %s. Surcharge ou 503/429 detecte. Reessai dans %.1fs (tentative %d/%d)...",
                        self.model_name,
                        exc,
                        delay,
                        attempt,
                        self.max_retries,
                    )
                    time.sleep(delay)
                except APIStatusError as exc:
                    last_exception = exc
                    status_code = getattr(exc, "status_code", 0)
                    is_transient = status_code in (429, 500, 502, 503, 504)
                    if is_transient and attempt < self.max_retries:
                        delay = min(
                            self.retry_delay * (self.retry_backoff ** (attempt - 1))
                            + random.uniform(0.5, 1.5),
                            60.0,
                        )
                        if status_code == 429:
                            delay = max(5.0, delay)
                        logger.warning(
                            "Erreur de statut API temporaire (%s) du juge (%s). Reessai dans %.1fs (tentative %d/%d)...",
                            status_code,
                            exc,
                            delay,
                            attempt,
                            self.max_retries,
                        )
                        time.sleep(delay)
                    else:
                        if span is not None and hasattr(span, "record_exception"):
                            try:
                                span.record_exception(exc)
                                span.set_status("ERROR")
                            except Exception:
                                pass
                        raise
                except Exception as exc:
                    if span is not None and hasattr(span, "record_exception"):
                        try:
                            span.record_exception(exc)
                            span.set_status("ERROR")
                        except Exception:
                            pass
                    raise

            if response is None and last_exception:
                raise last_exception

            raw_content = response.choices[0].message.content or "{}"
            clean_content = self._extract_json(raw_content)

            try:
                data = json.loads(clean_content, strict=False)
            except json.JSONDecodeError as exc:
                repaired = False
                for fix in ['"', '"}', '"\n}', '"\n}\n}', '"\n}\n}\n}']:
                    try:
                        data = json.loads(clean_content + fix, strict=False)
                        repaired = True
                        break
                    except Exception:
                        continue
                if not repaired:
                    logger.warning(
                        "Contenu brut du juge non analysable en JSON (%s) : %s",
                        exc,
                        raw_content[:500],
                    )
                    raise exc

            judge_eval = JudgeEvaluation.model_validate(data)

            if span is not None and hasattr(span, "set_outputs"):
                try:
                    span.set_outputs(
                        {
                            "overall_clinical_summary": judge_eval.overall_clinical_summary,
                            "scores": {
                                k: v.score for k, v in judge_eval.scores.items()
                            },
                            "hallucinations_count": len(
                                judge_eval.identified_hallucinations
                            ),
                            "missing_data_errors_count": len(
                                judge_eval.identified_missing_data_errors
                            ),
                        }
                    )
                except Exception:
                    pass

            return judge_eval

    def _extract_json(self, text: str) -> str:
        text_clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        json_match = re.search(r"```json\s*(.*?)\s*```", text_clean, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        code_match = re.search(r"```\s*(.*?)\s*```", text_clean, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        open_braces = [m.start() for m in re.finditer(r"\{", text_clean)]
        close_braces = [m.start() for m in re.finditer(r"\}", text_clean)]
        for start in open_braces:
            for end in reversed(close_braces):
                if end > start:
                    candidate = text_clean[start : end + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except Exception:
                        pass
        return text_clean
