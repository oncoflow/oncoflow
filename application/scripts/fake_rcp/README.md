# Générateur de fiches RCP fictives

Produit des fiches de réunion de concertation pluridisciplinaire **entièrement inventées**, en **Word (.docx)** et en **PDF**, pour tester Oncoflow sans jamais utiliser de dossier réel.

Chaque document porte la mention « DOCUMENT FICTIF » et son nom se termine par `.sample.docx` / `.sample.pdf` (seuls noms de documents autorisés dans le dépôt par le garde-fou `check_no_patient_files.sh`).

## Utilisation

Depuis le dossier `application/` :

```bash
uv run python -m scripts.fake_rcp -n 20 --seed 1                 # 20 dossiers, Word + PDF
uv run python -m scripts.fake_rcp --centers chu_valcourt --formats pdf
uv run python -m scripts.fake_rcp --pathologies pancreas colon --stage pre --missing-rate 0.4
uv run python -m scripts.fake_rcp -o ressources/PatientMDTForm   # visibles directement dans l'interface
```

Ou depuis la racine : `make fake-rcp N=20 SEED=1`.

Par défaut, les fichiers sont écrits dans `application/ressources/PatientMDTForm/fictifs/`, ignoré par git. La même graine donne toujours le même jeu.

## Diversité produite

| Centre (inventé) | Gabarit |
| :-- | :-- |
| `chu_valcourt` | Fiche structurée en tableaux, type export de dossier communicant de cancérologie |
| `ch_saint_aubin` | Courrier narratif au médecin traitant |
| `institut_tilleuls` | Formulaire de centre de lutte contre le cancer avec pièces à cocher |
| `clinique_belvedere` | Fiche courte de clinique privée, abréviations (ATCD, HDM, MT…) |
| `hopital_ardoise` | Export texte brut d'un logiciel métier, dates ISO, police à chasse fixe |

Pathologies : `pancreas`, `colon`, `rectum`, `oesophagus`, `hcc`, `lung`, `breast`, `glioblastoma`, `prostate` (RCP digestive, foie, thoracique, sénologie, neuro-oncologie, uro-oncologie).

Chaque dossier existe en version **pré-RCP** (demande d'inscription, sans décision) ou **post-RCP** (avec proposition et participants).

## Vérité terrain (`manifest.json`)

Pour évaluer les fonctions d'Oncoflow, chaque dossier est accompagné de ce qu'un relecteur devrait trouver :

- `missing_items` / `outdated_items` / `complete` : pièces absentes ou trop anciennes (complétude) ;
- `expected_requests` : demandes préalables attendues (oncogériatrie à partir de 75 ans, nutrition, relecture d'imagerie externe, actualisation d'examen, complément de bilan, consultation d'anesthésie) ;
- `required_specialties`, `participants`, `missing_specialties` : quorum.

Ces règles sont volontairement simples et **ne constituent pas une référence clinique** : le contenu médical est plausible mais n'a pas été validé par des médecins.

## Avertissement

Noms, adresses et numéros sont générés par [Faker](https://faker.readthedocs.io/) (`fr_FR`) ; les établissements et réseaux sont inventés (codes postaux en 99xxx, inexistants). Toute ressemblance avec une personne réelle serait fortuite.
