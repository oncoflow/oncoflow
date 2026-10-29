# Spécification de l'API REST versionnée (v1) — MedDataSyntis

Cette documentation détaille l'ensemble des points d'entrée de l'API REST de MedDataSyntis versionnée sous `/api/v1`.

L'API permet de gérer les dossiers RCP (Réunions de Concertation Pluridisciplinaire) des patients, de piloter les agents experts d'intelligence artificielle, d'interroger les guides scientifiques (TNCD) de référence et de discuter avec les agents.

---

## Démarrage rapide

Pour démarrer le serveur d'API localement avec le rechargement automatique :

```bash
uv run uvicorn app-api:app --reload --host 127.0.0.1 --port 8000
```

Une fois démarré, la documentation interactive Swagger UI est disponible sur : [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## Structure du Code de l'API

L'API est structurée de manière modulaire au sein du dossier `application/` :
* **Point d'entrée principal** : [app-api.py](file:///home/guillaume/git/oncoflow/application/app-api.py) (configuration de FastAPI, lifespan, et inclusion des routeurs).
* **Routeurs** : [src/routers/](file:///home/guillaume/git/oncoflow/application/src/routers/) (`rcp.py`, `agents.py`, `resources.py`, `queue.py`), dépendances partagées dans [db_interface.py](file:///home/guillaume/git/oncoflow/application/src/infrastructure/documents/db_interface.py).
* **Modèles Pydantic / Schémas** : [src/models/](file:///home/guillaume/git/oncoflow/application/src/models/) (`rcp.py`, `agents.py`, `resources.py`, `queue.py`). Chaque endpoint déclare un `response_model`.

---

## 1. Spécification OpenAPI

### Obtenir la spécification OpenAPI
* **URL** : `/api/v1/openapi.json`
* **Méthode** : `GET`
* **Description** : Renvoie le schéma de configuration OpenAPI v3 de l'API au format JSON (schémas de requête **et** de réponse de tous les endpoints).
* **Interfaces interactives** : `/docs` (Swagger UI) et `/redoc` s'appuient sur cette même URL.
* **Exemple** : `curl -s http://localhost:8000/api/v1/openapi.json -o openapi.json`

---

## 2. Gestion des Dossiers Patients & Fiches RCP (`/api/v1/rcp`)

### Lister les dossiers patients (synthèse sur la dernière RCP analysée)
* **URL** : `/api/v1/rcp/patients`
* **Méthode** : `GET`
* **Description** : Récupère la liste des dossiers patients, où chaque carte reflète les indicateurs cliniques de la **dernière fiche RCP analysée** du patient.
* **Réponse de succès (200 OK)** :
  ```json
  [
    {
      "patient_id": "roussel_marion_1968_04_12",
      "patient": "Marion ROUSSEL",
      "first_name": "Marion",
      "last_name": "ROUSSEL",
      "date_birth": "1968-04-12T00:00:00",
      "rcp_count": 2,
      "latest_file": "ROUSSEL-Marion_2026-07.pdf",
      "date_refresh": "2026-07-14T16:00:00",
      "date": "2026-07-20T00:00:00",
      "experts": ["pancreas expert"],
      "missing": [],
      "urgency": "Urgent",
      "urgency_score": 2,
      "intervention_required": true,
      "intervention_type": "chirurgie"
    }
  ]
  ```

### Obtenir le détail d'un dossier patient et l'historique de ses RCP
* **URL** : `/api/v1/rcp/patients/{patient_id}`
* **Méthode** : `GET`
* **Description** : Récupère les informations d'identité du patient, le nom de sa dernière fiche RCP analysée (`latest_file`), ainsi que la liste chronologique complète de ses fiches RCP (`rcps`).

### Supprimer un dossier patient complet
* **URL** : `/api/v1/rcp/patients/{patient_id}`
* **Méthode** : `DELETE`
* **Description** : Supprime le dossier patient ainsi que toutes ses fiches RCP associées en base et sur le disque.

### Poser une question à un agent expert sur l'ensemble du dossier patient
* **URL** : `/api/v1/rcp/patients/{patient_id}/chat`
* **Méthode** : `POST`
* **Corps de la requête (application/json)** :
  ```json
  {
    "agent_name": "pancreas expert",
    "message": "Quelle est l'évolution du patient entre ses différentes RCP ?"
  }
  ```
* **Description** : Dialogue avec un agent expert en lui fournissant le contexte complet de toutes les fiches RCP du dossier patient (`PatientContext` / `get_patient_mtds_markdown`).

### Lister les fiches RCP scannées
* **URL** : `/api/v1/rcp`
* **Méthode** : `GET`
* **Description** : Récupère la liste synthétique de toutes les fiches RCP disponibles en base, triées par date de scan décroissante.
* **Réponse de succès (200 OK)** :
  ```json
  [
    {
      "file": "ROUSSEL-Marion_anon.pdf",
      "patient_id": "roussel_marion_1968_04_12",
      "patient": "Marion ROUSSEL",
      "date_refresh": "2026-07-14T16:00:00",
      "date": "2026-07-20T00:00:00",
      "experts": ["pancreas expert"],
      "missing": [],
      "urgency": "Urgent",
      "urgency_score": 2,
      "intervention_required": true,
      "intervention_type": "chirurgie"
    }
  ]
  ```

### Obtenir le détail complet d'une fiche RCP
* **URL** : `/api/v1/rcp/{filename}`
* **Méthode** : `GET`
* **Description** : Récupère l'intégralité du document structuré MongoDB pour un fichier RCP spécifique.
* **Réponse de succès (200 OK)** : renvoie l'objet JSON contenant les extractions faites par chaque agent expert (`PatientAdministrative`, `ExpertAnswer`, `MTDCompleted`, etc.).

### Supprimer une fiche RCP
* **URL** : `/api/v1/rcp/{filename}`
* **Méthode** : `DELETE`
* **Description** : Supprime la fiche de la base de données MongoDB (et la retire de la liste `files` du patient associé) ainsi que le PDF correspondant du disque.
* **Réponse de succès (200 OK)** :
  ```json
  {
    "message": "Dossier 'ROUSSEL-Marion_anon.pdf' supprimé avec succès."
  }
  ```

### Téléverser une nouvelle fiche RCP (PDF) et l'associer à un patient
* **URL** : `/api/v1/rcp/upload`
* **Méthode** : `POST`
* **Type de contenu** : `multipart/form-data`
* **Corps de la requête** :
  * `file` : Le fichier PDF de la RCP (binaire)
  * `patient_id` *(optionnel)* : Identifiant d'un patient existant auquel rattacher la fiche. Si omis (par défaut : mode automatique), l'indexation RAG et l'agent administratif IA extraient `first_name`, `last_name` et `date_birth` pour créer ou rattacher automatiquement le dossier patient.
* **Description** : Enregistre le PDF, exécute le RAG + l'extraction administrative IA, et associe la fiche au dossier patient.
* **Réponse de succès (200 OK)** :
  ```json
  {
    "filename": "ROUSSEL-Marion_anon.pdf",
    "patient_id": "roussel_marion_1968_04_12",
    "patient": {
      "patient_id": "roussel_marion_1968_04_12",
      "first_name": "Marion",
      "last_name": "ROUSSEL",
      "date_birth": "1968-04-12T00:00:00",
      "files": ["ROUSSEL-Marion_anon.pdf"]
    },
    "message": "Fichier téléversé, indexé et associé au patient avec succès."
  }
  ```

### Lancer/Relancer le traitement IA d'une fiche RCP
* **URL** : `/api/v1/rcp/{filename}/process`
* **Méthode** : `POST`
* **Corps de la requête (application/json)** :
  ```json
  {
    "model_name": "PatientPerformanceStatus"
  }
  ```
  *(Note : passez `model_name: null` ou omettez le paramètre pour lancer l'analyse complète).*
* **Description** : Déclenche l'extraction des données médicales par les agents d'IA pour le dossier ciblé.
* **Réponse de succès (200 OK)** :
  ```json
  {
    "message": "Modèle 'PatientPerformanceStatus' retraité avec succès pour 'ROUSSEL-Marion_anon.pdf'."
  }
  ```

### Poser une question à un agent expert sur une fiche RCP
* **URL** : `/api/v1/rcp/{filename}/chat`
* **Méthode** : `POST`
* **Corps de la requête (application/json)** :
  ```json
  {
    "agent_name": "pancreas expert",
    "message": "Quel est le statut OMS du patient ?"
  }
  ```
* **Description** : Dialogue directement avec un agent expert dans le cadre d'une fiche RCP spécifique.
* **Réponse de succès (200 OK)** :
  ```json
  {
    "response": "Le statut WHO/OMS du patient est de 1, comme documenté dans la lettre d'admission."
  }
  ```

### Télécharger le PDF original
* **URL** : `/api/v1/rcp/{filename}/pdf`
* **Méthode** : `GET`
* **Description** : Télécharge directement le document source PDF d'un patient.
* **Réponse** : Flux binaire `application/pdf`.

---

## 3. Gestion des Agents (`/api/v1/agents`)

### Lister les agents configurés
* **URL** : `/api/v1/agents`
* **Méthode** : `GET`
* **Description** : Liste tous les agents disponibles dans le domaine configuré (ex: oncology), leur prompt système, leurs ressources et leurs modèles LLM.
* **Réponse de succès (200 OK)** :
  ```json
  [
    {
      "name": "pancreas expert",
      "system_prompt": "You are a distinguished medical expert specializing in pancreas diseases...",
      "models": ["mistral-nemo"],
      "resources": ["TNCDPANCREAS.pdf"]
    }
  ]
  ```

### Obtenir les détails d'un agent
* **URL** : `/api/v1/agents/{agent_name}`
* **Méthode** : `GET`
* **Description** : Récupère la configuration détaillée d'un agent spécifique.

---

## 4. Gestion des Ressources Cliniques (`/api/v1/resources`)

### Lister les guides scientifiques (ressources)
* **URL** : `/api/v1/resources`
* **Méthode** : `GET`
* **Description** : Liste l'ensemble des fichiers PDF scientifiques configurés et indique s'ils sont déjà indexés dans la base vectorielle.
* **Réponse de succès (200 OK)** :
  ```json
  [
    {
      "filename": "TNCDPANCREAS.pdf",
      "is_indexed": true
    },
    {
      "filename": "TNCDOESOPHAGE.pdf",
      "is_indexed": false
    }
  ]
  ```

### Indexer un guide scientifique
* **URL** : `/api/v1/resources/{filename}/index`
* **Méthode** : `POST`
* **Description** : Charge, découpe en chunks et injecte le document scientifique dans la base de données vectorielle (Chroma/Milvus) pour permettre aux agents IA de s'y référer.
* **Réponse de succès (200 OK)** :
  ```json
  {
    "filename": "TNCDOESOPHAGE.pdf",
    "message": "Ressource indexée avec succès."
  }
  ```

### Interroger un guide scientifique (Chat Ressource)
* **URL** : `/api/v1/resources/{filename}/chat`
* **Méthode** : `POST`
* **Corps de la requête (application/json)** :
  ```json
  {
    "message": "Quelles sont les recommandations pour une tumeur du pancréas résécable ?"
  }
  ```
* **Description** : Interroge le guide scientifique via l'agent "Ressource Assistant" (RAG).
* **Réponse de succès (200 OK)** :
  ```json
  {
    "response": "Selon le TNCD Chapitre Pancréas, pour une tumeur résécable, une résection chirurgicale d'emblée suivie d'une chimiothérapie adjuvante par FOLFIRINOX est recommandée..."
  }
  ```
