# Suite d'Évaluation des Agents Oncoflow (LLM-as-a-Judge & MLflow)

Ce module fournit un banc de test et d'évaluation complet pour les agents de la plateforme **Oncoflow**, découplé de l'interface Streamlit. Il met en œuvre une approche **LLM-as-a-Judge** (sans vérité terrain) opérée via **LiteLLM**, sensibilisée aux limites techniques des petits modèles locaux (**SLM 7B-14B quantifiés en 4-bit**), et centralise les métriques et diffs de prompts sur **MLflow**.

---

## 🏗️ Architecture du Module

```text
evaluation/
├── docker-compose.mlflow.yml       # Serveur MLflow (v3.13.0) + Backend SQLite (Réseau search-community)
├── requirements-eval.txt           # Dépendances Python nécessaires à l'évaluation (mlflow==3.13.0)
├── run_eval.py                     # Point d'entrée CLI principal
├── config/
│   ├── eval_config.yaml            # Paramètres généraux (endpoints LiteLLM, domaine par défaut)
│   ├── target_model_profile.yaml   # Profil des limitations des SLM locaux (injecté au Juge)
│   └── rubrics/
│       ├── oncology_rubrics.yaml   # Grille de cotation clinique TNCD (Oncologie digestive)
│       └── sma_rubrics.yaml        # Grille de cotation clinique PNDS (Amyotrophie Spinale)
├── datasets/
│   ├── oncology/manifest.json      # Cas tests réels anonymisés (CHEVALIER, LEFEBVRE, etc.)
│   └── sma/manifest.json           # Cas tests SMA
├── engine/
│   ├── judge.py                    # Client du Juge Frontière via LiteLLM
│   ├── metrics.py                  # Journalisation des métriques (1 à 5) dans MLflow
│   ├── prompt_optimizer.py         # Moteur de diff et de réécriture de prompts pour SLM
│   └── runner.py                   # Orchestrateur d'évaluation (Ask unitaire & Débat RCP)
└── tests/
    ├── conftest.py                 # Fixtures Pytest partagées
    ├── test_judge.py               # Tests unitaires du Juge et de l'extraction JSON
    ├── test_prompt_optimizer.py    # Tests unitaires de la génération de diffs
    ├── test_metrics.py             # Tests unitaires de la journalisation MLflow
    ├── test_runner.py              # Tests unitaires de l'orchestrateur
    └── test_cli.py                 # Tests unitaires de l'interface CLI
```

---

## 🚀 Démarrage Rapide via `make`

Le Makefile à la racine du projet intègre désormais toutes les commandes d'évaluation :

### 1. Initialiser l'environnement d'évaluation et MLflow
Installe les dépendances applicatives et d'évaluation, puis démarre la stack Docker MLflow :
```bash
make eval-init
```
> Le dashboard MLflow est accessible sur : **`http://localhost:5000`**

### 2. Lancer les tests unitaires et la validation Ruff
```bash
# Lancer la suite complète de tests unitaires d'évaluation (100% isolés et mockés)
make eval-test

# Vérifier la conformité du code avec le linter Ruff
make eval-lint

# Formater automatiquement avec Ruff
make eval-format
```

### 3. Exécuter l'évaluation avec options configurables (`make eval-run`)

#### Évaluation par défaut (Oncologie digestive, Débat RCP complet) :
```bash
make eval-run
```

#### Évaluer un cas précis (ex: Emilie CHEVALIER) :
```bash
make eval-run CASE_ID=onco-01
```

#### Évaluer en mode unitaire sur un agent spécifique :
```bash
make eval-run MODE=single_agent AGENT="pancreas expert"
```

#### Évaluer le domaine Amyotrophie Spinale (SMA) :
```bash
make eval-run DOMAIN=sma
```

#### Changer de modèle juge frontière via LiteLLM à la volée :
```bash
make eval-run JUDGE_MODEL=claude-3-7-sonnet
```

---

## 🎯 Dimensions Évaluées par le Juge (Scores 1 à 5)

| Métrique | Description Clinique & Technique |
| :--- | :--- |
| **`clinical_faithfulness`** | Ancrage strict sur le dossier patient (MTD). Zéro tolérance pour les faits inventés. |
| **`completeness_awareness`** | Détection des examens non réalisés et renseignement rigoureux de `what_missing`. |
| **`guideline_conformance`** | Respect des arbres de décision TNCD (Oncologie) ou PNDS (SMA) et du rôle de chaque spécialiste. |
| **`structural_robustness`** | Conformité stricte du JSON au schéma Pydantic (`PatientMDTForm`) sans retries superflus. |
| **`debate_consensus`** | Qualité de l'arbitrage et de la synthèse du coordinateur à partir des avis croisés d'experts. |

---

## 🧠 Sensibilisation aux Limitations des SLM Locaux

Le Juge frontière reçoit systématiquement le fichier [`evaluation/config/target_model_profile.yaml`](file:///home/guillaume/git/oncoflow/evaluation/config/target_model_profile.yaml).
Il lui est strictement interdit de recommander des prompts surdimensionnés (CoT à 15 étapes ou méta-prompts verbeux).

Ses propositions d'amélioration de prompt appliquent obligatoirement les règles d'or pour SLM :
1. **Directives affirmatives positives** (élimination des négations multiples « Ne pas inventer... »).
2. **Délimiteurs Markdown explicites** (`### CONTEXTE`, `### TÂCHE`, `### RÈGLES`, `### FORMAT`).
3. **Concision drastique** (réduction de 25 à 40% du nombre de tokens de prompt).
4. **Micro-exemples few-shot** sur les cas ambigus plutôt que des règles abstraites.
5. **Positionnement du schéma JSON en toute fin de prompt**.

Tous les diffs de prompts sont automatiquement enregistrés et consultables dans l'onglet **Artifacts** de chaque run sur MLflow.

---

## ⚡ Fonctionnalités Avancées MLflow 3

### 1. Enregistrement Automatique dans le **Prompt Registry**
Pour chaque question clinique et chaque agent évalué, les prompts initiaux ainsi que les prompts révisés/optimisés suggérés par le juge frontière sont automatiquement versionnés et archivés dans le **Prompt Registry de MLflow 3** (`mlflow.genai.register_prompt`). Chaque version est traçable avec ses métadonnées (cas ID, agent, domaine, gains attendus).

### 2. Évaluation Progressive « Au fil de l'eau »
L'exécution ne bloque plus jusqu'à la fin complète du banc d'évaluation :
- Les résultats s'affichent en temps réel dans un tableau dynamique terminal grâce à `rich.live.Live`.
- Dans MLflow, une session parente regroupe des runs enfants imbriqués (`nested=True`), finalisés et synchronisés question par question.

### 3. Résilience et Retry Automatique (Erreurs 503 / Surcharge)
Face aux pics de demande sur les modèles juges distants (`openai.InternalServerError: 503 - model experiencing high demand`), un mécanisme de **retry avec backoff exponentiel et gigue aléatoire** est intégré nativement dans `LLMJudge`.

### 4. Traçabilité Complète (MLflow Tracing)
Les appels du juge sont automatiquement instrumentés sous forme de spans `LLM` au sein d'OpenTelemetry et MLflow Tracing. Les erreurs ou exceptions sont capturées sur le span (`record_exception`) et les traces sont immédiatement purgées (`flush_trace_async_logging`) pour garantir une visibilité instantanée sur l'UI MLflow (`http://localhost:5000`).
