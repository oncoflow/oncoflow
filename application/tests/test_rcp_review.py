"""
Data-driven tests of the RCP review questions on synthetic RCP records
(tests/fixtures/rcp). No LLM is called: the LLM is mocked with the gold answers.
The live evaluation is in tests/test_rcp_eval_llm.py.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from src.application.agent.tools import get_mtd_markdown
from src.application.evaluation.rcp_eval import (
    load_rcp_cases,
    normalize,
    score_answer,
)
from src.domain.common.patient_mdt_common_form import PatientMDTForm
from src.domain.oncology.rcp_review import RCP_REVIEW_QUESTIONS, RCPReviewerAgent

FIXTURES = Path(__file__).parent / "fixtures" / "rcp"
CASES = load_rcp_cases(FIXTURES)
CASE_IDS = [c.case_id for c in CASES]


def _pairs(keep=lambda expected: True):
    """(case, question) pairs with expected labels, filtered on the labels."""
    return [
        pytest.param(case, question, id=f"{case.case_id}-{question}")
        for case in CASES
        for question, expected in case.expected.items()
        if keep(expected)
    ]


SCORED = _pairs()
WITH_BOOLEAN = _pairs(lambda e: any(isinstance(v, bool) for v in e.values()))
WITH_MUST_MENTION = _pairs(lambda e: bool(e.get("must_mention")))


def fiche_field(case, label: str) -> str:
    match = re.search(rf"{label}\s*:\**\s*(.+)", case.fiche)
    assert match, f"{case.case_id}: '{label}' not found in fiche_rcp.md"
    return match.group(1).strip()


def age_at(birth: date, day: date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


# ---------------------------------------------------------------- fixtures data


def test_fixtures_are_discovered():
    assert len(CASES) >= 5


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_case_is_synthetic_and_complete(case):
    # The repository is public: only fictitious patients are allowed
    assert case.synthetic is True
    assert "FICTIF" in case.fiche
    assert case.fiche.strip() and case.annexes
    assert set(case.expected) <= set(RCP_REVIEW_QUESTIONS)
    assert set(case.gold) == set(RCP_REVIEW_QUESTIONS)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_annexes_are_about_the_same_patient(case):
    last_name = fiche_field(case, "Nom")
    birth = fiche_field(case, "Date de naissance")
    for name, annex in case.annexes.items():
        assert last_name in annex, f"{name} is about another patient"
        assert birth in annex, f"{name} has another date of birth"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_stated_age_matches_date_of_birth_unless_expected(case):
    """Deterministic baseline of the RecordInconsistencies question for the age."""
    birth = date.fromisoformat(fiche_field(case, "Date de naissance"))
    rcp_day = date.fromisoformat(fiche_field(case, "Date de la RCP"))
    stated_age = int(re.match(r"\d+", fiche_field(case, "Âge")).group())

    age_is_coherent = stated_age == age_at(birth, rcp_day)
    age_inconsistency_expected = any(
        "age" in group
        for group in case.expected.get("RecordInconsistencies", {}).get(
            "must_mention", []
        )
    )
    assert age_is_coherent is not age_inconsistency_expected


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_administrative_data_passes_form_validator(case):
    admin = PatientMDTForm.PatientAdministrative(
        first_name=fiche_field(case, "Prénom"),
        last_name=fiche_field(case, "Nom"),
        age=int(re.match(r"\d+", fiche_field(case, "Âge")).group()),
        date_birth=fiche_field(case, "Date de naissance"),
        date_rcp=fiche_field(case, "Date de la RCP"),
        gender="Male" if fiche_field(case, "Sexe") == "Homme" else "Female",
    )
    assert admin.date_birth < admin.date_rcp

    # A date of birth after the RCP date must be rejected by the form validator
    with pytest.raises(ValidationError):
        PatientMDTForm.PatientAdministrative(
            **admin.model_dump()
            | {
                "date_birth": admin.date_rcp,
                "date_rcp": admin.date_rcp - timedelta(days=1),
            }
        )


# ------------------------------------------------------------ models & scoring


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_gold_answers_are_valid(case):
    for question, answer in case.gold.items():
        RCP_REVIEW_QUESTIONS[question].model_validate(answer)


@pytest.mark.parametrize("case, question", SCORED)
def test_gold_answer_passes_expected(case, question):
    gold = RCP_REVIEW_QUESTIONS[question].model_validate(case.gold[question])
    result = score_answer(case.case_id, question, gold, case.expected[question])
    assert result.passed, result.errors


@pytest.mark.parametrize("case, question", WITH_BOOLEAN)
def test_wrong_boolean_answer_fails(case, question):
    bool_fields = [k for k, v in case.expected[question].items() if isinstance(v, bool)]
    wrong = case.gold[question] | {k: not case.gold[question][k] for k in bool_fields}
    result = score_answer(case.case_id, question, wrong, case.expected[question])
    assert not result.passed


@pytest.mark.parametrize("case, question", WITH_MUST_MENTION)
def test_answer_without_details_fails_must_mention(case, question):
    groups = case.expected[question]["must_mention"]
    # Right boolean but no justification: every keyword group is missed
    bare = {k: v for k, v in case.gold[question].items() if not isinstance(v, list)}
    result = score_answer(case.case_id, question, bare, case.expected[question])
    assert len(result.errors) == len(groups)


def test_normalize_removes_accents_and_case():
    assert normalize("Épidermoïde État Général") == "epidermoide etat general"


def test_questions_cover_the_four_rcp_questions():
    assert set(RCP_REVIEW_QUESTIONS) == {
        "SurgicalResectionDiscussion",
        "MissingDataForResection",
        "RecordInconsistencies",
        "AnnexDiscordance",
    }
    for model in RCP_REVIEW_QUESTIONS.values():
        assert model.question.strip()
        # The question must not be part of the JSON schema asked to the LLM
        assert "question" not in model.model_json_schema()["properties"]


# ---------------------------------------------------------- agent integration


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_record_exposes_fiche_and_annexes_to_agent_tool(case):
    runtime = MagicMock()
    runtime.context = {"reader": case.to_record(), "logger": MagicMock()}

    markdown = get_mtd_markdown.func(runtime)

    assert markdown.startswith("# Fiche RCP")
    assert case.fiche.strip() in markdown
    for name, annex in case.annexes.items():
        assert f"# Document annexe : {name}" in markdown
        assert annex.strip() in markdown


@pytest.mark.parametrize("case, question", SCORED)
@patch("src.application.agent.agent.Context")
@patch("src.application.agent.agent.create_agent")
@patch("src.application.agent.agent.get_llm_client")
def test_reviewer_agent_answer_is_parsed_and_scored(
    mock_get_llm_client, mock_create_agent, mock_context_cls, case, question
):
    config = MagicMock()
    config.llm.models = "ollama/qwen3:14b"
    model = RCP_REVIEW_QUESTIONS[question]
    # The mocked LLM answers the gold answer, wrapped in a thinking block
    mock_create_agent.return_value.invoke.return_value = {
        "messages": [
            AIMessage(
                f"<think>relecture du dossier</think>"
                f"```json\n{json.dumps(case.gold[question], ensure_ascii=False)}\n```"
            )
        ]
    }

    agent = RCPReviewerAgent(config=config, mtd=case.to_record(), output_format=model)
    answer = agent.ask(model.question)

    # Only the markdown tool is given: no vector database is needed
    assert agent.additionnal_readers == []
    assert mock_create_agent.call_args.kwargs["tools"] == [get_mtd_markdown]
    sent = mock_create_agent.return_value.invoke.call_args.args[0]["messages"]
    assert sent == [{"role": "user", "content": model.question}]
    assert isinstance(answer, model)
    result = score_answer(case.case_id, question, answer, case.expected[question])
    assert result.passed, result.errors
