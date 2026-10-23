"""Conversion locale d'un document (PDF, DOCX...) en Markdown.

Docling est utilisé en priorité. Pour un PDF, Docling a besoin de ses modèles de mise
en page : s'ils ne sont pas disponibles localement (poste hors ligne), on se replie
sur une extraction PyMuPDF (texte et tableaux), moins fidèle mais entièrement locale.
Aucun appel réseau n'est autorisé : Hugging Face est forcé en mode hors ligne.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DOCLING_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".md", ".txt"}


@dataclass
class Converted:
    markdown: str
    engine: str  # "docling" ou "pymupdf"


def _docling(path: Path) -> str:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False  # les fiches RCP sont des PDF natifs ; l'OCR nécessiterait d'autres modèles
    artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH")
    if artifacts:
        options.artifacts_path = artifacts
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    return converter.convert(str(path)).document.export_to_markdown()


def _text_flags() -> int:
    import pymupdf

    return pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES  # « fi » plutôt que « ﬁ »


def _cell_text(page, bbox) -> str:
    """Texte d'une cellule, mot par mot (l'extraction de tableau de PyMuPDF perd parfois les espaces)."""
    if bbox is None:
        return ""
    words = page.get_text("words", clip=bbox, sort=True, flags=_text_flags())
    return " ".join(w[4] for w in words).replace("|", "/")


def _table_markdown(page, table) -> str:
    rows = [[_cell_text(page, cell) for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    lines = ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
    lines.insert(1, "|" + "---|" * width)
    return "\n".join(lines)


def _pymupdf(path: Path) -> str:
    import pymupdf

    parts = []
    with pymupdf.open(str(path)) as pdf:
        for page in pdf:
            tables = page.find_tables().tables
            boxes = [pymupdf.Rect(t.bbox) for t in tables]
            items = [(t.bbox[1], _table_markdown(page, t)) for t in tables]
            for block in page.get_text("blocks", sort=True, flags=_text_flags()):
                rect = pymupdf.Rect(block[:4])
                if block[6] == 0 and not any(rect.intersects(b) for b in boxes):
                    items.append((block[1], " ".join(block[4].split())))
            parts += [text for _, text in sorted(items, key=lambda item: item[0]) if text]
    return "\n\n".join(parts) + "\n"


def convert(path: Path, engine: str = "auto") -> Converted:
    """Convertit ``path`` en Markdown avec ``engine`` : "auto", "docling" ou "pymupdf"."""
    path = Path(path)
    if engine in {"auto", "docling"} and path.suffix.lower() in DOCLING_SUFFIXES:
        try:
            return Converted(_docling(path), "docling")
        except Exception as error:  # modèles absents, document illisible...
            if engine == "docling" or path.suffix.lower() != ".pdf":
                raise
            logger.warning("Docling indisponible pour %s (%s) : repli sur PyMuPDF", path.name, error)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Format non pris en charge sans Docling : {path.suffix}")
    return Converted(_pymupdf(path), "pymupdf")
