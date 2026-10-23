"""Règles complémentaires à eds-pseudo, pensées pour les fiches structurées.

eds-pseudo repère bien les noms précédés d'une civilité (« Dr », « Mme »...), les dates,
les téléphones ou les courriels dans du texte rédigé. Sur des fiches de RCP, une grande
partie des identifiants est en revanche rangée dans des champs (« Nom : X »,
tableaux « | Patient | X | ») sans civilité : ces règles exploitent ces repères, puis
propagent chaque identifiant trouvé à ses autres occurrences dans le document.
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator

from .entities import Span

# --- Repères de champ ---------------------------------------------------------------

# PERSONNE : la valeur est découpée en NOM (majuscules) et PRENOM (initiale majuscule).
DEFAULT_CUES: dict[str, str] = {
    **dict.fromkeys(
        [
            "patient",
            "patiente",
            "nom du patient",
            "nom et prenom",
            "nom prenom",
            "identite",
            "medecin",
            "medecin traitant",
            "medecin demandeur",
            "medecin presentateur",
            "medecin referent",
            "medecin responsable",
            "demandeur",
            "presentateur",
            "referent",
            "adresse par",
            "mt",
            "redacteur",
            "signataire",
            "praticien",
            "interne",
            "correspondant",
        ],
        "PERSONNE",
    ),
    **dict.fromkeys(["nom", "nom de naissance", "nom d'usage", "nom marital", "nom de jeune fille"], "NOM"),
    **dict.fromkeys(["prenom", "prenoms"], "PRENOM"),
    **dict.fromkeys(["date de naissance", "ne le", "nee le", "ddn", "naissance", "dn"], "DATE_NAISSANCE"),
    **dict.fromkeys(["adresse", "domicile", "adresse postale", "demeurant"], "ADRESSE"),
    **dict.fromkeys(["ville", "commune", "lieu de naissance", "localite"], "VILLE"),
    **dict.fromkeys(["code postal", "cp"], "ZIP"),
    **dict.fromkeys(
        [
            "ipp",
            "nip",
            "n dossier",
            "no dossier",
            "numero de dossier",
            "n de dossier",
            "n patient",
            "numero patient",
            "id patient",
            "identifiant patient",
            "n ipp",
        ],
        "IPP",
    ),
    **dict.fromkeys(["nda", "n sejour", "numero de sejour", "n de sejour", "n venue"], "NDA"),
    **dict.fromkeys(
        ["nir", "n securite sociale", "numero de securite sociale", "n de securite sociale", "n ss"], "SECU"
    ),
    **dict.fromkeys(["tel", "telephone", "portable", "tel portable"], "TEL"),
    **dict.fromkeys(["mail", "courriel", "e mail", "email"], "MAIL"),
}

TITLES = r"(?:Dr|Docteur|Pr|Professeur|M|Mr|Mme|Mlle|Madame|Monsieur|Mademoiselle)\.?"
_DATE = (
    r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}(?:er)?\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre"
    r"|d[ée]cembre)\s+\d{4}"
)
DATE_RE = re.compile(_DATE, re.IGNORECASE)
_UPPER = "A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ"
_WORD = rf"[{_UPPER}][\w'’-]*"
_LINK = r"(?:de|du|des|d'|d’|la|le|les|l'|l’|sur|sous|en|lès|les|aux|et)"


def normalize_cue(text: str) -> str:
    """« Né(e) le : » et « NE_LE » donnent tous deux « ne le »."""
    text = re.sub(r"<br\s*/?>", " ", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"\((?:e|s|es)\)", "", text.casefold())
    text = re.sub(r"[_\-°.*#]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" :|\t")


class CueIndex:
    """Recherche de repères tolérante aux espaces perdus par l'extraction (« Nomdenaissance »)."""

    def __init__(self, cues: dict[str, str]):
        self.cues = {normalize_cue(k): v for k, v in cues.items()}
        self.compact = {k.replace(" ", ""): v for k, v in self.cues.items()}

    def get(self, label: str) -> str | None:
        key = normalize_cue(label)
        return self.cues.get(key) or self.compact.get(key.replace(" ", "")) if key else None

    def __contains__(self, label: str) -> bool:
        return self.get(label) is not None


def _strip(text: str, start: int, end: int) -> tuple[int, int]:
    """Réduit [start, end[ en retirant espaces et ponctuation de bord."""
    while start < end and text[start] in " \t*_:;,.|":
        start += 1
    while end > start and text[end - 1] in " \t*_:;,|":
        end -= 1
    return start, end


def _value_spans(text: str, start: int, end: int, kind: str) -> Iterator[Span]:
    """Transforme la valeur d'un champ en entités selon le type du repère."""
    start, end = _strip(text, start, end)
    if end <= start:
        return
    value = text[start:end]
    if kind == "DATE_NAISSANCE":
        match = DATE_RE.search(value)
        if match:
            yield Span(start + match.start(), start + match.end(), kind, "repere")
    elif kind in {"IPP", "NDA", "SECU", "TEL"}:
        match = re.search(r"[\dA-Z][\dA-Z .-]{3,}[\dA-Z]|\d{4,}", value)
        if match:
            yield Span(start + match.start(), start + match.end(), kind, "repere")
    elif kind == "VILLE":
        zip_match = re.match(r"(\d{5})\s+", value)
        if zip_match:
            yield Span(start, start + 5, "ZIP", "repere")
            start += zip_match.end()
        yield Span(start, end, kind, "repere")
    elif kind in {"PERSONNE", "NOM", "PRENOM"}:
        yield from _person_spans(text, start, end, kind)
    else:
        yield Span(start, end, kind, "repere")


def _person_spans(text: str, start: int, end: int, kind: str) -> Iterator[Span]:
    """Découpe « Dr Sylvie GIMENEZ », « NORMAND, Richard » ou « THIERRY » en NOM / PRENOM."""
    value = text[start:end]
    cut = re.search(r"[(\[]|\s[-–—]\s", value)  # « Dr X (Urologie) »
    if cut:
        value = value[: cut.start()]
    tokens = [m for m in re.finditer(r"[\w'’-]+\.?", value) if not re.fullmatch(TITLES, m.group())]
    tokens = [m for m in tokens if m.group()[0].isalpha()]
    if not tokens:
        return
    if len(tokens) == 1 and kind != "PERSONNE":
        m = tokens[0]
        yield Span(start + m.start(), start + m.end(), kind, "repere")
        return
    for m in tokens:
        word = m.group().rstrip(".")
        if not word[0].isupper():
            continue
        if word.isupper() and len(word) > 1:
            label = "NOM"
        else:
            label = "PRENOM" if kind != "NOM" else "NOM"
        yield Span(start + m.start(), start + m.start() + len(word), label, "repere")


def _table_rows(lines: list[tuple[int, str]]) -> Iterator[tuple[list[tuple[int, int]], bool, list[str] | None]]:
    """Itère sur les lignes de tableau markdown : (cellules, est_entête, entêtes courantes)."""
    header: list[str] | None = None
    previous_was_table = False
    for offset, line in lines:
        if not line.lstrip().startswith("|"):
            header, previous_was_table = None, False
            continue
        cells = []
        pos = line.index("|") + 1
        while True:
            nxt = line.find("|", pos)
            if nxt == -1:
                break
            cells.append((offset + pos, offset + nxt))
            pos = nxt + 1
        if re.fullmatch(r"[\s|:-]+", line):  # ligne de séparation
            continue
        is_header = not previous_was_table
        previous_was_table = True
        yield cells, is_header, header
        if is_header:
            header = [normalize_cue(line[s - offset : e - offset]) for s, e in cells]


def cue_spans(text: str, cues: dict[str, str]) -> list[Span]:
    """Entités repérées grâce aux libellés de champ (tableaux, « Libellé : valeur », prose)."""
    index = CueIndex(cues)
    spans: list[Span] = []
    lines, offset = [], 0
    for line in text.split("\n"):
        lines.append((offset, line))
        offset += len(line) + 1

    # 1. Tableaux : cellule libellé suivie de sa valeur, ou colonne dont l'entête est un repère.
    column_mode = False
    for cells, is_header, header in _table_rows(lines):
        kinds = [index.get(text[s:e]) for s, e in cells]
        pairs = 0
        for i in range(len(cells) - 1):
            value = text[cells[i + 1][0] : cells[i + 1][1]]
            if kinds[i] and value.strip() and not kinds[i + 1]:
                spans += _value_spans(text, *cells[i + 1], kinds[i])
                pairs += 1
        if is_header:
            # Un tableau « libellé | valeur » n'a pas de ligne d'entête : pas de lecture par colonne.
            column_mode = pairs == 0
        elif header and column_mode:
            for i, (s, e) in enumerate(cells):
                kind = index.get(header[i]) if i < len(header) else None
                if kind and not kinds[i]:
                    spans += _value_spans(text, s, e, kind)

    # 2. « Libellé : valeur » : la valeur court jusqu'au libellé suivant de la ligne.
    for line_offset, line in lines:
        if line.lstrip().startswith("|"):
            continue
        fields = []  # (début du libellé, fin des deux-points, type ; None = simple borne)
        for match in re.finditer(r"([^\s:|;]+(?:[ _'’][^\s:|;]+){0,3})\s*:(?!\d)", line):
            words = re.split(r"(?<=[ _'’])", match.group(1))
            for i in range(len(words)):  # libellé le plus long d'abord : « Médecin traitant » > « traitant »
                kind = index.get("".join(words[i:]))
                if kind:
                    label_start = match.start(1) + sum(len(w) for w in words[:i])
                    fields.append((label_start, match.end(), kind))
                    break
            else:
                last = words[-1].strip(" _")
                if last.isupper() and len(last) > 1:  # libellé d'export (« SEXE: ») : borne la valeur précédente
                    fields.append((match.end(1) - len(last), match.end(), None))
        for i, (_, colon_end, kind) in enumerate(fields):
            if kind is None:
                continue
            end = fields[i + 1][0] if i + 1 < len(fields) else len(line)
            stop = re.search(r"[|;]|\s{3,}|\s[-–—]\s", line[colon_end:end])
            if stop:
                end = colon_end + stop.start()
            spans += _value_spans(text, line_offset + colon_end, line_offset + end, kind)

    # 3. Prose : « né le 4 février 1956 », « demeurant 6, chemin X à Ville ».
    for match in re.finditer(rf"\bn[ée]e?(?:\(e\))?\s+le\s+({_DATE})", text, re.IGNORECASE):
        spans.append(Span(match.start(1), match.end(1), "DATE_NAISSANCE", "repere"))
    address_re = rf"\b(?:demeurant|domicili[ée]e?|r[ée]sidant)\s+(?:au\s+|à\s+)?(.+?)\s+à\s+({_WORD}(?:[ -](?:{_LINK}|{_WORD}))*)"
    for match in re.finditer(address_re, text):
        spans.append(Span(match.start(1), match.end(1), "ADRESSE", "repere"))
        spans.append(Span(match.start(2), match.end(2), "VILLE", "repere"))
    return spans


# --- Règles de forme ----------------------------------------------------------------

_ZIP_CITY = re.compile(rf"(?<![\d/.,-])\b(\d{{5}})\s+({_WORD}(?:[ -](?:{_LINK}|{_WORD}))*)")
_HOSPITAL = re.compile(
    rf"\b(?:CHU|CHR|CHI|CHG|CH|GHU|GH|AP-HP|Centre\s+hospitalier(?:\s+(?:universitaire|régional|intercommunal))?"
    rf"|H[ôo]pital|H[ôo]pitaux|Clinique|Polyclinique|Institut|Centre\s+de\s+lutte\s+contre\s+le\s+cancer"
    rf"|Réseau|3C)(?:\s+(?:{_LINK}|[a-zàâçéèêëîïôûùüÿ]+)){{0,4}}?\s+{_WORD}(?:[ -](?:{_LINK}[ ]?)*{_WORD})*"
)


_TITLED_PERSON = re.compile(
    rf"\b(?:Dr|Docteur|Pr|Professeur|M\.|Mr|Mme|Mlle|Madame|Monsieur|Mademoiselle)\.?[ \t]+"
    rf"((?:(?:[{_UPPER}]\.|[{_UPPER}][\w'’-]*)[ \t]+){{0,3}}[{_UPPER}][\w'’-]*)"
)


def titled_person_spans(text: str) -> Iterator[Span]:
    """Personnes précédées d'une civilité, initiales accentuées comprises (« Dr Élise LEMONNIER »).

    Les règles d'eds-pseudo ne reconnaissent que les majuscules ASCII ([A-Z]) et
    manquent donc « Élise », « Émile » ou « CLÉMENT ».
    """
    for match in _TITLED_PERSON.finditer(text):
        words = []
        for w in re.finditer(r"[\w'’-]+", match.group(1)):
            if re.match(r"\s*:", text[match.start(1) + w.end() :]):
                break  # « DEMANDEUR: » est le libellé suivant, pas un nom
            words.append(w)
        has_upper = any(w.group().isupper() and len(w.group()) > 1 for w in words)
        for i, w in enumerate(words):
            word = w.group()
            if word.isupper() and len(word) > 1:
                label = "NOM"
            elif len(word) == 1:
                continue  # initiale
            else:
                label = "NOM" if not has_upper and i == len(words) - 1 and len(words) > 1 else "PRENOM"
                if len(words) == 1:
                    label = "NOM"
            yield Span(match.start(1) + w.start(), match.start(1) + w.end(), label, "regle")


def pattern_spans(text: str) -> list[Span]:
    """Personnes avec civilité, code postal + ville, établissements et réseaux de soins."""
    spans = list(titled_person_spans(text))
    for match in _ZIP_CITY.finditer(text):
        spans.append(Span(match.start(1), match.end(1), "ZIP", "regle"))
        spans.append(Span(match.start(2), match.end(2), "VILLE", "regle"))
    for match in _HOSPITAL.finditer(text):
        spans.append(Span(match.start(), match.end(), "HOPITAL", "regle"))
    return spans


# --- Propagation --------------------------------------------------------------------

PROPAGATED_LABELS = {"NOM", "PRENOM", "VILLE", "HOPITAL", "ADRESSE", "IPP", "NDA", "SECU", "AUTRE"}
STOPWORDS = {"le", "la", "les", "de", "du", "des", "et", "dr", "pr", "mme", "nom", "date", "rcp", "ville"}


def find_forms(text: str, forms: Iterable[tuple[str, str]], source: str, require_capital: bool = True) -> list[Span]:
    """Toutes les occurrences (mot entier, casse indifférente) des formes données."""
    spans = []
    for form, label in forms:
        form = form.strip()
        if len(form) < 3 or form.casefold() in STOPWORDS:
            continue
        pattern = re.compile(rf"(?<![\w-]){re.escape(form)}(?![\w-])", re.IGNORECASE)
        for match in pattern.finditer(text):
            first = match.group()[0]
            if require_capital and first.isalpha() and not first.isupper():
                continue
            spans.append(Span(match.start(), match.end(), label, source))
    return spans


def propagate(text: str, spans: list[Span]) -> list[Span]:
    """Étend chaque identifiant détecté à ses autres occurrences dans le document."""
    forms = {(text[s.start : s.end], s.label) for s in spans if s.label in PROPAGATED_LABELS}
    return find_forms(text, forms, "propagation")
