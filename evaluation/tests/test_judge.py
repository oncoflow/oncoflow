"""Tests unitaires pour le composant LLMJudge."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from evaluation.engine.judge import JudgeEvaluation, LLMJudge


def test_judge_init():
    judge = LLMJudge()
    assert judge.eval_config is not None
    assert judge.target_model_profile is not None
    assert "Qwen/Qwen3-14B-GGUF" in str(judge.target_model_profile)


def test_judge_load_rubric():
    judge = LLMJudge()
    onco_rubric = judge.load_rubric("oncology")
    assert onco_rubric["domain"] == "oncology"
    assert "clinical_faithfulness" in onco_rubric["metrics"]

    sma_rubric = judge.load_rubric("sma")
    assert sma_rubric["domain"] == "sma"
    assert "pnds_conformance" in sma_rubric["metrics"]


def test_judge_build_system_prompt():
    judge = LLMJudge()
    prompt = judge.build_system_prompt("oncology")
    assert "PROFIL DU MODELE CIBLE" in prompt
    assert "Small Language Models (SLM)" in prompt
    assert "TNCD" in prompt


def test_extract_json_variants():
    judge = LLMJudge()

    # 1. Block ```json
    text1 = 'Voici la reponse :\n```json\n{"score": 5}\n```'
    assert json.loads(judge._extract_json(text1)) == {"score": 5}

    # 2. Block avec thinking <think>
    text2 = '<think>Analyse en cours...</think>\n```json\n{"score": 4}\n```'
    assert json.loads(judge._extract_json(text2)) == {"score": 4}

    # 3. JSON brut
    text3 = 'Preambule textuel {"status": "ok"} suffixe'
    assert json.loads(judge._extract_json(text3)) == {"status": "ok"}


@patch("evaluation.engine.judge.OpenAI")
def test_judge_evaluate(mock_openai_cls, sample_judge_response):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(sample_judge_response)
    mock_response = MagicMock(choices=[mock_choice])
    mock_client.chat.completions.create.return_value = mock_response

    judge = LLMJudge()
    judge.client = mock_client

    result = judge.evaluate(
        domain="oncology",
        agent_name="pancreas expert",
        case_id="onco-01",
        patient_mtd_text="Patient avec tumeur de la tete du pancreas.",
        agent_output={"resecability": "borderline"},
        current_prompt="Extrais les infos...",
    )

    assert isinstance(result, JudgeEvaluation)
    assert result.domain == "oncology"
    assert result.scores["clinical_faithfulness"].score == 5
    assert result.prompt_optimization is not None
    assert (
        "Directives affirmatives"
        in result.prompt_optimization.slm_optimizations_applied
    )


@patch("evaluation.engine.judge.time.sleep", return_value=None)
@patch("evaluation.engine.judge.OpenAI")
def test_judge_evaluate_retry_on_503(
    mock_openai_cls, mock_sleep, sample_judge_response
):
    """Verifie que le juge effectue un retry avec backoff sur une erreur 503 et reussit."""
    from openai import InternalServerError

    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(sample_judge_response)
    mock_success = MagicMock(choices=[mock_choice])

    err_response = MagicMock(status_code=503)
    error_503 = InternalServerError(
        message="503 Service Unavailable",
        response=err_response,
        body={"detail": "This model is currently experiencing high demand."},
    )

    # 1er appel: 503, 2eme appel: succes
    mock_client.chat.completions.create.side_effect = [error_503, mock_success]

    judge = LLMJudge()
    judge.client = mock_client
    judge.max_retries = 3
    judge.retry_delay = 0.01

    result = judge.evaluate(
        domain="oncology",
        agent_name="pancreas expert",
        case_id="onco-01",
        patient_mtd_text="Dossier patient...",
        agent_output={"resecability": "resecable"},
        current_prompt="Prompt...",
    )

    assert isinstance(result, JudgeEvaluation)
    assert mock_client.chat.completions.create.call_count == 2
    assert mock_sleep.call_count >= 1


@patch("evaluation.engine.judge.time.sleep", return_value=None)
@patch("evaluation.engine.judge.OpenAI")
def test_judge_evaluate_exhausts_retries(mock_openai_cls, mock_sleep):
    """Verifie que l'erreur 503 est levee si les tentatives de retry sont epuisees."""
    import pytest
    from openai import InternalServerError

    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    err_response = MagicMock(status_code=503)
    error_503 = InternalServerError(
        message="503 Service Unavailable",
        response=err_response,
        body={"detail": "This model is currently experiencing high demand."},
    )

    mock_client.chat.completions.create.side_effect = error_503

    judge = LLMJudge()
    judge.client = mock_client
    judge.max_retries = 3
    judge.retry_delay = 0.01

    with pytest.raises(InternalServerError):
        judge.evaluate(
            domain="oncology",
            agent_name="pancreas expert",
            case_id="onco-01",
            patient_mtd_text="Dossier patient...",
            agent_output={"resecability": "resecable"},
            current_prompt="Prompt...",
        )

    assert mock_client.chat.completions.create.call_count == 3
    assert mock_sleep.call_count >= 2
