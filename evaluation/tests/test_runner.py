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
    assert onco_form.__name__ in ("PatientMDTForm", "PatientMDTOncologicForm")
    assert len(onco_agents.expert_agents) >= 3

    sma_agents, sma_form = runner.load_domain_components("sma")
    assert sma_agents is not None
    assert sma_form.__name__ in ("PatientMDTForm", "PatientMDTSmaForm")
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


@patch("evaluation.engine.runner.mlflow")
@patch("evaluation.engine.runner.DocumentReader")
@patch("evaluation.engine.runner.collaborative_debate")
def test_runner_run_case_evaluation_stream(
    mock_collab,
    mock_doc_reader_cls,
    mock_mlflow,
    sample_judge_response,
):
    mock_collab.return_value = {"resecability": "resecable"}
    mock_reader = MagicMock()
    mock_doc = MagicMock(page_content="Texte patient")
    mock_reader.markdown_exporter = [mock_doc]
    mock_doc_reader_cls.return_value = mock_reader

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
                {"id": "onco-01", "filename": "case1.pdf"},
                {"id": "onco-02", "filename": "case2.pdf"},
            ],
        },
    ):
        with patch("pathlib.Path.exists", return_value=True):
            stream = runner.run_case_evaluation_stream(
                domain="oncology",
                mode="debate",
            )
            results = list(stream)

    assert len(results) == 2
    assert results[0]["case_id"] == "onco-01"
    assert results[1]["case_id"] == "onco-02"
    assert results[0]["prompt_name"] == "oncoflow_oncology_debate_prompt"
    assert results[0]["status"] == "success"


@patch("evaluation.engine.runner.mlflow")
@patch("evaluation.engine.runner.DocumentReader")
@patch("evaluation.engine.runner.collaborative_debate")
def test_runner_run_case_evaluation_stream_error_handling(
    mock_collab,
    mock_doc_reader_cls,
    mock_mlflow,
):
    """Verifie qu'une erreur sur un cas ne stoppe pas l'ensemble de l'evaluation."""
    mock_collab.side_effect = RuntimeError("Erreur API 503 Gateway")
    mock_reader = MagicMock()
    mock_doc = MagicMock(page_content="Texte patient")
    mock_reader.markdown_exporter = [mock_doc]
    mock_doc_reader_cls.return_value = mock_reader

    runner = EvaluationRunner()

    with patch.object(
        EvaluationRunner,
        "load_manifest",
        return_value={
            "domain": "oncology",
            "cases": [
                {"id": "onco-01", "filename": "case1.pdf"},
            ],
        },
    ):
        with patch("pathlib.Path.exists", return_value=True):
            results = list(runner.run_case_evaluation_stream(domain="oncology"))

    assert len(results) == 1
    assert results[0]["status"] == "error"
    assert "Erreur" in results[0]["summary"]


@patch("evaluation.engine.runner.mlflow")
def test_runner_submodels_discovery_and_resolution(mock_mlflow):
    runner = EvaluationRunner()
    _, onco_form = runner.load_domain_components("oncology")

    submodels = runner.get_form_submodels(onco_form)
    assert "PatientAdministrative" in submodels
    assert "RadiologicExams" in submodels

    # Test exact match
    res_admin = runner.resolve_form_submodel(onco_form, "PatientAdministrative")
    assert res_admin is not None
    assert res_admin[0] == "PatientAdministrative"

    # Test resolution of RadiologicExamType to RadiologicExams
    res_rad = runner.resolve_form_submodel(onco_form, "RadiologicExamType")
    assert res_rad is not None
    assert res_rad[0] == "RadiologicExams"

    # Test resolution of RadiologicExams
    res_rad2 = runner.resolve_form_submodel(onco_form, "RadiologicExams")
    assert res_rad2 is not None
    assert res_rad2[0] == "RadiologicExams"

    # Test unknown class returns None
    res_none = runner.resolve_form_submodel(onco_form, "UnknownNonExistentClass")
    assert res_none is None


@patch("evaluation.engine.runner.mlflow")
@patch("evaluation.engine.runner.DocumentReader")
@patch("evaluation.engine.runner.collaborative_debate")
def test_runner_run_case_evaluation_targeted_class(
    mock_collab,
    mock_doc_reader_cls,
    mock_mlflow,
    sample_judge_response,
):
    mock_collab.return_value = {"first_name": "Jean", "last_name": "Dupont"}
    mock_reader = MagicMock()
    mock_doc = MagicMock(page_content="Dossier patient texte test")
    mock_reader.markdown_exporter = [mock_doc]
    mock_doc_reader_cls.return_value = mock_reader

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
                target_class="PatientAdministrative",
            )

    assert len(results) == 1
    assert results[0]["case_id"] == "onco-01"
    assert results[0]["target_class"] == "PatientAdministrative"
    assert (
        results[0]["prompt_name"]
        == "oncoflow_oncology_patientadministrative_debate_prompt"
    )
    assert results[0]["status"] == "success"


@patch("evaluation.engine.runner.mlflow")
@patch("evaluation.engine.runner.DocumentReader")
@patch("evaluation.engine.runner.collaborative_debate")
def test_runner_run_case_evaluation_auto_mode_patient_administrative_single_agent(
    mock_collab,
    mock_doc_reader_cls,
    mock_mlflow,
    sample_judge_response,
):
    """Verifie que PatientAdministrative s'execute automatiquement en agent unique (Administratives_agent) et non en debat."""
    mock_reader = MagicMock()
    mock_doc = MagicMock(page_content="Dossier patient texte test")
    mock_reader.markdown_exporter = [mock_doc]
    mock_doc_reader_cls.return_value = mock_reader

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
            with patch(
                "src.domain.common.agents.Agents.Administratives_agent.ask"
            ) as mock_ask:
                mock_ask.return_value = MagicMock(
                    model_dump=MagicMock(
                        return_value={"first_name": "Jean", "last_name": "Dupont"}
                    )
                )
                results = runner.run_case_evaluation(
                    domain="oncology",
                    case_id="onco-01",
                    # mode par defaut = "auto"
                    target_class="PatientAdministrative",
                )

    # Le debat ne doit JAMAIS etre appele pour PatientAdministrative
    mock_collab.assert_not_called()
    assert len(results) == 1
    assert results[0]["case_id"] == "onco-01"
    assert results[0]["target_class"] == "PatientAdministrative"
    assert "administrative" in results[0]["prompt_name"].lower()
    assert results[0]["status"] == "success"
