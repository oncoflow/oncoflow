#!/usr/bin/env python3
"""Point d'entree CLI pour lancer l'evaluation des agents Oncoflow avec MLflow.

Exemples d'utilisation :
  python evaluation/run_eval.py --domain oncology --mode debate
  python evaluation/run_eval.py --domain oncology --case-id onco-01
  python evaluation/run_eval.py --domain sma --mode debate
  python evaluation/run_eval.py --domain oncology --mode single_agent --agent "pancreas expert"
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

# Resolution des chemins : nettoyage des conflits de package et injection prioritaire
EVAL_DIR = Path(__file__).resolve().parent
ROOT_DIR = EVAL_DIR.parent
APP_DIR = ROOT_DIR / "application"

# 1. Suppression definitive de l'ancien sous-dossier evaluation/src pour eviter tout masquage
legacy_src = EVAL_DIR / "src"
if legacy_src.is_dir():
    shutil.rmtree(legacy_src, ignore_errors=True)

# 2. Retrait d'EVAL_DIR de sys.path s'il y a ete insere automatiquement par l'interpreteur
for eval_p in [str(EVAL_DIR), str(EVAL_DIR.resolve())]:
    while eval_p in sys.path:
        sys.path.remove(eval_p)

# 3. Insertion prioritaire d'APP_DIR (qui contient le vrai package src) et de ROOT_DIR
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(1, str(ROOT_DIR))

from evaluation.config.settings import EvaluationSettings  # noqa: E402
from evaluation.engine.runner import EvaluationRunner  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("OncoflowEval.CLI")
console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Banc d'evaluation LLM-as-a-Judge pour les agents Oncoflow avec MLflow."
    )
    parser.add_argument(
        "--domain",
        choices=["oncology", "sma"],
        default="oncology",
        help="Domaine clinique a evaluer (oncology ou sma). Defaut: oncology.",
    )
    parser.add_argument(
        "--mode",
        choices=["debate", "single_agent"],
        default="debate",
        help="Mode d'evaluation : 'debate' (workflow RCP collaboratif) ou 'single_agent' (extraction unitaire).",
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default=None,
        help="Identifiant d'un cas precis a evaluer (ex: onco-01, onco-02). Si omis, evalue tous les cas.",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="Nom exact de l'agent a evaluer en mode single_agent (ex: 'pancreas expert', 'Administrative').",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Chemin alternatif vers eval_config.yaml.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Surcharge du modele utilise par LiteLLM pour le juge (ex: claude-3-7-sonnet, gpt-4o).",
    )
    return parser.parse_args()


def display_results_table(results: list[dict]):
    if not results:
        console.print("[yellow]Aucun resultat a afficher.[/yellow]")
        return

    table = Table(
        title="[bold green]Résultats d'Évaluation des Agents Oncoflow (LLM-as-a-Judge)[/bold green]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Cas ID", style="dim", width=12)
    table.add_column("Agent / Workflow", style="bold", width=32)
    table.add_column("Fidélité MTD", justify="center")
    table.add_column("Détection Manques", justify="center")
    table.add_column("Conformité Guide", justify="center")
    table.add_column("Structure JSON", justify="center")
    table.add_column("Consensus Débat", justify="center")
    table.add_column("Note Moyenne", justify="center", style="bold magenta")

    for res in results:
        cid = res["case_id"]
        agent = res["agent"]
        m = res.get("metrics", {})

        def fmt(val):
            if val is None:
                return "-"
            fval = float(val)
            color = "green" if fval >= 4.0 else ("yellow" if fval >= 3.0 else "red")
            return f"[{color}]{fval:.1f}/5[/{color}]"

        faith = fmt(m.get("judge_clinical_faithfulness"))
        comp = fmt(m.get("judge_completeness_awareness"))
        guide = fmt(
            m.get("judge_tncd_or_pnds_conformance")
            or m.get("judge_guideline_conformance")
        )
        struct = fmt(m.get("judge_structural_robustness"))
        debate = fmt(m.get("judge_debate_consensus"))
        avg = fmt(m.get("judge_overall_average"))

        table.add_row(cid, agent, faith, comp, guide, struct, debate, avg)

    console.print(table)


def main():
    args = parse_args()

    console.print(
        Panel.fit(
            f"[bold blue]Oncoflow LLM-as-a-Judge Evaluation Suite[/bold blue]\n"
            f"[dim]Domaine :[/dim] [bold]{args.domain}[/bold] | "
            f"[dim]Mode :[/dim] [bold]{args.mode}[/bold] | "
            f"[dim]Filtre Cas :[/dim] {args.case_id or 'Tous les cas'}\n"
            f"[dim]Visualisation des traces :[/dim] http://localhost:5000",
            border_style="cyan",
        )
    )

    settings = EvaluationSettings.from_yaml(args.config)
    if args.judge_model:
        settings.judge.model = args.judge_model

    runner = EvaluationRunner(settings=settings)

    with console.status(
        "[bold green]Exécution de l'évaluation en cours (Inférence + Juge Frontière)..."
    ):
        results = runner.run_case_evaluation(
            domain=args.domain,
            case_id=args.case_id,
            mode=args.mode,
            target_agent_name=args.agent,
        )

    console.print("\n")
    display_results_table(results)

    console.print(
        Panel(
            "[bold green]Évaluation terminée avec succès ![/bold green]\n"
            "Consultez les graphiques, les métriques comparatives et les diffs de prompts sur l'UI MLflow :\n"
            "[link=http://localhost:5000]http://localhost:5000[/link]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
