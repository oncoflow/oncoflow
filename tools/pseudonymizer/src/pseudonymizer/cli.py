"""Ligne de commande : ``pseudonymizer --help``."""

import argparse
import json
import logging
import sys
from pathlib import Path

DEFAULT_WORKSPACE = Path("~/.pseudonymizer").expanduser()
logger = logging.getLogger("pseudonymizer")


def _detector(args):
    from .detect import Detector, DetectorConfig
    from .lexicon import Lexicon

    config = DetectorConfig(eds_model=args.model)
    lexicon = Lexicon.load(args.workspace / "lexicon.json") if args.workspace else Lexicon()
    return Detector(config, lexicon)


def cmd_convert(args):
    from .convert import convert

    result = convert(args.input, args.engine)
    _write(args.output, result.markdown)
    logger.info("Conversion %s", result.engine)


def cmd_pseudonymize(args):
    from .convert import convert
    from .pseudonymize import pseudonymize

    markdown = convert(args.input, args.engine).markdown
    output, mapping = pseudonymize(markdown, _detector(args).detect(markdown), args.strategy, seed=args.input.name)
    _write(args.output, output)
    if args.mapping:
        args.mapping.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning(
            "Table de correspondance écrite dans %s : elle permet de ré-identifier, protégez-la.", args.mapping
        )


def cmd_add(args):
    from .workspace import Workspace

    workspace = Workspace(args.workspace)
    for path in args.inputs:
        print(workspace.add(path, engine=args.engine))


def cmd_serve(args):
    import uvicorn

    from .detect import DetectorConfig
    from .server import create_app
    from .workspace import Workspace

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        logger.warning(
            "Écoute sur %s : l'interface n'a pas d'authentification, réservez-la à un réseau de confiance.", args.host
        )
    workspace = Workspace(args.workspace, DetectorConfig(eds_model=args.model))
    print(f"Espace de travail : {workspace.root}\nInterface : http://{args.host}:{args.port}")
    uvicorn.run(create_app(workspace), host=args.host, port=args.port, log_level="warning")


def cmd_evaluate(args):
    from .detect import Detector, DetectorConfig
    from .evaluate import evaluate

    configs = {
        "eds-pseudo (règles seules)": DetectorConfig.eds_only(),
        "pseudonymizer": DetectorConfig(eds_model=args.model),
    }
    for name, config in configs.items():
        for suffix in args.formats:
            report = evaluate(args.dataset, Detector(config), f".{suffix}", args.engine)
            print(
                f"{name:28} {suffix:5} documents={report.documents:3} identifiants={report.identifiers:4} "
                f"fuites={len(report.leaks):3} rappel={report.recall:6.1%}  {dict(report.by_label())}"
            )


def cmd_export(args):
    from .workspace import Workspace

    records = Workspace(args.workspace).training_records(only_validated=not args.all)
    _write(args.output, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    logger.info("%d document(s) exporté(s)", len(records))


def _write(path: Path | None, text: str) -> None:
    if path:
        path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pseudonymizer", description="Pseudonymisation locale de documents médicaux.")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, workspace=True):
        p.add_argument("--engine", choices=["auto", "docling", "pymupdf"], default="auto", help="moteur de conversion")
        p.add_argument("--model", help="modèle eds-pseudo local (chemin), en plus des règles")
        if workspace:
            p.add_argument(
                "-w",
                "--workspace",
                type=Path,
                default=DEFAULT_WORKSPACE,
                help="espace de travail (défaut : ~/.pseudonymizer)",
            )

    p = sub.add_parser("convert", help="convertir un PDF/DOCX en Markdown")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path)
    common(p, workspace=False)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("pseudonymize", help="convertir puis pseudonymiser un document")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--strategy", choices=["placeholder", "surrogate"], default="placeholder")
    p.add_argument("--mapping", type=Path, help="écrire la table de correspondance (sensible)")
    common(p)
    p.set_defaults(func=cmd_pseudonymize)

    p = sub.add_parser("add", help="importer des documents dans l'espace de travail")
    p.add_argument("inputs", type=Path, nargs="+")
    common(p)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("serve", help="lancer l'interface web de vérification")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    common(p)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("evaluate", help="mesurer les fuites sur un jeu fictif annoté (manifest.json)")
    p.add_argument("dataset", type=Path)
    p.add_argument("--formats", nargs="+", default=["docx", "pdf"])
    common(p, workspace=False)
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("export", help="exporter les annotations validées (format eds-pseudo)")
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--all", action="store_true", help="inclure les documents non validés")
    common(p)
    p.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    for noisy in ("docling", "RapidOCR", "httpx"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    args.func(args)


if __name__ == "__main__":
    main()
