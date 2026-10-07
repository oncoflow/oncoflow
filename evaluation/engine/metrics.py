"""Definitions et helpers pour la journalisation des metriques LLM-as-a-Judge dans MLflow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import mlflow

from evaluation.engine.judge import JudgeEvaluation

logger = logging.getLogger("OncoflowEval.Metrics")

METRIC_KEYS = [
    "clinical_faithfulness",
    "completeness_awareness",
    "guideline_conformance",
    "structural_robustness",
    "debate_consensus",
]


def register_prompt_to_registry(
    name: str,
    template: str,
    commit_message: str | None = None,
    tags: dict[str, str] | None = None,
    model_config: dict[str, Any] | None = None,
) -> Any:
    """Enregistre un prompt dans le Prompt Registry de MLflow 3.

    Supporte l'API mlflow.genai.register_prompt (MLflow 3.x) avec retro-compatibilite
    et tolerance aux environnements ne disposant pas du backend Prompt Registry.
    """
    if not name or not template:
        return None

    import re

    clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name.strip())
    try:
        eff_tags = dict(tags or {})
        import os

        exp_id = os.environ.get("MLFLOW_EXPERIMENT_ID", "1")
        if "_mlflow_experiment_ids" not in eff_tags:
            eff_tags["_mlflow_experiment_ids"] = f",{exp_id},"

        if hasattr(mlflow, "genai") and hasattr(mlflow.genai, "register_prompt"):
            prompt_obj = mlflow.genai.register_prompt(
                name=clean_name,
                template=template,
                commit_message=commit_message
                or "Prompt enregistre lors de l'evaluation Oncoflow",
                tags=eff_tags,
                model_config=model_config,
            )
            logger.info(
                "Prompt '%s' enregistre dans le Prompt Registry MLflow 3 (version: %s)",
                clean_name,
                getattr(prompt_obj, "version", "1"),
            )
            return prompt_obj
        elif hasattr(mlflow, "register_prompt"):
            return mlflow.register_prompt(name=clean_name, template=template)
    except Exception as e:
        logger.warning(
            "Enregistrement du prompt '%s' dans le Prompt Registry MLflow indisponible (%s). "
            "Sauvegarde persistante sous forme d'artefact de run.",
            clean_name,
            e,
        )
    return None


def safe_mlflow_log_text(text: str, artifact_file: str) -> None:
    """Enregistre un texte comme artefact dans MLflow avec gestion d'erreurs d'I/O et de permissions."""
    try:
        mlflow.log_text(text, artifact_file)
    except Exception as e:
        logger.warning(
            "Impossible d'enregistrer l'artefact textuel '%s' dans MLflow (%s). "
            "Poursuite de l'evaluation.",
            artifact_file,
            e,
        )


def safe_mlflow_log_artifact(local_path: str, artifact_path: str | None = None) -> None:
    """Enregistre un artefact fichier dans MLflow avec gestion d'erreurs d'I/O et de permissions."""
    try:
        mlflow.log_artifact(local_path, artifact_path=artifact_path)
    except Exception as e:
        logger.warning(
            "Impossible d'enregistrer l'artefact fichier '%s' dans MLflow (%s). "
            "Poursuite de l'evaluation.",
            local_path,
            e,
        )


def log_judge_evaluation_to_mlflow(
    judge_eval: JudgeEvaluation,
    artifacts: list[Path] | None = None,
    step: int = 0,
    prompt_name: str | None = None,
    prompt_template: str | None = None,
    prompt_tags: dict[str, str] | None = None,
) -> dict[str, float]:
    """Enregistre les scores du juge et les artefacts associes dans le run MLflow actif."""
    logged_metrics: dict[str, float] = {}

    for metric_name, score_obj in judge_eval.scores.items():
        mlflow_metric_key = f"judge_{metric_name}"
        mlflow.log_metric(mlflow_metric_key, float(score_obj.score), step=step)
        logged_metrics[mlflow_metric_key] = float(score_obj.score)

    if logged_metrics:
        avg_score = sum(logged_metrics.values()) / len(logged_metrics)
        mlflow.log_metric("judge_overall_average", avg_score, step=step)
        logged_metrics["judge_overall_average"] = avg_score

    # Log summary tags
    mlflow.set_tag("agent_name", judge_eval.agent_name)
    mlflow.set_tag("domain", judge_eval.domain)
    mlflow.set_tag("case_id", judge_eval.evaluated_case_id)
    mlflow.set_tag(
        "hallucinations_count", str(len(judge_eval.identified_hallucinations))
    )
    mlflow.set_tag(
        "missing_data_errors_count",
        str(len(judge_eval.identified_missing_data_errors)),
    )

    # Enregistrement dans le Prompt Registry MLflow 3 si un prompt est fourni
    if prompt_name and prompt_template:
        p_tags = {"domain": judge_eval.domain, "case_id": judge_eval.evaluated_case_id}
        if prompt_tags:
            p_tags.update(prompt_tags)
        prompt_ver = register_prompt_to_registry(
            name=prompt_name,
            template=prompt_template,
            commit_message=f"Prompt utilise pour le cas {judge_eval.evaluated_case_id} ({judge_eval.agent_name})",
            tags=p_tags,
        )
        mlflow.set_tag("prompt.registry.name", prompt_name)
        if prompt_ver is not None and hasattr(prompt_ver, "version"):
            mlflow.set_tag("prompt.registry.version", str(prompt_ver.version))
        safe_mlflow_log_text(
            prompt_template,
            f"prompts/{prompt_name}.txt",
        )

    # Enregistrement du prompt optimise suggere par le juge dans le Prompt Registry MLflow 3
    if (
        judge_eval.prompt_optimization
        and judge_eval.prompt_optimization.suggested_prompt
    ):
        opt_name = f"oncoflow_{judge_eval.domain}_{judge_eval.agent_name}_optimized"
        opt_tags = {
            "domain": judge_eval.domain,
            "case_id": judge_eval.evaluated_case_id,
            "agent": judge_eval.agent_name,
            "optimized": "true",
            "expected_gain": judge_eval.prompt_optimization.expected_gain,
        }
        opt_ver = register_prompt_to_registry(
            name=opt_name,
            template=judge_eval.prompt_optimization.suggested_prompt,
            commit_message=f"Prompt revise SLM suggere par le juge pour {judge_eval.evaluated_case_id}",
            tags=opt_tags,
        )
        if opt_ver is not None and hasattr(opt_ver, "version"):
            mlflow.set_tag("prompt.optimized.version", str(opt_ver.version))

    # Log evaluation json as text artifact
    eval_json = judge_eval.model_dump_json(indent=2)
    safe_mlflow_log_text(
        eval_json,
        f"evaluations/{judge_eval.agent_name}_{judge_eval.evaluated_case_id}.json",
    )

    # Log external artifacts (e.g. prompt diffs, full MTD dumps)
    if artifacts:
        for art_path in artifacts:
            if art_path.exists():
                safe_mlflow_log_artifact(
                    str(art_path), artifact_path="prompt_optimizations"
                )

    logger.info(
        "Metriques MLflow enregistrees pour %s (%s) : Moyenne=%.2f",
        judge_eval.agent_name,
        judge_eval.evaluated_case_id,
        logged_metrics.get("judge_overall_average", 0.0),
    )
    return logged_metrics
