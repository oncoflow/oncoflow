"""Tests unitaires pour la journalisation des metriques MLflow."""

from __future__ import annotations

from unittest.mock import patch

from evaluation.engine.judge import JudgeEvaluation
from evaluation.engine.metrics import log_judge_evaluation_to_mlflow


@patch("evaluation.engine.metrics.mlflow")
def test_log_judge_evaluation_to_mlflow(mock_mlflow, sample_judge_response, tmp_path):
    judge_eval = JudgeEvaluation.model_validate(sample_judge_response)

    artifact_file = tmp_path / "sample_diff.md"
    artifact_file.write_text("diff content", encoding="utf-8")

    metrics = log_judge_evaluation_to_mlflow(
        judge_eval=judge_eval,
        artifacts=[artifact_file],
        step=0,
    )

    assert "judge_clinical_faithfulness" in metrics
    assert metrics["judge_clinical_faithfulness"] == 5.0
    assert "judge_overall_average" in metrics

    # Verifications des appels MLflow
    assert mock_mlflow.log_metric.call_count >= 5
    assert mock_mlflow.set_tag.call_count >= 4
    mock_mlflow.log_text.assert_called_once()
    mock_mlflow.log_artifact.assert_called_once_with(
        str(artifact_file), artifact_path="prompt_optimizations"
    )
