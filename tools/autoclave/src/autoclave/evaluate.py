"""Évaluation sur un jeu de fiches fictives dont on connaît les identifiants.

Le jeu est produit par le générateur d'Oncoflow (``application/scripts/fake_rcp``) : son
``manifest.json`` liste, pour chaque document, les valeurs identifiantes qu'il contient.
On mesure ce qui subsiste dans le texte pseudonymisé (fuites).
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .convert import convert
from .detect import Detector
from .pseudonymize import MONTHS, pseudonymize


def _variants(label: str, value: str) -> list[str]:
    """Formes sous lesquelles une valeur peut apparaître dans un document."""
    if label in {"DATE_NAISSANCE", "DATE"}:
        d = date.fromisoformat(value)
        return [value, d.strftime("%d/%m/%Y"), f"{d.day} {MONTHS[d.month - 1]} {d.year}"]
    return [value]


def _present(text: str, variant: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(variant)}(?![\w-])", text, re.IGNORECASE) is not None


@dataclass
class Report:
    documents: int = 0
    identifiers: int = 0
    leaks: list[dict] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return 1 - len(self.leaks) / self.identifiers if self.identifiers else 1.0

    def by_label(self) -> Counter:
        return Counter(leak["label"] for leak in self.leaks)

    def by_center(self) -> Counter:
        return Counter(leak["center"] for leak in self.leaks)


def evaluate(dataset: Path, detector: Detector, suffix: str = ".pdf", engine: str = "auto") -> Report:
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    report = Report()
    for entry in manifest:
        name = next((f for f in entry["files"] if f.endswith(suffix)), None)
        if name is None:
            continue
        markdown = convert(dataset / name, engine).markdown
        output, _ = pseudonymize(markdown, detector.detect(markdown))
        report.documents += 1
        for identifier in entry["identifiers"]:
            variants = [v for v in _variants(identifier["label"], identifier["value"]) if _present(markdown, v)]
            if not variants:
                continue  # valeur absente du document converti
            report.identifiers += 1
            leaked = [v for v in variants if _present(output, v)]
            if leaked:
                report.leaks.append({**identifier, "file": name, "center": entry["center"], "found": leaked[0]})
    return report
