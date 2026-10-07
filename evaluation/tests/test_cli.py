"""Tests unitaires pour l'interface CLI run_eval."""

from __future__ import annotations

import sys
from unittest.mock import patch

from evaluation.run_eval import display_results_table, parse_args


def test_parse_args_defaults():
    with patch.object(sys, "argv", ["run_eval.py"]):
        args = parse_args()
        assert args.domain == "oncology"
        assert args.mode == "auto"
        assert args.case_id is None
        assert args.judge_model is None
        assert args.target_class is None


def test_parse_args_custom():
    test_argv = [
        "run_eval.py",
        "--domain",
        "sma",
        "--mode",
        "single_agent",
        "--case-id",
        "sma-01",
        "--agent",
        "neurologist expert",
        "--target-class",
        "PatientAdministrative",
        "--judge-model",
        "gpt-4o",
    ]
    with patch.object(sys, "argv", test_argv):
        args = parse_args()
        assert args.domain == "sma"
        assert args.mode == "single_agent"
        assert args.case_id == "sma-01"
        assert args.agent == "neurologist expert"
        assert args.target_class == "PatientAdministrative"
        assert args.judge_model == "gpt-4o"


def test_display_results_table_no_crash():
    display_results_table([])

    sample_results = [
        {
            "case_id": "onco-01",
            "agent": "pancreas expert",
            "target_class": "PatientAdministrative",
            "metrics": {
                "judge_clinical_faithfulness": 5.0,
                "judge_completeness_awareness": 4.0,
                "judge_tncd_or_pnds_conformance": 5.0,
                "judge_structural_robustness": 5.0,
                "judge_debate_consensus": 4.5,
                "judge_overall_average": 4.7,
            },
        }
    ]
    display_results_table(sample_results)


@patch("evaluation.run_eval.EvaluationRunner")
@patch("evaluation.run_eval.parse_args")
def test_main_live_streaming(mock_parse_args, mock_runner_cls):
    """Verifie le bon deroulement de main() avec l'affichage au fil de l'eau."""
    from unittest.mock import MagicMock
    from evaluation.run_eval import main

    mock_args = MagicMock(
        domain="oncology",
        mode="debate",
        case_id="onco-01",
        agent=None,
        target_class="RadiologicExamType",
        config=None,
        judge_model=None,
    )
    mock_parse_args.return_value = mock_args

    mock_runner = MagicMock()
    mock_runner_cls.return_value = mock_runner
    mock_runner.run_case_evaluation_stream.return_value = [
        {
            "case_id": "onco-01",
            "agent": "MDT Coordinator (Debate Synthesis)",
            "target_class": "RadiologicExams",
            "metrics": {
                "judge_clinical_faithfulness": 5.0,
                "judge_overall_average": 4.8,
            },
            "summary": "OK",
            "prompt_name": "oncoflow_oncology_debate_prompt",
            "status": "success",
        }
    ]

    main()

    mock_runner.run_case_evaluation_stream.assert_called_once_with(
        domain="oncology",
        case_id="onco-01",
        mode="debate",
        target_agent_name=None,
        target_class="RadiologicExamType",
    )
