# 🖥️ Oncoflow — Frontend Application Dashboard

<p align="left">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-%3E%3D%203.13-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python Version" /></a>
  <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/Frontend-Streamlit%201.57+-FF4B4B?style=flat-square&logo=streamlit&logoColor=white" alt="Streamlit" /></a>
  <a href="tests"><img src="https://img.shields.io/badge/Tests-Pytest%20Passing-brightgreen?style=flat-square&logo=pytest&logoColor=white" alt="Tests Status" /></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square" alt="Ruff Linter" /></a>
  <a href="../README.md#-souveraineté--sécurité-locale"><img src="https://img.shields.io/badge/Privacy-100%25%20Local%20First-2ea44f?style=flat-square&logo=shield&logoColor=white" alt="Local First" /></a>
</p>

Cette partie de l'application contient l'interface utilisateur développée en **Streamlit** ainsi que les configurations liées à l'exécution de l'application.

## 🚀 Lancement de l'application
Pour démarrer l'interface d'Oncoflow localement en mode développement, exécutez la commande suivante depuis ce dossier (`application/`) :
```bash
uv run streamlit run app-ui.py
```

---

## 🔐 Système de Connexion (Authentification)
L'application requiert une authentification pour accéder aux dossiers patients. Ce système fonctionne de manière sécurisée et entièrement locale.

### Fichier de configuration `auth_config.yaml`
Le fichier de configuration `application/auth_config.yaml` contient les identifiants et les paramètres de cookies de session de l'authentificateur.

#### Identifiants de test par défaut :
* **Username** : `admin`
* **Password** : `admin`

### Ajouter ou modifier un utilisateur
Les mots de passe dans `auth_config.yaml` doivent être hachés avec Bcrypt. Un script interactif est fourni pour gérer l'ajout et la mise à jour des utilisateurs directement dans le fichier YAML :

1. Lancez le script interactif de gestion des utilisateurs :
   ```bash
   uv run python scratch/add_user.py
   ```
2. Saisissez les informations demandées à l'écran (nom d'utilisateur, nom complet, e-mail et mot de passe).
3. Le script génèrera automatiquement le hash Bcrypt sécurisé et l'écrira directement dans le fichier `auth_config.yaml`.
