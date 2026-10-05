"""Tests unitaires pour PromptOptimizer."""

from __future__ import annotations

from pathlib import Path

from evaluation.engine.prompt_optimizer import PromptOptimizer


def test_generate_diff_markdown():
    orig = "Tu ne dois pas inventer d'information.\nNe mentionne pas la langue."
    sugg = (
        "### INSTRUCTIONS\nInscris uniquement les faits verifiables.\n### FORMAT\nJSON"
    )
    opts = ["Suppression des negations", "Ajout des balises markdown"]
    gain = "Reduction des hallucinations de 30%"

    diff_md = PromptOptimizer.generate_diff_markdown(
        agent_name="pancreas expert",
        original_prompt=orig,
        suggested_prompt=sugg,
        optimizations_applied=opts,
        expected_gain=gain,
    )

    assert "Rapport d'Optimisation de Prompt : pancreas expert" in diff_md
    assert "```diff" in diff_md
    assert "Suppression des negations" in diff_md
    assert "Reduction des hallucinations de 30%" in diff_md
    assert sugg in diff_md


def test_save_prompt_artifact(tmp_path: Path):
    content = "# Test Diff Markdown"
    artifact_path = PromptOptimizer.save_prompt_artifact(
        output_dir=tmp_path,
        agent_name="MDT Coordinator",
        case_id="onco-01",
        markdown_content=content,
    )

    assert artifact_path.exists()
    assert artifact_path.name == "prompt_opt_mdt_coordinator_onco-01.md"
    assert artifact_path.read_text(encoding="utf-8") == content
