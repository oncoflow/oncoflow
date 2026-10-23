# Autoclave

> *Stérilisation de documents médicaux.* Au bloc, l'autoclave stérilise les instruments ; ici, il retire des documents ce qui permet d'identifier un patient, avant qu'ils ne quittent le service.

**Autoclave** est un outil **autonome et 100 % local** de pseudonymisation de documents médicaux (fiches de RCP, comptes rendus, courriers), avec une **interface web de vérification humaine**. Il ne dépend pas d'Oncoflow et peut être réutilisé dans d'autres projets.

Un document passe par trois états dans l'interface :

| État | Signification |
| :-- | :-- |
| **Contaminé** | Importé et analysé, pas encore relu |
| **En cycle** | En cours de vérification |
| **Stérile** | Validé par un humain ; inclus dans l'export d'entraînement |

Chaîne de traitement :

1. **Conversion** du PDF ou du DOCX en Markdown avec [Docling](https://github.com/docling-project/docling). Pour un PDF, si les modèles Docling ne sont pas installés sur le poste, l'outil se replie sur une extraction PyMuPDF (texte et tableaux).
2. **Détection** des identifiants avec les règles d'[eds-pseudo](https://github.com/aphp/eds-pseudo) (AP-HP, licence BSD-3), complétées par des règles pensées pour les fiches structurées, le lexique appris et, en option, le modèle eds-pseudo entraîné.
3. **Vérification** dans le navigateur : le Markdown et le PDF d'origine côte à côte. On sélectionne à la souris ce qui est encore identifiant et on corrige les détections.
4. **Apprentissage local** : chaque correction enrichit un lexique qui s'applique aux documents suivants. Les documents validés s'exportent au format d'entraînement d'eds-pseudo.

> **Aucune donnée ne sort du poste.** Hugging Face est forcé en mode hors ligne, l'interface n'utilise aucune ressource externe (ni CDN ni police distante) et le serveur n'écoute que sur `127.0.0.1` par défaut.

## Installation

```bash
cd tools/autoclave
uv sync
```

eds-pseudo n'est pas publié sur PyPI : il est installé depuis GitHub, à un commit figé dans `pyproject.toml`.

### Modèles Docling (recommandé pour les PDF)

À faire une fois, sur un poste qui a accès à Internet. Le dossier peut ensuite être copié sur le poste hospitalier :

```bash
uv run docling-tools models download layout tableformer -o ~/docling-models
export DOCLING_ARTIFACTS_PATH=~/docling-models
```

Sans ces modèles, les PDF sont convertis par PyMuPDF (`conversion pymupdf` s'affiche dans l'interface). Les DOCX n'ont besoin d'aucun modèle.

### Modèle eds-pseudo entraîné (facultatif)

Le modèle public [AP-HP/eds-pseudo-public](https://hf.co/AP-HP/eds-pseudo-public) demande un accès sur Hugging Face. Une fois téléchargé dans un dossier local, ajoutez `--model /chemin/vers/le/modele` aux commandes.

## Utilisation

```bash
# Interface de vérification (http://127.0.0.1:8765)
uv run autoclave serve

# Importer des documents dans l'espace de travail
uv run autoclave add fiche1.pdf fiche2.docx

# En ligne de commande, sans vérification
uv run autoclave convert fiche.pdf -o fiche.md
uv run autoclave pseudonymize fiche.pdf -o fiche.pseudo.md                       # [NOM], [DATE]...
uv run autoclave pseudonymize fiche.pdf --strategy surrogate --mapping table.json # valeurs fictives

# Exporter les documents validés pour entraîner eds-pseudo (scripts/train.py)
uv run autoclave export -o annotations.jsonl
```

L'espace de travail est `~/.autoclave` par défaut (option `-w`). Il est **hors du dépôt** et contient des données réelles : documents, lexique et table de correspondance. Protégez-le comme le dossier patient.

### Méthodes de remplacement

| Méthode | Résultat |
| :-- | :-- |
| `placeholder` (défaut) | `[NOM]`, `[PRENOM]`, `[DATE_NAISSANCE]`… |
| `surrogate` | Valeurs fictives cohérentes : un même nom reçoit toujours le même substitut, et toutes les dates sont décalées du même nombre de jours, ce qui préserve les délais et l'âge. |

La table de correspondance (`--mapping`) permet de ré-identifier le document : c'est ce qui distingue une pseudonymisation d'une anonymisation. Elle est aussi sensible que le document d'origine.

## Interface de vérification

Lancement : `uv run autoclave serve` (ou `make autoclave` depuis la racine d'Oncoflow).

| Action | Geste |
| :-- | :-- |
| Masquer un passage oublié | Le sélectionner à la souris (la sélection s'ajuste aux mots entiers), puis choisir l'étiquette : clic, touches `1`…`0`, ou `Entrée` pour la dernière étiquette utilisée |
| Corriger une détection | Cliquer dessus : changer l'étiquette ou « Pas identifiant » (`X`) |
| Parcourir les entités | `J` / `K` ; l'entité courante est encadrée dans le PDF |
| Annuler | `Ctrl+Z`, ou le bouton « Annuler » de la notification |
| Vérifier le résultat | Onglet « Aperçu pseudonymisé » |
| Terminer | « Déclarer stérile » (`V`) : le document entre dans l'export d'entraînement |

Côté PDF, chaque entité est encadrée de sa couleur. Survoler une entité d'un côté la met en évidence de l'autre ; cliquer sur un cadre du PDF ouvre l'entité correspondante dans le texte. Pendant une sélection, le passage est recherché dans le PDF (cadre pointillé orange) pour vérifier le parallèle.

### Ce que l'outil apprend de vos corrections

| Correction | Effet sur les documents suivants |
| :-- | :-- |
| Passage oublié et masqué | La forme est ajoutée à « Toujours masquer ». Si elle suivait un libellé (« Médecin coordonnateur : X », cellule de tableau), ce libellé devient un nouveau repère de champ. |
| Détection rejetée | La forme est ajoutée à « Ne jamais masquer » (ex. « Child-Pugh », « Gleason »). |
| Correction annulée | Elle est oubliée. |

Le lexique se consulte et se modifie dans le panneau « Lexique appris ». « Ré-analyser tout » réapplique la détection à tous les documents.

## Écarts d'eds-pseudo identifiés et corrigés

eds-pseudo est conçu pour des comptes rendus rédigés de l'AP-HP. Sur des fiches de RCP, ses règles laissent passer environ un identifiant sur quatre :

| Écart | Exemple | Règle ajoutée |
| :-- | :-- | :-- |
| Noms sans civilité rangés dans des champs | `\| Nom de naissance \| VAILLANT \|`, `PATIENT: NORMAND, Richard` | Repères de champ (tableaux Markdown, « Libellé : valeur », exports en capitales) |
| Initiales accentuées ignorées (règles en `[A-Z]`) | `Dr Élise LEMONNIER`, `Dr Sylvie CLÉMENT` | Règle de civilité Unicode |
| Date de naissance classée comme simple date | `DDN: 1955-06-30`, `\| Date de naissance \| 11/10/1953 \|` | Repères de date de naissance |
| IPP propre à l'AP-HP (10 chiffres commençant par 8) | `IPP: 298277534` | Repères « IPP », « N° dossier », « NIP »… |
| Ville et code postal hors adresse complète | `80728 Gauthier`, `demeurant … à Pichon-la-Forêt` | Règles code postal + ville et « demeurant … à » |
| Établissements (modèle uniquement) | `CHU de Valcourt`, `3C Landes-et-Marais` | Règle sur les noms d'établissements et de réseaux |
| Un identifiant détecté une fois mais pas ailleurs | `VAILLANT a reçu…` | Propagation à toutes les occurrences |
| Libellés pris pour des noms | `SEXE: M DDN:` → « DDN » masqué comme nom | Filtre : un mot suivi de « : » n'est pas un nom |

### Mesure

`autoclave evaluate` mesure les fuites sur un jeu fictif dont on connaît les identifiants : patient, médecins, adresse, IPP, date de naissance. Le jeu est généré par `application/scripts/fake_rcp` d'Oncoflow : 5 centres aux mises en page différentes, PDF et DOCX.

```bash
cd application && uv run python -m scripts.fake_rcp -n 20 --seed 11 -o /tmp/fake
cd ../tools/autoclave && uv run autoclave evaluate /tmp/fake
```

| Détection | DOCX | PDF (repli PyMuPDF) |
| :-- | :-- | :-- |
| Règles eds-pseudo seules | 74,0 % des identifiants masqués (81 fuites / 312) | 74,0 % |
| Autoclave | **99,7 %** (1 fuite / 312) | **99,7 %** |

La fuite restante est une ville fictive homonyme d'un mot clinique (« Masse »). Ces chiffres portent sur des documents synthétiques : ils ne remplacent pas une vérification humaine sur de vrais documents, qui est précisément le rôle de l'interface.

## Développement

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Organisation de `src/autoclave/` :

| Module | Rôle |
| :-- | :-- |
| `convert.py` | Conversion Docling, avec repli PyMuPDF |
| `detect.py` | Orchestration : eds-pseudo, règles, lexique, propagation |
| `rules.py` | Règles complémentaires |
| `lexicon.py` | Lexique appris |
| `entities.py` | Étiquettes, sources et résolution des chevauchements |
| `pseudonymize.py` | Remplacement par étiquettes ou valeurs fictives |
| `workspace.py` | Stockage local des documents et des annotations |
| `locate.py` | Position des entités dans le PDF |
| `server.py` + `static/` | API et interface web |
| `evaluate.py` | Mesure des fuites |
| `cli.py` | Ligne de commande |

## Limites

- **Documents scannés** : l'OCR est désactivé, car il nécessite d'autres modèles. Les PDF scannés ne produisent pas de texte.
- **Couverture des règles** : elles visent les documents français et les identifiants usuels. Les identifiants indirects (profession rare, histoire familiale singulière…) relèvent de la vérification humaine.
- **Pas d'authentification** : l'interface est mono-utilisateur, à lancer sur le poste qui détient les documents.
