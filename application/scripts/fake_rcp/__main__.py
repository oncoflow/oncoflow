import argparse
from pathlib import Path

from . import FORMATS, generate_dataset
from .centers import CENTERS
from .pathologies import PATHOLOGIES


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.fake_rcp",
        description="Génère des fiches RCP fictives (Word et PDF) de plusieurs centres inventés, "
        "avec un manifest.json de vérité terrain (pièces manquantes, demandes préalables, quorum).",
    )
    parser.add_argument(
        "-n", "--count", type=int, default=10, help="nombre de dossiers (défaut : 10)"
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("ressources/PatientMDTForm/fictifs"),
        help="dossier de sortie (défaut : ressources/PatientMDTForm/fictifs, ignoré par git)",
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="graine pour un jeu reproductible"
    )
    parser.add_argument(
        "--centers",
        nargs="+",
        choices=sorted(CENTERS),
        help="centres à utiliser (défaut : tous)",
    )
    parser.add_argument(
        "--pathologies",
        nargs="+",
        choices=sorted(PATHOLOGIES),
        help="pathologies à utiliser (défaut : toutes)",
    )
    parser.add_argument(
        "--formats", nargs="+", choices=sorted(FORMATS), default=["docx", "pdf"]
    )
    parser.add_argument(
        "--stage",
        choices=["pre", "post"],
        help="pre : demande avant RCP, post : compte rendu (défaut : mélange)",
    )
    parser.add_argument(
        "--missing-rate",
        type=float,
        default=0.2,
        help="probabilité qu'un élément du dossier manque (défaut : 0.2)",
    )
    args = parser.parse_args()

    cases = generate_dataset(
        args.out,
        count=args.count,
        seed=args.seed,
        centers=args.centers,
        pathologies=args.pathologies,
        formats=tuple(args.formats),
        stage=args.stage,
        missing_rate=args.missing_rate,
    )
    print(f"{len(cases)} dossiers fictifs générés dans {args.out} (voir manifest.json)")


if __name__ == "__main__":
    main()
