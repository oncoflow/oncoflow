# Fiches RCP synthétiques

**Tous les patients, dates et établissements sont fictifs.** Aucune donnée réelle de patient ne doit être ajoutée dans ce dossier (le dépôt est public).

Chaque cas contient :

- `fiche_rcp.md` : la fiche RCP telle que présentée en réunion ;
- `annexes/*.md` : les documents annexes (comptes rendus d'imagerie, d'anatomopathologie, de biologie…) ;
- `case.json` :
  - `expected` : pour chacune des questions de `src/domain/oncology/rcp_review.py`, les valeurs attendues des champs booléens / énumérés (`null` = non évalué) et `must_mention`, une liste de groupes de mots-clés dont au moins un de chaque groupe doit apparaître dans la réponse ;
  - `gold` : une réponse de référence pour chaque question, valide pour son modèle Pydantic.

| Cas | Discuter une résection ? | Données manquantes ? | Incohérences dans la fiche ? | Annexes discordantes ? |
| :-- | :-: | :-: | :-: | :-: |
| `pancreas_resecable_complet` | oui (résécable) | non | non | non |
| `pancreas_bilan_incomplet` | oui (statut inconnu) | **oui** : histologie, scanner thoracique, CA 19-9, OMS | non | non |
| `oesophage_incoherences` | non évalué | non évalué | **oui** : âge, histologie, OMS | non |
| `chc_annexes_discordantes` | non évalué | non évalué | non évalué | **oui** : nombre de nodules, thrombose portale, Child-Pugh |
| `pancreas_metastatique` | non (métastatique) | non | non | non |

Pour ajouter un cas : créer un nouveau dossier avec la même structure, les tests unitaires (`tests/test_rcp_review.py`) le prennent automatiquement en compte.
