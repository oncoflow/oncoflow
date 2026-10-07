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


@patch("evaluation.engine.metrics.mlflow")
def test_log_judge_evaluation_with_prompt_registry(mock_mlflow, sample_judge_response):
    """Verifie l'enregistrement d'un prompt dans le Prompt Registry MLflow 3 lors du log."""
    from unittest.mock import MagicMock

    mock_prompt_obj = MagicMock(version="2")
    mock_mlflow.genai.register_prompt.return_value = mock_prompt_obj

    judge_eval = JudgeEvaluation.model_validate(sample_judge_response)

    metrics = log_judge_evaluation_to_mlflow(
        judge_eval=judge_eval,
        prompt_name="oncoflow_oncology_debate_prompt",
        prompt_template="Question de test pour le Prompt Registry",
        step=1,
    )

    assert "judge_overall_average" in metrics
    mock_mlflow.genai.register_prompt.assert_called()
    mock_mlflow.set_tag.assert_any_call(
        "prompt.registry.name", "oncoflow_oncology_debate_prompt"
    )
    mock_mlflow.set_tag.assert_any_call("prompt.registry.version", "2")


@patch("evaluation.engine.metrics.mlflow")
def test_register_prompt_to_registry_fallback(mock_mlflow):
    """Verifie le fallback gracieux si le Prompt Registry leve une exception."""
    from evaluation.engine.metrics import register_prompt_to_registry

    mock_mlflow.genai.register_prompt.side_effect = RuntimeError(
        "Endpoint indisponible"
    )

    result = register_prompt_to_registry(
        name="test_prompt",
        template="Mon template de test",
    )
    assert result is None
