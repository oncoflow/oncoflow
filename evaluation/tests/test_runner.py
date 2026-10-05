"""Tests unitaires pour EvaluationRunner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from evaluation.engine.judge import JudgeEvaluation
from evaluation.engine.runner import EvaluationRunner


@patch("evaluation.engine.runner.mlflow")
def test_runner_load_domain_components(mock_mlflow):
    runner = EvaluationRunner()

    onco_agents, onco_form = runner.load_domain_components("oncology")
    assert onco_agents is not None
    assert onco_form.__name__ == "PatientMDTForm"
    assert len(onco_agents.expert_agents) >= 3

    sma_agents, sma_form = runner.load_domain_components("sma")
    assert sma_agents is not None
    assert sma_form.__name__ == "PatientMDTForm"
    assert len(sma_agents.expert_agents) >= 5


@patch("evaluation.engine.runner.mlflow")
def test_runner_load_manifest(mock_mlflow):
    runner = EvaluationRunner()

    onco_manifest = runner.load_manifest("oncology")
    assert onco_manifest["domain"] == "oncology"
    assert len(onco_manifest["cases"]) >= 4

    sma_manifest = runner.load_manifest("sma")
    assert sma_manifest["domain"] == "sma"
    assert len(sma_manifest["cases"]) >= 1


@patch("evaluation.engine.runner.mlflow")
def test_runner_extract_mtd_text(mock_mlflow):
    runner = EvaluationRunner()

    mock_reader = MagicMock()
    mock_doc = MagicMock(page_content="Contenu page markdown")
    mock_reader.markdown_exporter = [mock_doc]

    text = runner.extract_mtd_text(mock_reader)
    assert text == "Contenu page markdown"


@patch("evaluation.engine.runner.mlflow")
@patch("evaluation.engine.runner.DocumentReader")
@patch("evaluation.engine.runner.collaborative_debate")
def test_runner_run_case_evaluation_debate(
    mock_collab,
    mock_doc_reader_cls,
    mock_mlflow,
    sample_judge_response,
):
    mock_collab.return_value = {"resecability": "resecable"}

    mock_reader = MagicMock()
    mock_doc = MagicMock(page_content="Dossier patient texte test")
    mock_reader.markdown_exporter = [mock_doc]
    mock_doc_reader_cls.return_value = mock_reader

    mock_run = MagicMock()
    mock_mlflow.start_run.return_value.__enter__.return_value = mock_run

    runner = EvaluationRunner()
    runner.judge.evaluate = MagicMock(
        return_value=JudgeEvaluation.model_validate(sample_judge_response)
    )

    with patch.object(
        EvaluationRunner,
        "load_manifest",
        return_value={
            "domain": "oncology",
            "cases": [
                {
                    "id": "onco-01",
                    "filename": "CHEVALIER-Emilie_anon.pdf",
                }
            ],
        },
    ):
        with patch("pathlib.Path.exists", return_value=True):
            results = runner.run_case_evaluation(
                domain="oncology",
                case_id="onco-01",
                mode="debate",
            )

    assert len(results) == 1
    assert results[0]["case_id"] == "onco-01"
    assert "judge_clinical_faithfulness" in results[0]["metrics"]
