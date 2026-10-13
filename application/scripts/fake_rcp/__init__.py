"""Générateur de fiches RCP fictives (Word et PDF) issues de plusieurs centres inventés.

Usage : ``uv run python -m scripts.fake_rcp --help`` depuis le dossier ``application``.
"""

import json
import random
from pathlib import Path

from .centers import CENTERS
from .generator import CaseGenerator
from .model import FakeCase
from .pathologies import PATHOLOGIES
from .render import to_docx, to_pdf

FORMATS = {"docx": to_docx, "pdf": to_pdf}


def generate_dataset(
    out_dir: Path,
    count: int = 10,
    seed: int = 0,
    centers: list[str] | None = None,
    pathologies: list[str] | None = None,
    formats: tuple[str, ...] = ("docx", "pdf"),
    stage: str | None = None,
    missing_rate: float = 0.2,
) -> list[FakeCase]:
    """Génère ``count`` dossiers fictifs dans ``out_dir`` et un ``manifest.json`` de vérité terrain.

    Les centres et pathologies sont parcourus en alternance pour garantir la diversité.
    """
    centers = centers or list(CENTERS)
    pathologies = pathologies or list(PATHOLOGIES)
    out_dir.mkdir(parents=True, exist_ok=True)
    generator = CaseGenerator(seed=seed, missing_rate=missing_rate)
    order = random.Random(seed).sample(pathologies, len(pathologies))

    cases, manifest = [], []
    for n in range(count):
        center_id = centers[n % len(centers)]
        pathology_id = order[n % len(order)]
        case_id = f"fictif_{center_id}_{pathology_id}_{n + 1:03d}"
        case = generator.generate(case_id, center_id, pathology_id, stage=stage)
        document = CENTERS[center_id].render(case)
        files = []
        for fmt in formats:
            path = out_dir / f"{case_id}.sample.{fmt}"
            FORMATS[fmt](document, path)
            files.append(path.name)
        cases.append(case)
        manifest.append({"files": files, **case.ground_truth()})

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cases
