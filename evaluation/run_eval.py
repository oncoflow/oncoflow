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

import os  # noqa: E402
import yaml  # noqa: E402

# Pre-configuration de l'environnement MLflow AVANT tout import du domaine applicatif
eval_cfg_file = EVAL_DIR / "config/eval_config.yaml"
if eval_cfg_file.exists():
    try:
        with open(eval_cfg_file, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f) or {}
            mlflow_raw = raw_cfg.get("mlflow", {})
            _t_uri = mlflow_raw.get("tracking_uri", "http://localhost:5000")
            _exp_name = mlflow_raw.get("experiment_name", "oncoflow-agents-evaluation")
            os.environ["MLFLOW_TRACKING_URI"] = _t_uri
            os.environ["MLFLOW_EXPERIMENT_NAME"] = _exp_name
            os.environ["APP_TELEMETRY_ENDPOINT"] = _t_uri
            os.environ["APP_TELEMETRY_EXPERIMENT_NAME"] = _exp_name

            import mlflow

            mlflow.set_tracking_uri(_t_uri)
            try:
                _exp = mlflow.set_experiment(experiment_name=_exp_name)
                _exp_id = str(_exp.experiment_id)
                os.environ["MLFLOW_EXPERIMENT_ID"] = _exp_id
                os.environ["MLFLOW_TRACING_DESTINATION"] = _exp_id
                if hasattr(mlflow, "tracing") and hasattr(
                    mlflow.tracing, "set_destination"
                ):
                    from mlflow.entities.trace_location import (
                        MlflowExperimentLocation,
                    )

                    try:
                        _loc = MlflowExperimentLocation(_exp_id)
                    except TypeError:
                        _loc = MlflowExperimentLocation(experiment_id=_exp_id)

                    try:
                        mlflow.tracing.set_destination(_loc)
                    except Exception:
                        try:
                            mlflow.tracing.set_destination(_loc, context_local=False)
                        except Exception:
                            pass
                    try:
                        mlflow.tracing.set_destination(_loc, context_local=True)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

from evaluation.config.settings import EvaluationSettings  # noqa: E402
from evaluation.engine.runner import EvaluationRunner  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.live import Live  # noqa: E402
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
        choices=["auto", "debate", "single_agent"],
        default="auto",
        help="Mode d'evaluation : 'auto' (mode natif Oncoflow : debat si collaborative=True et >1 agent, agent unitaire sinon), 'debate' (force le debat), 'single_agent' (force l'agent unitaire). Defaut: auto.",
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
        "--target-class",
        "--model-class",
        type=str,
        default=None,
        dest="target_class",
        help="Classe du formulaire Pydantic a evaluer specifiquement (ex: PatientAdministrative, RadiologicExams, RadiologicExamType).",
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


def create_results_table() -> Table:
    table = Table(
        title="[bold green]Résultats d'Évaluation des Agents Oncoflow (Au fil de l'eau & MLflow 3)[/bold green]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Cas ID", style="dim", width=12)
    table.add_column("Agent / Workflow", style="bold", width=28)
    table.add_column("Classe Cible", justify="center", style="yellow")
    table.add_column("Fidélité MTD", justify="center")
    table.add_column("Détection Manques", justify="center")
    table.add_column("Conformité Guide", justify="center")
    table.add_column("Structure JSON", justify="center")
    table.add_column("Consensus Débat", justify="center")
    table.add_column("Note Moyenne", justify="center", style="bold magenta")
    table.add_column("Prompt Registry", justify="center", style="cyan")
    return table


def format_result_row(res: dict) -> list[str]:
    cid = res.get("case_id", "-")
    agent = res.get("agent", "-")
    target_cls = res.get("target_class") or "-"
    m = res.get("metrics", {})
    status = res.get("status", "success")

    def fmt(val):
        if val is None:
            return "-"
        fval = float(val)
        color = "green" if fval >= 4.0 else ("yellow" if fval >= 3.0 else "red")
        return f"[{color}]{fval:.1f}/5[/{color}]"

    if status == "error":
        err_msg = res.get("summary", "Erreur")
        return [
            cid,
            agent,
            str(target_cls),
            "[red]ERREUR[/red]",
            "-",
            "-",
            "-",
            "-",
            "[red]0.0/5[/red]",
            f"[red]{err_msg[:20]}[/red]",
        ]

    faith = fmt(m.get("judge_clinical_faithfulness"))
    comp = fmt(m.get("judge_completeness_awareness"))
    guide = fmt(
        m.get("judge_tncd_or_pnds_conformance") or m.get("judge_guideline_conformance")
    )
    struct = fmt(m.get("judge_structural_robustness"))
    debate = fmt(m.get("judge_debate_consensus"))
    avg = fmt(m.get("judge_overall_average"))
    prompt_reg = (
        "[green]Enregistré[/green]" if res.get("prompt_name") else "[dim]-[/dim]"
    )

    return [
        cid,
        agent,
        str(target_cls),
        faith,
        comp,
        guide,
        struct,
        debate,
        avg,
        prompt_reg,
    ]


def display_results_table(results: list[dict]):
    if not results:
        console.print("[yellow]Aucun resultat a afficher.[/yellow]")
        return

    table = create_results_table()
    for res in results:
        table.add_row(*format_result_row(res))

    console.print(table)


def main():
    args = parse_args()
    settings = EvaluationSettings.from_yaml(args.config)
    if args.judge_model:
        settings.judge.model = args.judge_model
    if args.target_class:
        settings.execution.target_class = args.target_class

    target_cls_display = (
        args.target_class or settings.execution.target_class or "Formulaire complet"
    )

    console.print(
        Panel.fit(
            f"[bold blue]Oncoflow LLM-as-a-Judge Evaluation Suite (MLflow 3)[/bold blue]\n"
            f"[dim]Domaine :[/dim] [bold]{args.domain}[/bold] | "
            f"[dim]Mode :[/dim] [bold]{args.mode}[/bold] | "
            f"[dim]Classe cible :[/dim] [bold yellow]{target_cls_display}[/bold yellow]\n"
            f"[dim]Filtre Cas :[/dim] {args.case_id or 'Tous les cas'}\n"
            f"[dim]Visualisation des traces :[/dim] http://localhost:5000\n"
            f"[dim]Prompt Registry :[/dim] Intégré (versionné par question et par agent)",
            border_style="cyan",
        )
    )

    import os

    os.environ["MLFLOW_TRACKING_URI"] = settings.mlflow.tracking_uri
    os.environ["MLFLOW_EXPERIMENT_NAME"] = settings.mlflow.experiment_name

    from src.infrastructure.telemetry.tracing import ensure_tracing_destination

    ensure_tracing_destination(experiment_name=settings.mlflow.experiment_name)

    runner = EvaluationRunner(settings=settings)

    table = create_results_table()
    results = []

    console.print(
        "\n[bold cyan]Exécution et journalisation au fil de l'eau en cours...[/bold cyan]\n"
    )

    with Live(table, console=console, refresh_per_second=4):
        for res in runner.run_case_evaluation_stream(
            domain=args.domain,
            case_id=args.case_id,
            mode=args.mode,
            target_agent_name=args.agent,
            target_class=args.target_class,
        ):
            results.append(res)
            table.add_row(*format_result_row(res))

    console.print("\n")
    if not results:
        console.print("[yellow]Aucun résultat d'évaluation n'a été produit.[/yellow]")

    console.print(
        Panel(
            "[bold green]Évaluation terminée avec succès ![/bold green]\n"
            "Chaque question et prompt ont été archivés dans le Prompt Registry MLflow.\n"
            "Visualisez les traces, les métriques en temps réel et les diffs de prompts sur l'UI MLflow :\n"
            "[link=http://localhost:5000]http://localhost:5000[/link]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
