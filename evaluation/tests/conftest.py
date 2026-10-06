"""Configuration Pytest pour la suite d'evaluation Oncoflow."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = EVAL_DIR.parent
APP_DIR = ROOT_DIR / "application"

# Nettoyage automatique du sous-dossier legacy evaluation/src
legacy_src = EVAL_DIR / "src"
if legacy_src.is_dir():
    shutil.rmtree(legacy_src, ignore_errors=True)

# Retrait d'EVAL_DIR de sys.path
for eval_p in [str(EVAL_DIR), str(EVAL_DIR.resolve())]:
    while eval_p in sys.path:
        sys.path.remove(eval_p)

# Insertion prioritaire
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(1, str(ROOT_DIR))

os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5000"
os.environ["JUDGE_BASE_URL"] = "http://localhost:4000/v1"
os.environ["JUDGE_API_KEY"] = "test-key"
os.environ["JUDGE_MODEL"] = "test-judge-model"


@pytest.fixture
def sample_judge_response():
    return {
        "domain": "oncology",
        "agent_name": "pancreas expert",
        "evaluated_case_id": "onco-01",
        "scores": {
            "clinical_faithfulness": {
                "score": 5,
                "justification": "Parfait ancrage sur le document.",
            },
            "completeness_awareness": {
                "score": 4,
                "justification": "Bilan biologique manquant bien detecte.",
            },
            "tncd_or_pnds_conformance": {
                "score": 5,
                "justification": "Recommandations conformes TNCD.",
            },
            "structural_robustness": {
                "score": 5,
                "justification": "Schema JSON immacule.",
            },
            "debate_consensus": {
                "score": 4,
                "justification": "Avis pertinent pour le consensus.",
            },
        },
        "identified_hallucinations": [],
        "identified_missing_data_errors": [],
        "prompt_optimization": {
            "slm_failure_diagnostics": "Le modele a hesite sur les cles de statut OMS.",
            "suggested_prompt": "### ROLE\nTu es un medecin expert.\n### FORMAT\n{schema}",
            "slm_optimizations_applied": ["Directives affirmatives"],
            "expected_gain": "Suppression des retries",
        },
        "overall_clinical_summary": "Excellente analyse d'ensemble.",
    }
