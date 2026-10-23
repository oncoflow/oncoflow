"""Lexique appris localement à partir des corrections de l'utilisateur.

- ``always`` : formes à masquer partout (identifiant oublié par la détection) ;
- ``never`` : formes à ne jamais masquer (faux positif, ex. « Child-Pugh ») ;
- ``cues`` : nouveaux libellés de champ (« Médecin coordonnateur : ») et type de leur valeur.

Le lexique contient des identifiants réels : il reste dans l'espace de travail local
et ne doit jamais être versionné ni partagé.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .entities import Span
from .rules import DEFAULT_CUES, normalize_cue

PERSON_LABELS = {"NOM", "PRENOM"}


@dataclass
class Lexicon:
    always: dict[str, str] = field(default_factory=dict)
    never: set[str] = field(default_factory=set)
    cues: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def key(form: str) -> str:
        return re.sub(r"\s+", " ", form.strip()).casefold()

    def all_cues(self) -> dict[str, str]:
        return {**DEFAULT_CUES, **self.cues}

    def is_never(self, form: str) -> bool:
        return self.key(form) in self.never

    # --- apprentissage -----------------------------------------------------------

    def learn_added(self, text: str, span: Span) -> None:
        """Un identifiant oublié : on le retient, ainsi que le libellé qui le précède."""
        form = text[span.start : span.end]
        self.never.discard(self.key(form))
        self.always[self.key(form)] = span.label
        cue = preceding_cue(text, span.start)
        if cue and cue not in DEFAULT_CUES:
            self.cues[cue] = "PERSONNE" if span.label in PERSON_LABELS else span.label

    def learn_rejected(self, text: str, span: Span) -> None:
        """Un faux positif : la forme ne sera plus masquée."""
        key = self.key(text[span.start : span.end])
        self.always.pop(key, None)
        self.never.add(key)

    def forget(self, form: str) -> None:
        """Oublie une forme apprise (correction annulée). Les libellés appris sont conservés."""
        key = self.key(form)
        self.always.pop(key, None)
        self.never.discard(key)

    # --- persistance ---------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> "Lexicon":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data.get("always", {}), set(data.get("never", [])), data.get("cues", {}))

    def save(self, path: Path) -> None:
        data = {"always": self.always, "never": sorted(self.never), "cues": self.cues}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def preceding_cue(text: str, start: int) -> str | None:
    """Libellé placé juste avant une valeur : « Libellé : », cellule précédente d'un tableau."""
    line_start = text.rfind("\n", 0, start) + 1
    before = text[line_start:start]
    match = re.search(r"([^|:\n]{2,40}?)\s*(?::|\|)\s*$", before)
    if not match:
        return None
    cue = normalize_cue(match.group(1))
    if not cue or len(cue.split()) > 5 or re.search(r"\d", cue):
        return None
    return cue
