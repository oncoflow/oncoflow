"""Definitions et helpers pour la journalisation des metriques LLM-as-a-Judge dans MLflow."""

from __future__ import annotations

import logging
from pathlib import Path

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


def log_judge_evaluation_to_mlflow(
    judge_eval: JudgeEvaluation,
    artifacts: list[Path] | None = None,
    step: int = 0,
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

    # Log evaluation json as text artifact
    eval_json = judge_eval.model_dump_json(indent=2)
    mlflow.log_text(
        eval_json,
        f"evaluations/{judge_eval.agent_name}_{judge_eval.evaluated_case_id}.json",
    )

    # Log external artifacts (e.g. prompt diffs, full MTD dumps)
    if artifacts:
        for art_path in artifacts:
            if art_path.exists():
                mlflow.log_artifact(str(art_path), artifact_path="prompt_optimizations")

    logger.info(
        "Metriques MLflow enregistrees pour %s (%s) : Moyenne=%.2f",
        judge_eval.agent_name,
        judge_eval.evaluated_case_id,
        logged_metrics.get("judge_overall_average", 0.0),
    )
    return logged_metrics
