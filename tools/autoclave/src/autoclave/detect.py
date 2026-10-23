"""Détection des identifiants : eds-pseudo + règles complémentaires + lexique appris."""

import logging
import os
import re
from dataclasses import dataclass, field
from functools import cached_property

from .entities import LABELS, Span, resolve
from .lexicon import Lexicon
from .rules import cue_spans, find_forms, pattern_spans, propagate

logger = logging.getLogger(__name__)

EDS_RULE_KEYS = ["TEL", "MAIL", "SECU", "PERSON", "IPP", "NDA", "RPPS"]


@dataclass
class DetectorConfig:
    use_eds_rules: bool = True
    # Chemin local (ou nom sur le hub) d'un modèle eds-pseudo entraîné, ex. AP-HP/eds-pseudo-public.
    eds_model: str | None = None
    use_cues: bool = True
    use_patterns: bool = True
    use_propagation: bool = True
    use_filters: bool = True
    labels: set[str] = field(default_factory=lambda: set(LABELS))

    @classmethod
    def eds_only(cls) -> "DetectorConfig":
        """Règles d'eds-pseudo seules, sans les compléments : sert de référence en évaluation."""
        return cls(use_cues=False, use_patterns=False, use_propagation=False, use_filters=False)


class Detector:
    def __init__(self, config: DetectorConfig | None = None, lexicon: Lexicon | None = None):
        self.config = config or DetectorConfig()
        self.lexicon = lexicon or Lexicon()

    @cached_property
    def eds_rules(self):
        import edsnlp

        nlp = edsnlp.blank("eds")
        nlp.add_pipe("eds.normalizer")
        nlp.add_pipe("eds_pseudo.simple_rules", config={"pattern_keys": EDS_RULE_KEYS})
        nlp.add_pipe("eds_pseudo.addresses")
        nlp.add_pipe("eds_pseudo.dates")
        return nlp

    @cached_property
    def eds_model(self):
        import edsnlp

        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # jamais de téléchargement implicite
        logger.info("Chargement du modèle eds-pseudo %s", self.config.eds_model)
        return edsnlp.load(self.config.eds_model)

    @staticmethod
    def _from_doc(doc, source: str) -> list[Span]:
        return [Span(e.start_char, e.end_char, e.label_, source) for e in doc.ents if e.label_ in LABELS]

    def _plausible(self, text: str, span: Span) -> bool:
        if self.lexicon.is_never(text[span.start : span.end]):
            return False
        # Un « nom » suivi de deux-points est un libellé de champ (« DDN: », « SEXE : »).
        if self.config.use_filters and span.label in {"NOM", "PRENOM"} and span.source != "lexique":
            return re.match(r"[ \t]*:", text[span.end :]) is None
        return True

    def detect(self, text: str) -> list[Span]:
        """Entités identifiantes du texte, sans chevauchement, triées par position."""
        spans: list[Span] = []
        if self.config.use_eds_rules:
            spans += self._from_doc(self.eds_rules(text), "eds-pseudo")
        if self.config.eds_model:
            spans += self._from_doc(self.eds_model(text), "eds-pseudo-ml")
        if self.config.use_cues:
            spans += cue_spans(text, self.lexicon.all_cues())
        if self.config.use_patterns:
            spans += pattern_spans(text)
        spans += find_forms(text, self.lexicon.always.items(), "lexique", require_capital=False)

        spans = [s for s in spans if self._plausible(text, s)]
        if self.config.use_propagation:
            spans += [s for s in propagate(text, resolve(spans, text)) if self._plausible(text, s)]
        return [s for s in resolve(spans, text) if s.label in self.config.labels]
