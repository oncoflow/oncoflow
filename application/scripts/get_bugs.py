import argparse
import json
import os
import sys
from datetime import datetime

# Ajout du dossier application au PYTHONPATH
script_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.abspath(os.path.join(script_dir, ".."))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from src.application.config import AppConfig  # noqa: E402
from src.domain.bug_report import BugCategory, BugSeverity, BugStatus  # noqa: E402
from src.infrastructure.documents.mongodb import Mongodb  # noqa: E402

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

SEVERITY_COLORS = {
    BugSeverity.critical.value: RED,
    BugSeverity.high.value: RED,
    BugSeverity.medium.value: YELLOW,
    BugSeverity.low.value: GREEN,
}

STATUS_COLORS = {
    BugStatus.open.value: RED,
    BugStatus.in_progress.value: YELLOW,
    BugStatus.resolved.value: GREEN,
    BugStatus.closed.value: DIM,
}


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def format_bugs_report(bugs: list[dict]) -> str:
    """Formate la liste des rapports de bugs pour un affichage lisible dans le terminal."""
    category_labels = {k.value: v for k, v in BugCategory.labels().items()}
    severity_labels = {k.value: v for k, v in BugSeverity.labels().items()}
    status_labels = {k.value: v for k, v in BugStatus.labels().items()}

    if not bugs:
        return f"{GREEN}Aucun rapport de bug trouvé dans MongoDB.{RESET}"

    open_count = sum(1 for b in bugs if b.get("status") == BugStatus.open.value)
    in_progress_count = sum(
        1 for b in bugs if b.get("status") == BugStatus.in_progress.value
    )
    resolved_count = sum(
        1
        for b in bugs
        if b.get("status") in (BugStatus.resolved.value, BugStatus.closed.value)
    )

    lines = [
        f"{BOLD}{CYAN}=== Rapports de bugs Oncoflow ({len(bugs)} total : "
        f"{RED}{open_count} ouvert(s){CYAN}, "
        f"{YELLOW}{in_progress_count} en cours{CYAN}, "
        f"{GREEN}{resolved_count} résolu(s)/fermé(s){CYAN}) ==={RESET}",
        "",
    ]

    for idx, bug in enumerate(bugs, start=1):
        bug_id = bug.get("bug_id", "unknown")
        title = bug.get("title", "Sans titre")
        sev = bug.get("severity", BugSeverity.medium.value)
        stat = bug.get("status", BugStatus.open.value)
        cat = bug.get("category", BugCategory.other.value)
        created_at = bug.get("created_at")
        date_str = (
            created_at.strftime("%Y-%m-%d %H:%M")
            if isinstance(created_at, datetime)
            else str(created_at or "Inconnue")
        )

        sev_color = SEVERITY_COLORS.get(sev, CYAN)
        stat_color = STATUS_COLORS.get(stat, CYAN)
        sev_label = severity_labels.get(sev, sev)
        stat_label = status_labels.get(stat, stat)
        cat_label = category_labels.get(cat, cat)

        lines.append(
            f"{BOLD}[{idx}] {bug_id}{RESET} — {BOLD}{title}{RESET} "
            f"[{stat_color}{stat_label}{RESET}] "
            f"[{sev_color}Sévérité: {sev_label}{RESET}]"
        )
        meta = [
            f"Catégorie: {cat_label}",
            f"Date: {date_str}",
            f"Auteur: {bug.get('reporter') or 'anonymous'}",
        ]
        if bug.get("page"):
            meta.append(f"Page: {bug['page']}")
        if bug.get("patient_id"):
            meta.append(f"Patient: {bug['patient_id']}")
        if bug.get("rcp_file"):
            meta.append(f"Fichier RCP: {bug['rcp_file']}")

        lines.append(f"    {DIM}{' | '.join(meta)}{RESET}")
        lines.append(f"    Description : {bug.get('description', '')}")
        if bug.get("steps_to_reproduce"):
            lines.append(f"    Reproduction: {bug['steps_to_reproduce']}")
        lines.append("-" * 80)

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Récupère et affiche les rapports de bugs stockés dans MongoDB."
    )
    parser.add_argument(
        "--status",
        choices=[s.value for s in BugStatus],
        default=None,
        help="Filtrer par statut (open, in_progress, resolved, closed)",
    )
    parser.add_argument(
        "--severity",
        choices=[s.value for s in BugSeverity],
        default=None,
        help="Filtrer par sévérité (low, medium, high, critical)",
    )
    parser.add_argument(
        "--category",
        choices=[c.value for c in BugCategory],
        default=None,
        help="Filtrer par catégorie",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Afficher la sortie au format JSON",
    )
    args = parser.parse_args(argv)

    app_conf = AppConfig()
    # Désactiver les logs verbeux sur stdout lors de l'exécution CLI
    app_conf.logs.level = "ERROR"

    filter_query: dict = {}
    if args.status:
        filter_query["status"] = args.status
    if args.severity:
        filter_query["severity"] = args.severity
    if args.category:
        filter_query["category"] = args.category

    try:
        db = Mongodb(app_conf)
        try:
            bugs = db.get_all_bug_reports(filter_query=filter_query)
        finally:
            db.close()
    except Exception as e:
        print(
            f"{RED}Erreur de connexion à MongoDB ({app_conf.mongodb.host}:{app_conf.mongodb.port}) : {e}{RESET}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        clean_bugs = [{k: v for k, v in b.items() if k != "_id"} for b in bugs]
        print(
            json.dumps(clean_bugs, indent=2, ensure_ascii=False, default=_json_default)
        )
    else:
        print(format_bugs_report(bugs))

    return 0


if __name__ == "__main__":
    sys.exit(main())
