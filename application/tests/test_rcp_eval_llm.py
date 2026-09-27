"""
Live evaluation of the RCP review questions against a real LLM.

Skipped by default (CI has no LLM). Run it in the homelab through Bifrost:

    ONCOFLOW_LLM_EVAL=1 APP_CONFIGLLM_TYPE=Bifrost APP_CONFIGLLM_URL=http://bifrost \\
    APP_CONFIGLLM_PORT=8080 APP_CONFIGLLM_URI=/v1 APP_CONFIGLLM_MODELS=ollama/qwen3:14b \\
    PYTHONPATH=. uv run pytest tests/test_rcp_eval_llm.py -v

The LLM backend must be local: never point this evaluation to a public cloud provider.
"""

import os
from pathlib import Path

import pytest

from src.application.evaluation.rcp_eval import load_rcp_cases, score_answer

pytestmark = pytest.mark.skipif(
    os.environ.get("ONCOFLOW_LLM_EVAL") != "1",
    reason="live LLM evaluation, set ONCOFLOW_LLM_EVAL=1 to run it",
)

CASES = load_rcp_cases(Path(__file__).parent / "fixtures" / "rcp")


@pytest.fixture(scope="module")
def config():
    from src.application.config import AppConfig

    return AppConfig()


@pytest.mark.parametrize(
    "case, question",
    [
        pytest.param(case, question, id=f"{case.case_id}-{question}")
        for case in CASES
        for question in case.expected
    ],
)
def test_llm_answers_rcp_question(config, case, question):
    from src.domain.oncology.rcp_review import RCP_REVIEW_QUESTIONS, RCPReviewerAgent

    model = RCP_REVIEW_QUESTIONS[question]
    agent = RCPReviewerAgent(config=config, mtd=case.to_record(), output_format=model)

    answer = agent.ask(model.question)

    result = score_answer(case.case_id, question, answer, case.expected[question])
    assert result.passed, f"{result.errors}\nanswer: {answer}"
