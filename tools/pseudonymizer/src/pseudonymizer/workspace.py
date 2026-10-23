"""Espace de travail local : documents, détections, annotations et lexique appris.

Arborescence (tout reste sur le poste, jamais dans un dépôt git) ::

    <racine>/
      lexicon.json                 lexique appris (contient des identifiants réels)
      documents/<id>/
        source.pdf | source.docx   document d'origine
        document.md                conversion Markdown (texte de référence des positions)
        meta.json                  nom, moteur de conversion, statut, dates
        detections.json            détections automatiques
        annotations.json           corrections : ajouts, rejets, changements d'étiquette
"""

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .convert import convert
from .detect import Detector, DetectorConfig
from .entities import Span, resolve
from .lexicon import Lexicon
from .pseudonymize import pseudonymize

STATUSES = ("a_verifier", "en_cours", "valide")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Annotations:
    added: list[Span]
    rejected: list[Span]
    relabeled: dict[tuple[int, int], str]

    @classmethod
    def empty(cls) -> "Annotations":
        return cls([], [], {})

    def to_dict(self) -> dict:
        return {
            "added": [s.to_dict() for s in self.added],
            "rejected": [s.to_dict() for s in self.rejected],
            "relabeled": [{"start": s, "end": e, "label": label} for (s, e), label in self.relabeled.items()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Annotations":
        return cls(
            [Span.from_dict({**d, "source": "manuel"}) for d in data.get("added", [])],
            [Span.from_dict({**d, "source": d.get("source", "manuel")}) for d in data.get("rejected", [])],
            {(d["start"], d["end"]): d["label"] for d in data.get("relabeled", [])},
        )


class Workspace:
    def __init__(self, root: Path, config: DetectorConfig | None = None):
        self.root = Path(root).expanduser()
        self.docs_dir = self.root / "documents"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or DetectorConfig()
        self.lexicon = Lexicon.load(self.lexicon_path)
        self.detector = Detector(self.config, self.lexicon)

    @property
    def lexicon_path(self) -> Path:
        return self.root / "lexicon.json"

    def save_lexicon(self) -> None:
        self.lexicon.save(self.lexicon_path)

    # --- documents -----------------------------------------------------------------

    def _dir(self, doc_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_-]{1,80}", doc_id):
            raise KeyError(doc_id)
        path = self.docs_dir / doc_id
        if not path.is_dir():
            raise KeyError(doc_id)
        return path

    @staticmethod
    def _read(path: Path, default):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    @staticmethod
    def _write(path: Path, data) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def add(self, source: Path, name: str | None = None, engine: str = "auto") -> str:
        """Importe, convertit et analyse un document ; renvoie son identifiant."""
        source = Path(source)
        name = Path(name or source.name).name
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
        stem = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")[:50] or "document"
        doc_id = f"{stem}-{digest}"
        folder = self.docs_dir / doc_id
        if folder.exists():
            return doc_id
        folder.mkdir()
        try:
            shutil.copyfile(source, folder / f"source{source.suffix.lower()}")
            converted = convert(source, engine)
            (folder / "document.md").write_text(converted.markdown, encoding="utf-8")
            self._write(
                folder / "meta.json",
                {"name": name, "engine": converted.engine, "status": "a_verifier", "added": _now(), "updated": _now()},
            )
            self.redetect(doc_id)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return doc_id

    def delete(self, doc_id: str) -> None:
        shutil.rmtree(self._dir(doc_id))

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.docs_dir.iterdir() if (p / "meta.json").exists())

    def meta(self, doc_id: str) -> dict:
        return self._read(self._dir(doc_id) / "meta.json", {})

    def set_status(self, doc_id: str, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        meta = self.meta(doc_id) | {"status": status, "updated": _now()}
        self._write(self._dir(doc_id) / "meta.json", meta)

    def source_path(self, doc_id: str) -> Path:
        return next(self._dir(doc_id).glob("source.*"))

    def markdown(self, doc_id: str) -> str:
        return (self._dir(doc_id) / "document.md").read_text(encoding="utf-8")

    # --- détections et annotations -------------------------------------------------

    def redetect(self, doc_id: str) -> list[Span]:
        spans = self.detector.detect(self.markdown(doc_id))
        self._write(self._dir(doc_id) / "detections.json", [s.to_dict() for s in spans])
        return spans

    def redetect_all(self) -> int:
        for doc_id in self.ids():
            self.redetect(doc_id)
        return len(self.ids())

    def detections(self, doc_id: str) -> list[Span]:
        return [Span.from_dict(d) for d in self._read(self._dir(doc_id) / "detections.json", [])]

    def annotations(self, doc_id: str) -> Annotations:
        return Annotations.from_dict(self._read(self._dir(doc_id) / "annotations.json", {}))

    def save_annotations(self, doc_id: str, annotations: Annotations, learn: bool = True) -> None:
        """Enregistre les corrections et, si demandé, en tire des règles pour le lexique."""
        text = self.markdown(doc_id)
        previous = self.annotations(doc_id)
        self._write(self._dir(doc_id) / "annotations.json", annotations.to_dict())
        meta = self.meta(doc_id)
        if meta.get("status") == "a_verifier":
            meta["status"] = "en_cours"
        self._write(self._dir(doc_id) / "meta.json", meta | {"updated": _now()})
        # Une correction annulée ou supprimée est aussi oubliée par le lexique.
        new_added = {s.key() for s in annotations.added}
        new_rejected = {s.key() for s in annotations.rejected}
        for span in previous.added:
            if span.key() not in new_added:
                self.lexicon.forget(text[span.start : span.end])
        for span in previous.rejected:
            if span.key() not in new_rejected:
                self.lexicon.forget(text[span.start : span.end])
        if learn:
            self._learn(text, previous, annotations)
        self.save_lexicon()

    def _learn(self, text: str, previous: Annotations, annotations: Annotations) -> None:
        old_added = {s.key() for s in previous.added}
        old_rejected = {s.key() for s in previous.rejected}
        for span in annotations.added:
            if span.key() not in old_added:
                self.lexicon.learn_added(text, span)
        for span in annotations.rejected:
            if span.key() not in old_rejected:
                self.lexicon.learn_rejected(text, span)

    def entities(self, doc_id: str) -> list[dict]:
        """Détections + corrections, avec l'état de chaque entité pour l'interface."""
        text = self.markdown(doc_id)
        notes = self.annotations(doc_id)
        rejected = {s.key() for s in notes.rejected}
        added = resolve(notes.added, text)
        result = []
        for span in self.detections(doc_id):
            if any(span.overlaps(a) for a in added):
                continue
            label = notes.relabeled.get(span.key(), span.label)
            state = "rejected" if span.key() in rejected else "detected"
            result.append(span.to_dict() | {"label": label, "state": state, "auto_label": span.label})
        result += [s.to_dict() | {"state": "added"} for s in added]
        for r in result:
            r["text"] = text[r["start"] : r["end"]]
        return sorted(result, key=lambda r: r["start"])

    def final_spans(self, doc_id: str) -> list[Span]:
        return [
            Span(e["start"], e["end"], e["label"], e["source"], e["text"])
            for e in self.entities(doc_id)
            if e["state"] != "rejected"
        ]

    def pseudonymized(self, doc_id: str, strategy: str = "placeholder") -> tuple[str, list[dict]]:
        return pseudonymize(self.markdown(doc_id), self.final_spans(doc_id), strategy, seed=doc_id)

    def training_records(self, only_validated: bool = True) -> list[dict]:
        """Documents annotés au format d'entraînement d'eds-pseudo (``scripts/train.py``)."""
        records = []
        for doc_id in self.ids():
            if only_validated and self.meta(doc_id).get("status") != "valide":
                continue
            records.append(
                {
                    "note_id": doc_id,
                    "note_text": self.markdown(doc_id),
                    "entities": [{"start": s.start, "end": s.end, "label": s.label} for s in self.final_spans(doc_id)],
                }
            )
        return records
