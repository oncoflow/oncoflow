"""Correspondance entre les entités du Markdown et leur position dans le PDF d'origine."""

import re
from collections import defaultdict
from pathlib import Path

import pymupdf


def _needle(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text)
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def page_sizes(pdf_path: Path) -> list[dict]:
    with pymupdf.open(str(pdf_path)) as pdf:
        return [{"width": p.rect.width, "height": p.rect.height} for p in pdf]


def render_page(pdf_path: Path, page: int, zoom: float = 2.0) -> bytes:
    with pymupdf.open(str(pdf_path)) as pdf:
        return pdf[page].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")


def locate(pdf_path: Path, entities: list[dict]) -> dict[int, list[dict]]:
    """Rectangles (en points PDF) de chaque entité, indexés par sa position de début.

    Quand un même texte apparaît plusieurs fois, la n-ième occurrence du Markdown est
    associée à la n-ième occurrence du PDF (ordre de lecture page par page).
    """
    hits_cache: dict[str, list[list[dict]]] = {}
    seen: dict[str, int] = defaultdict(int)
    result: dict[int, list[dict]] = {}
    with pymupdf.open(str(pdf_path)) as pdf:

        def hits(needle: str) -> list[list[dict]]:
            if needle not in hits_cache:
                found = []
                for number, page in enumerate(pdf):
                    for quad in page.search_for(needle, quads=True):
                        r = quad.rect
                        found.append([{"page": number, "x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1}])
                hits_cache[needle] = found
            return hits_cache[needle]

        for entity in sorted(entities, key=lambda e: e["start"]):
            needle = _needle(entity["text"])
            if len(needle) < 2:
                continue
            key = needle.casefold()
            found = hits(needle)
            if not found:  # texte recomposé par la conversion : on cherche mot à mot
                found = [h for word in needle.split() if len(word) >= 3 for h in hits(word)]
                result[entity["start"]] = [rect for hit in found for rect in hit]
                continue
            index = seen[key]
            seen[key] += 1
            result[entity["start"]] = found[index] if index < len(found) else found[-1]
    return result
