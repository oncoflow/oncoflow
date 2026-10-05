"""Module de gestion et de synthese des propositions d'amelioration de prompts pour SLM."""

from __future__ import annotations

import difflib
from pathlib import Path


class PromptOptimizer:
    """Analyse les propositions d'amelioration de prompts generees par le juge.

    Produit des rapports de comparaison pour MLflow.
    """

    @staticmethod
    def generate_diff_markdown(
        agent_name: str,
        original_prompt: str,
        suggested_prompt: str,
        optimizations_applied: list[str],
        expected_gain: str,
    ) -> str:
        """Genere un rapport markdown de comparaison avec bloc diff colorise."""
        orig_lines = original_prompt.strip().splitlines(keepends=True)
        sugg_lines = suggested_prompt.strip().splitlines(keepends=True)

        diff = "".join(
            difflib.unified_diff(
                orig_lines,
                sugg_lines,
                fromfile="Prompt_Actuel (v_default)",
                tofile="Prompt_Recommande_SLM (v_optim)",
                n=3,
            )
        )

        optim_bullets = "\n".join(f"- {opt}" for opt in optimizations_applied)

        return f"""# Rapport d'Optimisation de Prompt : {agent_name}

## 🎯 Objectif
Optimisation specifiquement calibree pour les modeles SLM locaux (7B-14B Q4_K_M).

## 🛠️ Optimisations Appliquees
{optim_bullets}

## 📈 Gain Clinique / Technique Attendu
{expected_gain}

## 🔍 Diff Descriptif
```diff
{diff}
```

## 📋 Nouveau Prompt Propose (Pret a l'emploi)
```markdown
{suggested_prompt.strip()}
```
"""

    @staticmethod
    def save_prompt_artifact(
        output_dir: Path,
        agent_name: str,
        case_id: str,
        markdown_content: str,
    ) -> Path:
        """Enregistre le rapport markdown d'amelioration de prompt en artefact local."""
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_agent_name = agent_name.lower().replace(" ", "_")
        filename = f"prompt_opt_{safe_agent_name}_{case_id}.md"
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        return filepath
