# 🤝 Guide de Contribution — Oncoflow

Merci de l'intérêt que vous portez à **Oncoflow** ! C'est un projet open-source et gratuit conçu pour aider les chirurgiens et oncologues français spécialisés en cancérologie digestive.

Pour rejoindre la communauté et commencer à contribuer :
1. Rejoignez notre serveur Discord officiel : [Rejoindre le Discord Oncoflow](https://discord.gg/C2RPhyn9x8)
2. Laissez un court message de salutation dans le salon `#ask-to-join` afin que nous vous donnions les droits d'écriture ! 😊

---

## 📋 Étapes pour contribuer

1. **Trouver ou Créer une Issue** : Choisissez une issue existante ou créez-en une nouvelle (`bug`, `feature`, `fix`, etc.).
2. **Fork & Branche** : Clonez le projet et créez une branche de travail liée à l'issue.
3. **Convention de Nommage** : Préfixez votre branche et vos commits (ex. `feature/nom-de-la-feature`, `fix/correction-de-bug`).
4. **Pull Request (PR)** : Ouvrez une PR sur le dépôt principal.
5. **Revue de Code** : Les administrateurs reliront et valideront vos modifications avant de fusionner.

---

## 🛡️ Règles d'Or du Développement

> [!CAUTION] **Stricte Confidentialité des Données Patient**
> * **Aucun appel externe à des API publiques** (comme OpenAI, Anthropic, etc.) n'est toléré dans le code de production.
> * L'application doit impérativement pouvoir tourner **100% hors-ligne (local-first)**.
> * Toutes les données médicales doivent rester au sein de l'infrastructure de l'hôpital.

* **Orchestration** : Utilisez autant que possible l'API standard de [LangChain](https://www.langchain.com/).
* **Modélisation** : Suivez le modèle d'architecture en oignon (Clean Onion Architecture).

---

## 💻 Environnement de Développement Local

### Prérequis Matériels & Logiciels
* **Matériel** : Une carte graphique dédiée (Nvidia) avec au moins **12 Go de VRAM** est vivement recommandée pour faire tourner les modèles de raisonnement locaux.
* **Système** : Docker & Docker Compose installés et configurés (avec support GPU Nvidia si Ollama est exécuté via Docker).
* **Langage** : Python **`>=3.13`** (exigence stricte spécifiée dans `pyproject.toml`).
* **Gestionnaire de Paquets** : Nous recommandons [**`uv`**](https://github.com/astral-sh/uv) pour une installation instantanée et reproductible.

---

### 1. Démarrage des Services de l'Infrastructure (Docker Compose)

Les services d'infrastructure d'Oncoflow sont divisés en deux fichiers Docker Compose situés dans `docker/compose/`. Lancez-les depuis la **racine du dépôt** :

#### A. Base de Données Vectorielle (Milvus Standalone)
Milvus est notre base de données de similarité principale. Elle utilise trois conteneurs locaux (milvus-standalone, etcd, minio) :
```bash
docker compose -f docker/compose/milvus-standalone-docker-compose.yml up -d
```
* **Vérification** : Milvus écoute sur le port local `19530`.

#### B. Services Communs (MongoDB & Ollama)
Ce fichier lance MongoDB (stockage des métadonnées patients et cache) et une instance optionnelle d'Ollama avec support GPU Nvidia :
```bash
docker compose -f docker/compose/docker-compose.yml up -d
```
* **MongoDB** : Écoute sur le port `27017` avec les identifiants par défaut `root:root`.
* **Ollama (Docker)** : Écoute sur le port `11434` et monte ses modèles sur `/data/ollama`.
  > [!TIP]
  > Si vous disposez déjà d'une instance **Ollama locale (native)** installée sur votre système d'exploitation, vous n'avez pas besoin de lancer le service Ollama du Docker Compose. Assurez-vous simplement que votre instance Ollama locale est active en tâche de fond et écoute sur `http://localhost:11434`.

#### C. Validation des Services
Vérifiez que tous les services requis tournent correctement sur votre machine :
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
Les ports locaux indispensables pour l'application sont :
* `19530` (Milvus Vector Store)
* `27017` (MongoDB Document Store)
* `11434` (Ollama Inference Server)

---

### 2. Configuration des Modèles IA locaux (Ollama)

Oncoflow nécessite trois types de modèles locaux pour fonctionner. Vous devez les récupérer via le client Ollama avant de démarrer l'application.

Voici les correspondances avec les variables de configuration (`AppConfig`) :

| Rôle dans l'application | Variable d'environnement | Modèle Recommandé (Standard VRAM >= 12Go) | Modèle Léger (Low VRAM < 8Go) |
| :--- | :--- | :--- | :--- |
| **Raisonnement Clinique** | `APP_LLM_MODELS` | `mistral-nemo` (12B) | `gemma2:2b` ou `llama3.2:3b` |
| **Vision & OCR local** | `APP_LLM_OCRMODELS` | `granite3.2-vision` (VLM) | `granite3.2-vision` |
| **Embeddings Vectoriels** | `APP_LLM_EMBEDDINGS` | `nomic-embed-text` | `all-MiniLM-L6-v2` |

#### Commandes de téléchargement (Ollama local) :
Exécutez les commandes suivantes dans votre terminal pour charger les modèles recommandés dans votre instance Ollama :
```bash
# Téléchargement du modèle d'embeddings vectoriels
ollama pull nomic-embed-text

# Téléchargement du modèle de raisonnement clinique
ollama pull mistral-nemo

# Téléchargement du modèle de vision (VLM) pour décoder les PDF et images
ollama pull granite3.2-vision
```

---

### 3. Installation des Dépendances Python

Placez-vous dans le sous-dossier `/application` :
```bash
cd application/
```

#### Option A : Avec `uv` (Recommandé - Ultra rapide)
```bash
# Crée automatiquement l'environnement virtuel et synchronise le fichier de verrouillage uv.lock
uv sync
```

#### Option B : Avec `pip` classique & `venv`
```bash
# Créer et activer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances en mode éditable
pip install -e .
```

---

### 4. Lancement de l'Interface Utilisateur (UI Streamlit)

L'interface graphique est propulsée par Streamlit. Elle offre le tableau de bord des RCP, le suivi des patients, la gestion des imports PDF et la visualisation des agents.

Pour démarrer l'UI :
1. Assurez-vous d'être dans le dossier `application/`
2. Lancez le serveur Streamlit avec votre environnement virtuel actif :

```bash
# Avec uv (Recommandé)
uv run streamlit run app-ui.py

# Avec pip classique (environnement virtuel activé)
streamlit run app-ui.py
```

Le terminal affichera les adresses d'accès :
```text
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.1.XX:8501
```

Ouvrez **`http://localhost:8501`** dans votre navigateur pour accéder à l'application.

---

### 5. Options et Diagnostic de Débogage

* **Mode console interactif (Debug sans interface graphique)** :
  ```bash
  uv run python3 app.py
  ```
* **Lister les Variables d'Environnement configurées et leurs valeurs par défaut** :
  ```bash
  uv run python3 app.py -e
  ```
* **Lancer l'UI avec un niveau de journalisation détaillé (DEBUG)** :
  ```bash
  APP_LOGS_LEVEL=DEBUG uv run streamlit run app-ui.py
  ```

---


---

## 📚 Plus d'informations

Pour approfondir vos connaissances sur le fonctionnement interne de l'application, reportez-vous aux guides suivants :
* [🩺 Guide d'utilisation Clinique](docs/guide_clinique.md)
* [💻 Référence Technique & Variables](docs/guide_technique.md)
* [🤖 Directives d'Agents IA (AGENTS.md)](AGENTS.md)
