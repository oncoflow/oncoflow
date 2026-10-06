"""Client LLM-as-a-Judge utilisant LiteLLM avec sensibilisation aux limitations des SLM locaux (7B-14B)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from openai import OpenAI
from pydantic import BaseModel, Field

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

    def __init__(self, config_path: Path | str | None = None):
        base_eval_dir = Path(__file__).resolve().parent.parent
        if config_path is None:
            config_path = base_eval_dir / "config/eval_config.yaml"

        with open(config_path, "r", encoding="utf-8") as f:
            self.eval_config = yaml.safe_load(f)

        profile_path = base_eval_dir / "config/target_model_profile.yaml"
        with open(profile_path, "r", encoding="utf-8") as f:
            self.target_model_profile = yaml.safe_load(f)

        self.rubrics_dir = base_eval_dir / "config/rubrics"

        judge_cfg = self.eval_config.get("judge", {})
        base_url = os.getenv(
            "LITELLM_BASE_URL",
            judge_cfg.get("base_url", "http://127.0.0.1:4000/v1"),
        )
        api_key = os.getenv(
            "LITELLM_API_KEY", judge_cfg.get("api_key", "sk-litellm-oncoflow")
        )
        self.model_name = os.getenv(
            "LITELLM_JUDGE_MODEL", judge_cfg.get("model", "gemini/gemini-2.5-flash")
        )
        self.temperature = judge_cfg.get("temperature", 0.0)

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        logger.info(
            "LLM Judge initialise via LiteLLM (%s) avec modele : %s",
            base_url,
            self.model_name,
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
    ) -> JudgeEvaluation:
        """Evalue une sortie d'agent ou de debat multi-agents."""
        system_prompt = self.build_system_prompt(domain)

        agent_output_str = (
            json.dumps(agent_output, indent=2, ensure_ascii=False)
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

        logger.info(
            "Envoi de l'evaluation au juge via LiteLLM (%s)...", self.model_name
        )
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )

        raw_content = response.choices[0].message.content or "{}"
        clean_content = self._extract_json(raw_content)

        data = json.loads(clean_content)
        return JudgeEvaluation.model_validate(data)

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
