"""Tests unitaires pour l'interface CLI run_eval."""

from __future__ import annotations

import sys
from unittest.mock import patch

from evaluation.run_eval import display_results_table, parse_args


def test_parse_args_defaults():
    with patch.object(sys, "argv", ["run_eval.py"]):
        args = parse_args()
        assert args.domain == "oncology"
        assert args.mode == "debate"
        assert args.case_id is None
        assert args.judge_model is None


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
        "--judge-model",
        "gpt-4o",
    ]
    with patch.object(sys, "argv", test_argv):
        args = parse_args()
        assert args.domain == "sma"
        assert args.mode == "single_agent"
        assert args.case_id == "sma-01"
        assert args.agent == "neurologist expert"
        assert args.judge_model == "gpt-4o"


def test_display_results_table_no_crash():
    display_results_table([])

    sample_results = [
        {
            "case_id": "onco-01",
            "agent": "pancreas expert",
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
