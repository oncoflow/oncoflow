"""Autoclave : interface web locale de vérification (FastAPI + page statique sans dépendance externe)."""

import json
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .entities import LABELS, SOURCE_NAMES, Span
from .locate import locate, page_sizes, render_page
from .workspace import STATUSES, Annotations, Workspace

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".docx"}
STATIC = files("autoclave") / "static"


class SpanIn(BaseModel):
    start: int
    end: int
    label: str = "AUTRE"
    source: str = "manuel"


class AnnotationsIn(BaseModel):
    added: list[SpanIn] = []
    rejected: list[SpanIn] = []
    relabeled: list[SpanIn] = []


class LexiconIn(BaseModel):
    always: dict[str, str] = {}
    never: list[str] = []
    cues: dict[str, str] = {}


def create_app(workspace: Workspace) -> FastAPI:
    app = FastAPI(title="Autoclave", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    def doc_or_404(doc_id: str) -> str:
        try:
            workspace.meta(doc_id)
        except KeyError:
            raise HTTPException(404, "Document inconnu") from None
        return doc_id

    def pdf_or_404(doc_id: str) -> Path:
        path = workspace.source_path(doc_or_404(doc_id))
        if path.suffix != ".pdf":
            raise HTTPException(404, "Aperçu natif disponible pour les PDF uniquement")
        return path

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/favicon.ico")
    def favicon():
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect x="3" y="5" width="26" height="22" rx="6" fill="none" stroke="#2f5bea" stroke-width="2.4"/><circle cx="16" cy="16" r="6.2" fill="none" stroke="#2f5bea" stroke-width="2.4"/><path d="M16 12.6v6.8M12.6 16h6.8" stroke="#2f5bea" stroke-width="2.4" stroke-linecap="round"/><circle cx="24.5" cy="9.5" r="1.4" fill="#2f5bea"/></svg>'
        return Response(svg, media_type="image/svg+xml")

    @app.get("/api/config")
    def config():
        return {"labels": LABELS, "sources": SOURCE_NAMES, "statuses": STATUSES}

    @app.get("/api/documents")
    def list_documents():
        docs = []
        for doc_id in workspace.ids():
            entities = workspace.entities(doc_id)
            docs.append(
                workspace.meta(doc_id)
                | {
                    "id": doc_id,
                    "entities": sum(e["state"] != "rejected" for e in entities),
                    "manual": sum(e["state"] == "added" for e in entities),
                    "rejected": sum(e["state"] == "rejected" for e in entities),
                }
            )
        return sorted(docs, key=lambda d: d.get("added", ""), reverse=True)

    @app.post("/api/documents")
    async def upload(file: Annotated[UploadFile, File()]):
        name = Path(file.filename or "document").name
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(415, "Formats acceptés : PDF et DOCX")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Fichier trop volumineux (50 Mo maximum)")
        if suffix == ".pdf" and not data.startswith(b"%PDF"):
            raise HTTPException(415, "Ce fichier n'est pas un PDF valide")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"upload{suffix}"
            path.write_bytes(data)
            try:
                doc_id = workspace.add(path, name=name)
            except Exception as error:  # noqa: BLE001 — Docling peut lever des erreurs très variées
                raise HTTPException(422, f"Conversion impossible : {type(error).__name__}") from None
        return {"id": doc_id}

    @app.get("/api/documents/{doc_id}")
    def get_document(doc_id: str):
        doc_or_404(doc_id)
        source = workspace.source_path(doc_id)
        return workspace.meta(doc_id) | {
            "id": doc_id,
            "markdown": workspace.markdown(doc_id),
            "entities": workspace.entities(doc_id),
            "pages": page_sizes(source) if source.suffix == ".pdf" else [],
        }

    @app.delete("/api/documents/{doc_id}")
    def delete_document(doc_id: str):
        workspace.delete(doc_or_404(doc_id))
        return {"ok": True}

    @app.put("/api/documents/{doc_id}/annotations")
    def put_annotations(doc_id: str, body: AnnotationsIn, learn: bool = True):
        doc_or_404(doc_id)
        text = workspace.markdown(doc_id)
        for span in [*body.added, *body.relabeled]:
            if span.label not in LABELS:
                raise HTTPException(422, f"Étiquette inconnue : {span.label}")
        for span in [*body.added, *body.rejected, *body.relabeled]:
            if not 0 <= span.start < span.end <= len(text):
                raise HTTPException(422, "Position hors du document")
        notes = Annotations(
            [Span(s.start, s.end, s.label, "manuel", text[s.start : s.end]) for s in body.added],
            [Span(s.start, s.end, s.label, s.source, text[s.start : s.end]) for s in body.rejected],
            {(s.start, s.end): s.label for s in body.relabeled},
        )
        workspace.save_annotations(doc_id, notes, learn=learn)
        return {"entities": workspace.entities(doc_id)}

    @app.put("/api/documents/{doc_id}/status/{status}")
    def put_status(doc_id: str, status: str):
        doc_or_404(doc_id)
        if status not in STATUSES:
            raise HTTPException(422, "Statut inconnu")
        workspace.set_status(doc_id, status)
        return workspace.meta(doc_id)

    @app.post("/api/documents/{doc_id}/redetect")
    def redetect(doc_id: str):
        workspace.redetect(doc_or_404(doc_id))
        return {"entities": workspace.entities(doc_id)}

    @app.post("/api/redetect")
    def redetect_all():
        return {"documents": workspace.redetect_all()}

    @app.get("/api/documents/{doc_id}/pages/{page}.png")
    def page_image(doc_id: str, page: int, zoom: float = 2.0):
        path = pdf_or_404(doc_id)
        if not 0 <= page < len(page_sizes(path)):
            raise HTTPException(404, "Page inconnue")
        return Response(render_page(path, page, min(max(zoom, 0.5), 4.0)), media_type="image/png")

    @app.get("/api/documents/{doc_id}/locations")
    def locations(doc_id: str):
        path = pdf_or_404(doc_id)
        return locate(path, workspace.entities(doc_id))

    @app.get("/api/documents/{doc_id}/locate")
    def locate_text(doc_id: str, start: int, end: int):
        path = pdf_or_404(doc_id)
        text = workspace.markdown(doc_id)
        if not 0 <= start < end <= len(text):
            raise HTTPException(422, "Position hors du document")
        return locate(path, [{"start": start, "end": end, "text": text[start:end]}]).get(start, [])

    @app.get("/api/documents/{doc_id}/output", response_class=PlainTextResponse)
    def output(doc_id: str, strategy: str = "placeholder"):
        if strategy not in {"placeholder", "surrogate"}:
            raise HTTPException(422, "Stratégie inconnue")
        return workspace.pseudonymized(doc_or_404(doc_id), strategy)[0]

    @app.get("/api/documents/{doc_id}/source")
    def source(doc_id: str):
        path = workspace.source_path(doc_or_404(doc_id))
        return FileResponse(path, filename=workspace.meta(doc_id)["name"])

    @app.get("/api/lexicon")
    def get_lexicon():
        lex = workspace.lexicon
        return {"always": lex.always, "never": sorted(lex.never), "cues": lex.cues}

    @app.put("/api/lexicon")
    def put_lexicon(body: LexiconIn):
        lex = workspace.lexicon
        lex.always, lex.never, lex.cues = dict(body.always), set(body.never), dict(body.cues)
        workspace.save_lexicon()
        return get_lexicon()

    @app.get("/api/export/training.jsonl", response_class=PlainTextResponse)
    def export_training(all_documents: bool = False):
        records = workspace.training_records(only_validated=not all_documents)
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"

    return app
