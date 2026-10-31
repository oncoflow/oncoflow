# ==============================================================================
# Oncoflow Makefile
# Outil de gestion des services, du développement et de l'infrastructure locale
# ==============================================================================

SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(HOME)/google-cloud-sdk/bin:$(PATH)

# Détection de l'exécutable uv, gcloud et de l'utilisateur courant (membre du groupe docker)
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
GCLOUD := $(shell command -v gcloud 2>/dev/null || echo $(HOME)/google-cloud-sdk/bin/gcloud)
DEPLOY_USER ?= $(shell id -un)

# Dossiers de l'application
APP_DIR := application
WEB_DIR := web

# Ports et configurations configurables
PORT_UI ?= 8501
PORT_WEB ?= 3000
HOST_WEB ?= 127.0.0.1
PORT_API ?= 8000
HOST_API ?= 127.0.0.1
CLOUDRUN_SERVICE ?= llama-cpp-chat
CLOUDRUN_PORT ?= 8080

# Configuration Production (Scaleway L4 24G - Multi-Domaines oncologic & sma)
ENV_PROD ?= $(CURDIR)/.env.prod
PROD_BASE_DOMAIN ?= meddatasyntis.bricks-it.fr
COMPOSE_MILVUS := dist/docker/compose/milvus-standalone-docker-compose.yml
COMPOSE_DEV := dist/docker/compose/docker-compose.yml
COMPOSE_PROD := dist/docker/compose/docker-compose.prod.yml
DEV_VOLUME_DIR ?= $(CURDIR)/dist/docker/compose/volumes
MODELS_DIR := dist/docker/compose/volumes/models
CHAT_MODEL_URL := https://huggingface.co/bartowski/Ornith-1.5-35B-A3B-GGUF/resolve/main/Ornith-1.5-35B-A3B-IQ4_XS.gguf
CHAT_MODEL_FILE := $(MODELS_DIR)/Ornith-1.5-35B-A3B-IQ4_XS.gguf
EMBED_MODEL_URL := https://huggingface.co/gpustack/bge-m3-GGUF/resolve/main/bge-m3-Q4_K_M.gguf
EMBED_MODEL_FILE := $(MODELS_DIR)/bge-m3-Q4_K_M.gguf

# Couleurs pour le terminal
CYAN  := \033[36m
GREEN := \033[32m
YELLOW:= \033[33m
RED   := \033[31m
RESET := \033[0m

.DEFAULT_GOAL := help

.PHONY: help init update install install-web upgrade start-api start-ui start-web start-worker start-ui-dev start-web-dev start-dev cloudrun-proxy cloudrun-proxy-stop stop test test-web coverage lint lint-web format format-web e2e-web build-web docker-build-web mongo-init docker-up docker-up-proxy docker-down docker-update docker-status pull-models clean status get-bugs api ui web worker ui-dev web-dev proxy proxy-stop dev init-prod sudoers-prod pull-models-prod logrotate-prod mongo-init-prod build-prod docker-up-prod docker-down-prod start-prod stop-prod restart-prod prod-update prod-update-all status-prod logs-prod up-prod down-prod prod pprod

## Affiche l'aide et la liste des commandes disponibles
help:
	@echo -e "$(CYAN)Usage: make <commande>$(RESET)"
	@echo ""
	@echo -e "$(GREEN)Commandes principales (Développement) :$(RESET)"
	@echo -e "  $(YELLOW)make init$(RESET)                Initialise l'environnement complet (uv sync + volumes + init Milvus v3.0)"
	@echo -e "  $(YELLOW)make update$(RESET)              Met à jour les packages Python (uv) et les images Docker (Milvus v3.0, MongoDB)"
	@echo -e "  $(YELLOW)make install$(RESET)             Installe les dépendances via uv sync"
	@echo -e "  $(YELLOW)make install-web$(RESET)         Installe les dépendances Node.js de l'interface web"
	@echo -e "  $(YELLOW)make upgrade$(RESET)             Met à jour toutes les dépendances Python (uv lock --upgrade && uv sync)"
	@echo -e "  $(YELLOW)make start-api$(RESET)           Démarre l'API FastAPI (port $(PORT_API))"
	@echo -e "  $(YELLOW)make start-ui$(RESET)            Démarre le dashboard Streamlit (port $(PORT_UI))"
	@echo -e "  $(YELLOW)make start-web$(RESET)           Démarre l'API FastAPI Cross-Domains et le serveur Web Node.js Fastify (port $(PORT_WEB))"
	@echo -e "  $(YELLOW)make start-ui-dev$(RESET)        Démarre Docker en mode proxy, proxy GCP et Streamlit UI"
	@echo -e "  $(YELLOW)make start-web-dev$(RESET)       Démarre Docker en mode proxy, proxy GCP Cloud Run et l'interface Web Node.js"
	@echo -e "  $(YELLOW)make cloudrun-proxy$(RESET)      Lance le proxy Cloud Run en tâche de fond (port $(CLOUDRUN_PORT))"
	@echo -e "  $(YELLOW)make cloudrun-proxy-stop$(RESET) Arrête le proxy Cloud Run"
	@echo -e "  $(YELLOW)make stop$(RESET)                Arrête l'UI (Streamlit/Web), l'API et le proxy Cloud Run"
	@echo ""
	@echo -e "$(GREEN)Commandes de Production (Scaleway L4 24G + OAuth2 Proxy GitHub + Multi-Domaines) :$(RESET)"
	@echo -e "  $(YELLOW)make init-prod$(RESET)           Initialise l'environnement prod (sudoers, .env.prod, volumes, init Milvus v3.0, logrotate, modèles)"
	@echo -e "  $(YELLOW)make sudoers-prod$(RESET)        Installe /etc/sudoers.d/meddatasyntis (Ubuntu 24.04+) pour $(DEPLOY_USER)"
	@echo -e "  $(YELLOW)make logrotate-prod$(RESET)      Génère et installe la configuration logrotate (/etc/logrotate.d/meddatasyntis)"
	@echo -e "  $(YELLOW)make pull-models-prod$(RESET)    Télécharge Ornith-1.5-35B-A3B (IQ4_XS) et bge-m3 (Q4_K_M)"
	@echo -e "  $(YELLOW)make start-prod$(RESET)          Démarre toute la stack prod (Milvus, Mongo, LLM L4, Streamlit & M3 Web UI oncologic-new/sma-new, OAuth2, Caddy)"
	@echo -e "  $(YELLOW)make stop-prod$(RESET)           Arrête tous les conteneurs de la stack prod"
	@echo -e "  $(YELLOW)make restart-prod$(RESET)        Redémarre UIs (Streamlit & Web M3 oncologic-new/sma-new) + API + OAuth2 Proxy + Caddy (sans décharger le LLM)"
	@echo -e "  $(YELLOW)make prod-update$(RESET)         git pull + mise à jour Milvus v3.0 & images UI/Web M3 + redémarrage sans coupure GPU"
	@echo -e "  $(YELLOW)make prod-update-all$(RESET)     Mise à jour complète de toute la stack Docker prod (y compris LLM/infra)"
	@echo -e "  $(YELLOW)make status-prod$(RESET)         Affiche l'état des services prod, santé LLM et VRAM GPU (nvidia-smi)"
	@echo -e "  $(YELLOW)make logs-prod$(RESET)           Affiche les logs en continu de la stack de production"
	@echo ""
	@echo -e "$(GREEN)Commandes de qualité & tests :$(RESET)"
	@echo -e "  $(YELLOW)make test$(RESET)                Exécute la suite de tests Pytest"
	@echo -e "  $(YELLOW)make test-web$(RESET)            Exécute les tests unitaires et d'intégration Vitest de $(WEB_DIR)/"
	@echo -e "  $(YELLOW)make coverage$(RESET)            Mesure le pourcentage de couverture de test"
	@echo -e "  $(YELLOW)make lint$(RESET)                Vérifie le code avec Ruff"
	@echo -e "  $(YELLOW)make lint-web$(RESET)            Vérifie le code TypeScript/CSS de $(WEB_DIR)/ avec Biome, tsc --noEmit et check-contrast.mjs"
	@echo -e "  $(YELLOW)make format$(RESET)              Formate le code avec Ruff"
	@echo -e "  $(YELLOW)make format-web$(RESET)          Formate le code de $(WEB_DIR)/ avec Biome"
	@echo -e "  $(YELLOW)make e2e-web$(RESET)             Exécute les tests end-to-end Playwright de $(WEB_DIR)/"
	@echo -e "  $(YELLOW)make get-bugs$(RESET)            Récupère et affiche les rapports de bugs depuis MongoDB"
	@echo ""
	@echo -e "$(GREEN)Commandes d'infrastructure & Ollama :$(RESET)"
	@echo -e "  $(YELLOW)make docker-up$(RESET)        Démarre Milvus et MongoDB via Docker Compose"
	@echo -e "  $(YELLOW)make docker-up-proxy$(RESET)  Démarre Docker en mode proxy (Milvus + MongoDB + embeddings)"
	@echo -e "  $(YELLOW)make docker-update$(RESET)    Télécharge les dernières images Docker (Milvus v3.0, MongoDB) et met à jour les conteneurs"
	@echo -e "  $(YELLOW)make docker-down$(RESET)      Arrête les conteneurs Milvus et MongoDB"
	@echo -e "  $(YELLOW)make docker-status$(RESET)    Vérifie l'état des conteneurs Docker"
	@echo -e "  $(YELLOW)make pull-models$(RESET)      Télécharge les modèles recommandés dans Ollama local"
	@echo -e "  $(YELLOW)make status$(RESET)           Affiche l'état des services et des ports"
	@echo -e "  $(YELLOW)make clean$(RESET)            Nettoie les caches (__pycache__, .pytest_cache, .ruff_cache)"
	@echo ""

## Initialise l'environnement de développement (dépendances Python, volumes Docker et permissions Milvus v3.0)
init: install
	@echo -e "$(CYAN)--> Préparation des volumes Docker de développement ($(DEV_VOLUME_DIR))...$(RESET)"
	@mkdir -p $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs}
	@chmod 777 $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs} 2>/dev/null || true
	@echo -e "$(CYAN)--> Téléchargement des images Docker (Milvus v3.0 & MongoDB) et initialisation du volume Milvus...$(RESET)"
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) pull
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) run --rm milvus-volume-init
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_DEV) pull
	@echo -e "$(GREEN)--> Initialisation de l'environnement terminée.$(RESET)"

## Met à jour les dépendances Python (uv) ainsi que les images et conteneurs Docker (Milvus v3.0, MongoDB)
update: upgrade docker-update
	@echo -e "$(GREEN)--> Mise à jour complète (packages Python + infrastructure Docker) terminée.$(RESET)"

## Installe l'environnement virtuel et les dépendances du projet
install:
	@echo -e "$(CYAN)--> Installation des dépendances avec uv sync...$(RESET)"
	cd $(APP_DIR) && $(UV) sync

## Installe les dépendances Node.js de l'interface web
install-web:
	@echo -e "$(CYAN)--> Installation des dépendances Node.js de l'interface web ($(WEB_DIR))...$(RESET)"
	npm install --prefix $(WEB_DIR)

## Met à jour l'ensemble des paquets et synchronise l'environnement
upgrade:
	@echo -e "$(CYAN)--> Mise à jour des paquets avec uv lock --upgrade && uv sync...$(RESET)"
	cd $(APP_DIR) && $(UV) lock --upgrade && $(UV) sync

## Démarre l'API FastAPI Cross-Domains (avec file PriorityQueue intégrée)
start-api:
	@echo -e "$(CYAN)--> Démarrage de l'API Cross-Domains sur http://$(HOST_API):$(PORT_API)...$(RESET)"
	cd $(APP_DIR) && $(UV) run python app-api.py

## Démarre l'API Cross-Domains (Queue intégrée) et l'interface Streamlit (logs partagés sur stdout)
start-ui:
	@echo -e "$(CYAN)--> Démarrage de l'API Cross-Domains (Queue PriorityQueue) et de Streamlit UI sur http://localhost:$(PORT_UI)...$(RESET)"
	@pkill -f "[p]ython.*app-api.py" 2>/dev/null || true
	@cd $(APP_DIR); \
	unset VIRTUAL_ENV; \
	export PYTHONUNBUFFERED=1; \
	export APP_QUEUE_API_URL=http://127.0.0.1:$(PORT_API); \
	$(UV) run python -u app-api.py & \
	API_PID=$$!; \
	trap "kill $$API_PID 2>/dev/null || true" INT TERM EXIT; \
	$(UV) run streamlit run app-ui.py --server.port=$(PORT_UI)

## Démarre l'API FastAPI Cross-Domains (en tâche de fond) et le serveur Web Node.js Fastify sur http://localhost:$(PORT_WEB)
start-web:
	@echo -e "$(CYAN)--> Démarrage de l'API Cross-Domains (Queue PriorityQueue) et du serveur Web Node.js Fastify sur http://localhost:$(PORT_WEB)...$(RESET)"
	@pkill -f "[p]ython.*app-api.py" 2>/dev/null || true
	@pkill -f "[t]sx.*src/main.ts" 2>/dev/null || true
	@unset VIRTUAL_ENV; \
	export PYTHONUNBUFFERED=1; \
	export APP_QUEUE_API_URL=http://127.0.0.1:$(PORT_API); \
	(cd $(APP_DIR) && $(UV) run python -u app-api.py) & \
	API_PID=$$!; \
	trap "kill $$API_PID 2>/dev/null || true" INT TERM EXIT; \
	WEB_FAKE_API_FALLBACK=false APP_API_URL=http://127.0.0.1:$(PORT_API) PORT_WEB=$(PORT_WEB) HOST_WEB=$(HOST_WEB) npm --prefix $(WEB_DIR) run dev

## Alias start-worker vers start-api (la file est désormais intégrée dans l'API Cross-Domains)
start-worker: start-api

## Démarre Streamlit UI et le Worker IA connectés au proxy GCP Cloud Run avec l'infrastructure Docker en mode proxy
start-ui-dev: cloudrun-proxy docker-up-proxy
	@echo -e "$(CYAN)--> Vérification de la disponibilité du serveur llama.cpp (Cloud Run)...$(RESET)"
	@READY=0; \
	for i in {1..30}; do \
		if curl -s -m 2 http://127.0.0.1:$(CLOUDRUN_PORT)/health 2>/dev/null | grep -q '"status":"ok"'; then \
			READY=1; \
			echo -e "  [$(GREEN)PRÊT$(RESET)] Serveur llama.cpp opérationnel."; \
			break; \
		fi; \
		if [ $$i -eq 1 ]; then \
			echo -n "  Attente de démarrage du modèle sur Cloud Run (cold start possible)"; \
		else \
			echo -n "."; \
		fi; \
		sleep 2; \
	done; \
	if [ $$READY -eq 0 ]; then \
		echo -e "\n  [$(YELLOW)ATTENTION$(RESET)] Le serveur llama.cpp n'a pas encore répondu au /health (le chargement du modèle peut encore être en cours)."; \
	fi
	@APP_CONFIGLLM_TYPE=litellm \
	APP_CONFIGLLM_URL=http://127.0.0.1 \
	$(MAKE) start-ui

## Démarre Docker en mode proxy, proxy GCP Cloud Run et l'interface Web Node.js (start-web)
start-web-dev: cloudrun-proxy docker-up-proxy
	@echo -e "$(CYAN)--> Vérification de la disponibilité du serveur llama.cpp (Cloud Run)...$(RESET)"
	@READY=0; \
	for i in {1..30}; do \
		if curl -s -m 2 http://127.0.0.1:$(CLOUDRUN_PORT)/health 2>/dev/null | grep -q '"status":"ok"'; then \
			READY=1; \
			echo -e "  [$(GREEN)PRÊT$(RESET)] Serveur llama.cpp opérationnel."; \
			break; \
		fi; \
		if [ $$i -eq 1 ]; then \
			echo -n "  Attente de démarrage du modèle sur Cloud Run (cold start possible)"; \
		else \
			echo -n "."; \
		fi; \
		sleep 2; \
	done; \
	if [ $$READY -eq 0 ]; then \
		echo -e "\n  [$(YELLOW)ATTENTION$(RESET)] Le serveur llama.cpp n'a pas encore répondu au /health (le chargement du modèle peut encore être en cours)."; \
	fi
	@APP_CONFIGLLM_TYPE=litellm \
	APP_CONFIGLLM_URL=http://127.0.0.1 \
	$(MAKE) start-web

## Lance le proxy Cloud Run en arrière-plan (ou le réutilise s'il est déjà actif) après vérification du login GCP
cloudrun-proxy:
	@echo -e "$(CYAN)--> Vérification de l'authentification GCP (gcloud)...$(RESET)"
	@if ! $(GCLOUD) auth print-access-token --quiet >/dev/null 2>&1; then \
		echo -e "  [$(YELLOW)AUTH$(RESET)] Session GCP expirée ou absente. Lancement de 'gcloud auth login'..."; \
		pkill -f "[g]cloud.*run.*services.*proxy" 2>/dev/null || true; \
		$(GCLOUD) auth login || { echo -e "  [$(RED)ERREUR$(RESET)] Échec de l'authentification GCP."; exit 1; }; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Authentification GCP valide."; \
	fi
	@if ss -tlnp 2>/dev/null | grep -q ":$(CLOUDRUN_PORT) "; then \
		echo -e "  [$(GREEN)OK$(RESET)] Proxy Cloud Run déjà actif sur le port $(CLOUDRUN_PORT)"; \
	else \
		echo -e "$(CYAN)--> Lancement du proxy Cloud Run vers $(CLOUDRUN_SERVICE) sur le port $(CLOUDRUN_PORT) en arrière-plan...$(RESET)"; \
		nohup $(GCLOUD) run services proxy $(CLOUDRUN_SERVICE) --port=$(CLOUDRUN_PORT) --quiet > /tmp/oncoflow-cloudrun-proxy.log 2>&1 & \
		echo -n "  Attente de la disponibilité du proxy"; \
		for i in {1..15}; do \
			if ss -tlnp 2>/dev/null | grep -q ":$(CLOUDRUN_PORT) "; then \
				echo -e " [$(GREEN)PRÊT$(RESET)]"; \
				break; \
			fi; \
			echo -n "."; \
			sleep 1; \
		done; \
		if ! ss -tlnp 2>/dev/null | grep -q ":$(CLOUDRUN_PORT) "; then \
			echo -e "\n  [$(YELLOW)ATTENTION$(RESET)] Le proxy n'a pas encore répondu sur le port $(CLOUDRUN_PORT). Logs (/tmp/oncoflow-cloudrun-proxy.log) :"; \
			cat /tmp/oncoflow-cloudrun-proxy.log 2>/dev/null || true; \
		fi; \
	fi

## Arrête le proxy Cloud Run
cloudrun-proxy-stop:
	@echo -e "$(YELLOW)--> Arrêt du proxy Cloud Run...$(RESET)"
	@if pgrep -f "[g]cloud.*run.*services.*proxy" >/dev/null 2>&1; then \
		pkill -f "[g]cloud.*run.*services.*proxy" 2>/dev/null && echo -e "  [$(RED)ARRÊTÉ$(RESET)] Cloud Run Proxy"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Cloud Run Proxy n'est pas actif"; \
	fi

# Raccourcis et alias
api: start-api
ui: start-ui
web: start-web
worker: start-worker
ui-dev: start-ui-dev
web-dev: start-web-dev
start-dev: start-ui-dev
start: start-ui
proxy: cloudrun-proxy
proxy-stop: cloudrun-proxy-stop

## Démarre l'API en arrière-plan puis le Worker IA et Streamlit au premier plan (sortie partagée sur stdout)
dev:
	@echo -e "$(CYAN)--> Démarrage du mode développement complet (API + Worker + UI)...$(RESET)"
	@$(MAKE) stop >/dev/null 2>&1
	@echo -e "  Démarrage de l'API en tâche de fond..."
	@nohup bash -c "cd $(APP_DIR) && $(UV) run python app-api.py" > /tmp/oncoflow-api.log 2>&1 &
	@sleep 2
	@$(MAKE) start-ui

## Arrête les processus actifs (Streamlit, Web UI Node.js, Worker, API FastAPI, proxy Cloud Run)
stop: cloudrun-proxy-stop docker-down
	@echo -e "$(YELLOW)--> Arrêt des processus applicatifs...$(RESET)"
	@if pgrep -f "[s]treamlit run app-ui.py" >/dev/null 2>&1; then \
		pkill -f "[s]treamlit run app-ui.py" 2>/dev/null && echo -e "  [$(RED)ARRÊTÉ$(RESET)] Streamlit UI"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Streamlit UI n'est pas actif"; \
	fi
	@if pgrep -f "[t]sx.*src/main.ts|[n]ode.*dist/main.js" >/dev/null 2>&1; then \
		pkill -f "[t]sx.*src/main.ts|[n]ode.*dist/main.js" 2>/dev/null && echo -e "  [$(RED)ARRÊTÉ$(RESET)] Web UI (Node.js Fastify)"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Web UI (Node.js Fastify) n'est pas active"; \
	fi
	@if pgrep -f "[p]ython.*app-worker.py" >/dev/null 2>&1; then \
		pkill -f "[p]ython.*app-worker.py" 2>/dev/null && echo -e "  [$(RED)ARRÊTÉ$(RESET)] Queue Worker"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Queue Worker n'est pas actif"; \
	fi
	@if pgrep -f "[p]ython.*app-api.py" >/dev/null 2>&1; then \
		pkill -f "[p]ython.*app-api.py" 2>/dev/null && echo -e "  [$(RED)ARRÊTÉ$(RESET)] FastAPI App"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] FastAPI App n'est pas active"; \
	fi
	@echo -e "$(GREEN)Terminé.$(RESET)"

## Lance la suite de tests Pytest
test:
	@echo -e "$(CYAN)--> Exécution des tests Pytest...$(RESET)"
	cd $(APP_DIR) && $(UV) run pytest

## Exécute les tests unitaires et d'intégration Vitest de web/
test-web:
	@echo -e "$(CYAN)--> Exécution des tests unitaires et d'intégration Vitest ($(WEB_DIR))...$(RESET)"
	npm --prefix $(WEB_DIR) run test

## Mesure le pourcentage de couverture de test du code source
coverage:
	@echo -e "$(CYAN)--> Calcul de la couverture de tests (pytest-cov)...$(RESET)"
	cd $(APP_DIR) && PYTHONPATH=. $(UV) run pytest --cov=src --cov-report=term-missing tests/


## Analyse la qualité et le style du code avec Ruff
lint:
	@echo -e "$(CYAN)--> Vérification Ruff sur src/...$(RESET)"
	cd $(APP_DIR) && $(UV) run ruff check src/

## Vérifie le code TypeScript/CSS de web/ avec Biome, tsc --noEmit et check-contrast.mjs
lint-web:
	@echo -e "$(CYAN)--> Vérification Biome, TypeScript et contraste WCAG sur $(WEB_DIR)/...$(RESET)"
	npm --prefix $(WEB_DIR) run lint

## Applique le formatage automatique avec Ruff
format:
	@echo -e "$(CYAN)--> Formatage Ruff sur src/...$(RESET)"
	cd $(APP_DIR) && $(UV) run ruff format src/

## Formate le code de web/ avec Biome
format-web:
	@echo -e "$(CYAN)--> Formatage Biome sur $(WEB_DIR)/...$(RESET)"
	npm --prefix $(WEB_DIR) run format

## Exécute les tests end-to-end Playwright de web/
e2e-web:
	@echo -e "$(CYAN)--> Exécution des tests end-to-end Playwright ($(WEB_DIR))...$(RESET)"
	npm --prefix $(WEB_DIR) run e2e

## Compile le code TypeScript de web/ vers web/dist/
build-web:
	@echo -e "$(CYAN)--> Compilation TypeScript de $(WEB_DIR)/...$(RESET)"
	npm --prefix $(WEB_DIR) run build

## Construit l'image Docker durcie de l'interface web Node.js (dist/docker/Dockerfile.web)
docker-build-web:
	@echo -e "$(CYAN)--> Construction de l'image Docker Web ($${ONCOFLOW_WEB_IMAGE:-ghcr.io/oncoflow/oncoflow-web}:$${ONCOFLOW_TAG:-latest})...$(RESET)"
	docker build -f dist/docker/Dockerfile.web -t $${ONCOFLOW_WEB_IMAGE:-ghcr.io/oncoflow/oncoflow-web}:$${ONCOFLOW_TAG:-latest} .
	@echo -e "$(GREEN)--> Image Docker Web construite avec succès !$(RESET)"

## Récupère et affiche les rapports de bugs stockés dans MongoDB
get-bugs:
	@echo -e "$(CYAN)--> Récupération des rapports de bugs depuis MongoDB...$(RESET)"
	@cd $(APP_DIR) && $(UV) run python scripts/get_bugs.py


## Initialise le replica set MongoDB (rs0) si nécessaire
mongo-init:
	@echo -e "$(CYAN)--> Initialisation / vérification du Replica Set MongoDB (rs0)...$(RESET)"
	@cd $(APP_DIR) && $(UV) run python -c "import time, sys; from pymongo import MongoClient; \
c = MongoClient('mongodb://root:root@127.0.0.1:27017/?directConnection=true&authSource=admin', serverSelectionTimeoutMS=2000); \
h = c.admin.command('hello'); \
(print('  [OK] MongoDB Replica Set déjà initialisé (Primary actif)'), sys.exit(0)) if h.get('isWritablePrimary') else None; \
c.admin.command('replSetInitiate', {'_id': 'rs0', 'members': [{'_id': 0, 'host': '127.0.0.1:27017'}]}); \
print('  [OK] MongoDB Replica Set (rs0) initialisé avec succès')" 2>/dev/null || echo -e "  [$(GREEN)OK$(RESET)] MongoDB Replica Set prêt."

## Démarre les services d'infrastructure Docker (Milvus & MongoDB)
docker-up:
	@mkdir -p $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs}
	@chmod 777 $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs} 2>/dev/null || true
	@echo -e "$(CYAN)--> Démarrage de Milvus Standalone...$(RESET)"
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) up -d
	@echo -e "$(CYAN)--> Démarrage des services communs (MongoDB)...$(RESET)"
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_DEV) up -d

## Démarre les conteneurs en mode proxy (Milvus, MongoDB, embeddings - sans chat local)
docker-up-proxy:
	@mkdir -p $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs}
	@chmod 777 $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs} 2>/dev/null || true
	@echo -e "$(CYAN)--> Démarrage de Milvus Standalone...$(RESET)"
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) up -d
	@echo -e "$(CYAN)--> Démarrage des services en mode proxy (MongoDB + embeddings, sans chat local)...$(RESET)"
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_DEV) --profile llamacpp up -d

## Met à jour les images Docker de développement (Milvus v3.0 & MongoDB) et recrée les conteneurs si actifs
docker-update:
	@mkdir -p $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs}
	@chmod 777 $(DEV_VOLUME_DIR)/{mongodb,mongodb_config,milvus,etcd,minio,logs} 2>/dev/null || true
	@echo -e "$(CYAN)--> Mise à jour des images Docker (Milvus Standalone v3.0 & MongoDB)...$(RESET)"
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) pull
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) run --rm milvus-volume-init
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_DEV) pull
	@if docker ps --format '{{.Names}}' | grep -q '^milvus-standalone$$'; then \
		echo -e "$(CYAN)--> Recréation des conteneurs Milvus actifs...$(RESET)"; \
		DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) up -d; \
	fi
	@if docker ps --format '{{.Names}}' | grep -q '^oncoflow-mongod$$'; then \
		echo -e "$(CYAN)--> Recréation des conteneurs MongoDB actifs...$(RESET)"; \
		DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_DEV) up -d; \
	fi

## Arrête les services d'infrastructure Docker
docker-down:
	@echo -e "$(YELLOW)--> Arrêt des conteneurs Docker...$(RESET)"
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_MILVUS) down --remove-orphans
	DOCKER_VOLUME_DIRECTORY=$(DEV_VOLUME_DIR) docker compose -f $(COMPOSE_DEV) down --remove-orphans

## Vérifie l'état des conteneurs Docker de la plateforme
docker-status:
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

## Télécharge les modèles recommandés dans Ollama local
pull-models:
	@echo -e "$(CYAN)--> Téléchargement des modèles Ollama (Embeddings, VLM, Raisonnement)...$(RESET)"
	ollama pull nomic-embed-text
	ollama pull granite3.2-vision
	ollama pull mistral-nemo

## Affiche le statut d'écoute des différents ports et processus Oncoflow
status:
	@echo -e "$(CYAN)=== État des services Oncoflow ===$(RESET)"
	@echo -n "FastAPI (port $(PORT_API)) : "
	@ss -tlnp 2>/dev/null | grep -q ":$(PORT_API) " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "Streamlit (port $(PORT_UI)) : "
	@ss -tlnp 2>/dev/null | grep -q ":$(PORT_UI) " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "Web UI Node.js (port $(PORT_WEB)) : "
	@ss -tlnp 2>/dev/null | grep -q ":$(PORT_WEB) " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "Queue Worker (app-worker.py) : "
	@pgrep -f "[p]ython.*app-worker.py" >/dev/null 2>&1 && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "Cloud Run Proxy (port $(CLOUDRUN_PORT)) : "
	@ss -tlnp 2>/dev/null | grep -q ":$(CLOUDRUN_PORT) " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "Milvus (port 19530) : "
	@ss -tlnp 2>/dev/null | grep -q ":19530 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "MongoDB (port 27017) : "
	@ss -tlnp 2>/dev/null | grep -q ":27017 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "Ollama local (port 11434) : "
	@ss -tlnp 2>/dev/null | grep -q ":11434 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"

## Nettoie les fichiers temporaires et les caches
clean:
	@echo -e "$(YELLOW)--> Nettoyage des caches...$(RESET)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(WEB_DIR)/dist $(WEB_DIR)/playwright-report $(WEB_DIR)/test-results 2>/dev/null || true
	@echo -e "$(GREEN)Caches nettoyés avec succès.$(RESET)"

# ==============================================================================
# Cibles de Production (Scaleway L4 24G + OAuth2 Proxy GitHub + Caddy TLS)
# ==============================================================================

## Initialise l'environnement de production (droits docker/sudoers, .env.prod, dossiers de volumes, logrotate et modèles GGUF)
init-prod:
	@echo -e "$(CYAN)--> Vérification des prérequis de production (Scaleway L4)...$(RESET)"
	@command -v docker >/dev/null 2>&1 || { echo -e "  [$(RED)ERREUR$(RESET)] Docker n'est pas installé."; exit 1; }
	@$(MAKE) sudoers-prod
	@if command -v nvidia-smi >/dev/null 2>&1; then \
		echo -e "  [$(GREEN)OK$(RESET)] GPU NVIDIA détecté : $$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -n1)"; \
	else \
		echo -e "  [$(YELLOW)ATTENTION$(RESET)] nvidia-smi non détecté. Vérifiez les drivers NVIDIA et nvidia-container-toolkit."; \
	fi
	@echo -e "$(CYAN)--> Création des répertoires de volumes persistants et des dossiers de domaines (oncology & sma)...$(RESET)"
	@mkdir -p dist/docker/compose/volumes/{mongodb,mongodb_config,milvus,etcd,minio,models,logs,caddy_data,caddy_config}
	@mkdir -p /data/meddatasyntis/common/{mongodb,mongodb_config,milvus,etcd,minio,models,logs,queue,caddy_data,caddy_config} 2>/dev/null || true
	@mkdir -p /data/meddatasyntis/oncologic/{mtd,documents} /data/meddatasyntis/sma/{mtd,documents} 2>/dev/null || true
	@mkdir -p application/ressources/PatientMDTForm/{oncology,sma} application/ressources/documents/{oncology,sma}
	@chmod 777 dist/docker/compose/volumes/{mongodb,mongodb_config,logs} 2>/dev/null || true
	@chmod 777 /data/meddatasyntis/common/{mongodb,mongodb_config,milvus,etcd,minio,logs,queue} 2>/dev/null || true
	@if [ ! -f "$(ENV_PROD)" ]; then \
		echo -e "$(CYAN)--> Génération de $(ENV_PROD) depuis .env.prod.example...$(RESET)"; \
		cp .env.prod.example "$(ENV_PROD)"; \
		COOKIE_SEC=$$(openssl rand -base64 32 | tr -- '+/' '-_'); \
		LITELLM_KEY="sk-$$(openssl rand -hex 32)"; \
		sed -i "s|OAUTH2_PROXY_COOKIE_SECRET=.*|OAUTH2_PROXY_COOKIE_SECRET=$${COOKIE_SEC}|" "$(ENV_PROD)"; \
		sed -i "s|LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=$${LITELLM_KEY}|" "$(ENV_PROD)"; \
		sed -i "s|APP_API_TOKEN=.*|APP_API_TOKEN=$$(openssl rand -hex 32)|" "$(ENV_PROD)"; \
		sed -i "s|APP_PROXY_SECRET=.*|APP_PROXY_SECRET=$$(openssl rand -hex 32)|" "$(ENV_PROD)"; \
		echo -e "  [$(YELLOW)ACTION REQUISE$(RESET)] Renseignez OAUTH2_PROXY_CLIENT_ID et OAUTH2_PROXY_CLIENT_SECRET dans $(ENV_PROD)"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Fichier $(ENV_PROD) déjà présent."; \
	fi
	@echo -e "$(CYAN)--> Initialisation du volume Milvus v3.0 (milvus-volume-init)...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) pull
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) run --rm milvus-volume-init
	@$(MAKE) logrotate-prod
	@$(MAKE) pull-models-prod
	@echo -e "$(GREEN)--> Initialisation de production terminée.$(RESET)"

## Installe /etc/sudoers.d/meddatasyntis (Ubuntu 24.04+) pour l'utilisateur courant
sudoers-prod:
	@echo -e "$(CYAN)--> Configuration sudoers (Ubuntu 24.04+) pour l'utilisateur '$(DEPLOY_USER)'...$(RESET)"
	@mkdir -p dist/docker/compose/volumes/logs
	@sed "s|__DEPLOY_USER__|$(DEPLOY_USER)|g" dist/sudoers/meddatasyntis > dist/docker/compose/volumes/logs/meddatasyntis.sudoers
	@if sudo visudo -cf dist/docker/compose/volumes/logs/meddatasyntis.sudoers >/dev/null 2>&1; then \
		sudo cp dist/docker/compose/volumes/logs/meddatasyntis.sudoers /etc/sudoers.d/meddatasyntis && \
		sudo chown root:root /etc/sudoers.d/meddatasyntis && \
		sudo chmod 0440 /etc/sudoers.d/meddatasyntis && \
		echo -e "  [$(GREEN)OK$(RESET)] Règle sudoers installée et validée dans /etc/sudoers.d/meddatasyntis (mode 0440)."; \
	else \
		echo -e "  [$(YELLOW)INFO$(RESET)] Fichier généré : dist/docker/compose/volumes/logs/meddatasyntis.sudoers"; \
		echo -e "  [$(YELLOW)INFO$(RESET)] Pour l'installer : sudo cp $(CURDIR)/dist/docker/compose/volumes/logs/meddatasyntis.sudoers /etc/sudoers.d/meddatasyntis && sudo chmod 0440 /etc/sudoers.d/meddatasyntis"; \
	fi

## Génère et installe la configuration logrotate pour les logs applicatifs MedDataSyntis
logrotate-prod:
	@echo -e "$(CYAN)--> Configuration de logrotate pour MedDataSyntis...$(RESET)"
	@mkdir -p dist/docker/compose/volumes/logs
	@chmod 777 dist/docker/compose/volumes/logs 2>/dev/null || true
	@sed "s|__MEDDATASYNTIS_LOG_DIR__|$(CURDIR)/dist/docker/compose/volumes/logs|g" dist/logrotate/meddatasyntis > dist/docker/compose/volumes/logs/meddatasyntis.logrotate
	@if sudo cp dist/docker/compose/volumes/logs/meddatasyntis.logrotate /etc/logrotate.d/meddatasyntis 2>/dev/null && sudo chown root:root /etc/logrotate.d/meddatasyntis 2>/dev/null && sudo chmod 644 /etc/logrotate.d/meddatasyntis 2>/dev/null; then \
		echo -e "  [$(GREEN)OK$(RESET)] Configuration installée dans /etc/logrotate.d/meddatasyntis"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Fichier généré : dist/docker/compose/volumes/logs/meddatasyntis.logrotate"; \
		echo -e "  [$(YELLOW)INFO$(RESET)] Pour l'activer au niveau système : sudo cp $(CURDIR)/dist/docker/compose/volumes/logs/meddatasyntis.logrotate /etc/logrotate.d/meddatasyntis && sudo chmod 644 /etc/logrotate.d/meddatasyntis"; \
	fi

## Télécharge les modèles GGUF de production (Ornith-1.5-35B-A3B IQ4_XS & bge-m3 Q4_K_M)
pull-models-prod:
	@mkdir -p "$(MODELS_DIR)"
	@echo -e "$(CYAN)--> Vérification / téléchargement du modèle d'embeddings (bge-m3-Q4_K_M.gguf)...$(RESET)"
	@if [ -f "$(EMBED_MODEL_FILE)" ]; then \
		echo -e "  [$(GREEN)OK$(RESET)] $(EMBED_MODEL_FILE) déjà présent."; \
	else \
		curl -fL -C - -o "$(EMBED_MODEL_FILE).part" "$(EMBED_MODEL_URL)" && mv "$(EMBED_MODEL_FILE).part" "$(EMBED_MODEL_FILE)"; \
		echo -e "  [$(GREEN)OK$(RESET)] Modèle d'embeddings téléchargé."; \
	fi
	@echo -e "$(CYAN)--> Vérification / téléchargement du modèle LLM L4 (Ornith-1.5-35B-A3B-IQ4_XS.gguf ~19.3 Go)...$(RESET)"
	@if [ -f "$(CHAT_MODEL_FILE)" ]; then \
		echo -e "  [$(GREEN)OK$(RESET)] $(CHAT_MODEL_FILE) déjà présent."; \
	else \
		curl -fL -C - -o "$(CHAT_MODEL_FILE).part" "$(CHAT_MODEL_URL)" && mv "$(CHAT_MODEL_FILE).part" "$(CHAT_MODEL_FILE)"; \
		echo -e "  [$(GREEN)OK$(RESET)] Modèle Ornith-1.5-35B-A3B téléchargé."; \
	fi

## Initialise le Replica Set MongoDB (rs0) directement dans le conteneur mongod
mongo-init-prod:
	@echo -e "$(CYAN)--> Initialisation / vérification du Replica Set MongoDB (rs0) en prod...$(RESET)"
	@for i in {1..15}; do \
		if docker exec oncoflow-mongod mongosh --quiet --eval "db.runCommand({ ping: 1 })" >/dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@docker exec oncoflow-mongod mongosh --quiet -u "$${APP_MONGODB_USER:-root}" -p "$${APP_MONGODB_PASSWORD:-root}" --authenticationDatabase admin --eval ' \
		try { \
			var s = rs.status(); \
			if (s.ok === 1) { print("  [OK] MongoDB Replica Set (rs0) déjà actif."); quit(0); } \
		} catch (e) {} \
		rs.initiate({_id: "rs0", members: [{_id: 0, host: "127.0.0.1:27017"}]}); \
		print("  [OK] MongoDB Replica Set (rs0) initialisé."); \
	' 2>/dev/null || echo -e "  [$(GREEN)OK$(RESET)] MongoDB Replica Set prêt."

## Construit les images Docker applicatives de production (Python FastAPI/Streamlit + Node.js Web UI M3)
build-prod: docker-build-web
	@echo -e "$(CYAN)--> Construction de l'image Docker de production ($${ONCOFLOW_IMAGE:-ghcr.io/oncoflow/oncoflow}:$${ONCOFLOW_TAG:-latest})...$(RESET)"
	docker build -f dist/docker/Dockerfile -t $${ONCOFLOW_IMAGE:-ghcr.io/oncoflow/oncoflow}:$${ONCOFLOW_TAG:-latest} .
	@echo -e "$(GREEN)--> Images Docker de production (App + Web M3) construites avec succès !$(RESET)"

## Démarre les conteneurs Docker de production (Multi-Domaines Oncology & SMA + Web M3 oncologic-new & sma-new)
docker-up-prod:
	@if [ ! -f "$(ENV_PROD)" ]; then \
		echo -e "  [$(RED)ERREUR$(RESET)] Fichier $(ENV_PROD) introuvable. Lancez d'abord 'make init-prod' et configurez vos identifiants GitHub OAuth."; \
		exit 1; \
	fi
	@if grep -q "votre_github_client_id" "$(ENV_PROD)"; then \
		echo -e "  [$(YELLOW)ATTENTION$(RESET)] OAUTH2_PROXY_CLIENT_ID contient encore la valeur par défaut dans $(ENV_PROD) !"; \
	fi
	@mkdir -p /data/meddatasyntis/common/{mongodb,mongodb_config,milvus,etcd,minio,models,logs,queue,caddy_data,caddy_config} 2>/dev/null || true
	@mkdir -p /data/meddatasyntis/oncologic/{mtd,documents} /data/meddatasyntis/sma/{mtd,documents} 2>/dev/null || true
	@chmod 777 /data/meddatasyntis/common/{mongodb,mongodb_config,milvus,etcd,minio,logs,queue} 2>/dev/null || true
	@echo -e "$(CYAN)--> Démarrage de Milvus Standalone...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) up -d
	@echo -e "$(CYAN)--> Préparation de l'image Web UI M3 (oncoflow-web pour oncologic-new & sma-new)...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) pull oncoflow-web 2>/dev/null || docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) build oncoflow-web
	@echo -e "$(CYAN)--> Démarrage de la stack de production MedDataSyntis (L4 GPU + Streamlit & Web M3 Oncology/SMA + OAuth2 Proxy + Caddy)...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) up -d
	@docker exec oncoflow-caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true

## Démarre toute la stack de production et attend la disponibilité des modèles LLM
start-prod: docker-up-prod
	@echo -e "$(CYAN)--> Vérification du chargement de Ornith-1.5-35B-A3B sur le GPU L4 (port 8080)...$(RESET)"
	@READY=0; \
	for i in {1..60}; do \
		if curl -s -m 2 http://127.0.0.1:8080/health 2>/dev/null | grep -q '"status":"ok"'; then \
			READY=1; \
			echo -e "\n  [$(GREEN)PRÊT$(RESET)] Serveur llama.cpp Chat (Ornith-1.5-35B-A3B) opérationnel sur L4."; \
			break; \
		fi; \
		if [ $$i -eq 1 ]; then \
			echo -n "  Chargement du modèle en VRAM (peut prendre 20 à 60s)"; \
		else \
			echo -n "."; \
		fi; \
		sleep 2; \
	done; \
	if [ $$READY -eq 0 ]; then \
		echo -e "\n  [$(YELLOW)INFO$(RESET)] Le chargement du modèle se poursuit en arrière-plan (voir 'make logs-prod')."; \
	fi
	@BASE_DOM=$$(grep -E '^PROD_BASE_DOMAIN=' "$(ENV_PROD)" 2>/dev/null | cut -d= -f2 || echo "$(PROD_BASE_DOMAIN)"); \
	BASE_DOM=$${BASE_DOM:-$(PROD_BASE_DOMAIN)}; \
	echo -e "$(GREEN)======================================================================$(RESET)"; \
	echo -e "  🚀 MedDataSyntis Production actif sur :"; \
	echo -e "     • Oncologie (Streamlit)     : $(CYAN)https://oncologic.$${BASE_DOM}$(RESET)"; \
	echo -e "     • Amyotrophie spinale (UI)  : $(CYAN)https://sma.$${BASE_DOM}$(RESET)"; \
	echo -e "     • Oncologie (Nouvelle M3)   : $(CYAN)https://oncologic-new.$${BASE_DOM}$(RESET)"; \
	echo -e "     • Amyotrophie spinale (M3)  : $(CYAN)https://sma-new.$${BASE_DOM}$(RESET)"; \
	echo -e "$(GREEN)======================================================================$(RESET)"

## Arrête tous les conteneurs de la stack de production (conserve les volumes de données)
stop-prod:
	@echo -e "$(YELLOW)--> Arrêt de la stack de production MedDataSyntis...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) down --remove-orphans
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) down --remove-orphans
	@echo -e "$(GREEN)--> Stack de production arrêtée.$(RESET)"

docker-down-prod: stop-prod
up-prod: start-prod
down-prod: stop-prod
prod: start-prod
pprod: start-prod

## Redémarre uniquement les services applicatifs et proxy (sans décharger le LLM de la VRAM L4)
restart-prod:
	@echo -e "$(CYAN)--> Redémarrage des services applicatifs (UIs Streamlit, Web M3 oncologic-new/sma-new, API Cross-Domains, OAuth2 Proxy, Caddy, LiteLLM) sans toucher au GPU...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) restart litellm oncoflow-ui-oncology oncoflow-ui-sma oncoflow-web oncoflow-api oauth2-proxy caddy
	@echo -e "$(GREEN)--> Services applicatifs redémarrés.$(RESET)"

## Met à jour le dépôt git, Milvus v3.0 et les images Docker UI/Web M3 sans décharger le modèle LLM du GPU
prod-update:
	@echo -e "$(CYAN)--> [1/5] Mise à jour du code source (git pull --ff-only)...$(RESET)"
	git pull --ff-only
	@echo -e "$(CYAN)--> [2/5] Mise à jour de Milvus Standalone (v3.0)...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) pull
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) up -d
	@echo -e "$(CYAN)--> [3/5] Téléchargement / construction des dernières images applicatives (UIs Streamlit, Web M3 oncologic-new/sma-new, oncoflow-api, oauth2-proxy, caddy, litellm)...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) pull oncoflow-ui-oncology oncoflow-ui-sma oncoflow-api oauth2-proxy caddy litellm
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) build oncoflow-web
	@echo -e "$(CYAN)--> [4/5] Recréation à chaud des conteneurs applicatifs (LLM conservé en VRAM)...$(RESET)"
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) up -d --no-deps oncoflow-ui-oncology oncoflow-ui-sma oncoflow-web oncoflow-api oauth2-proxy caddy litellm
	@docker exec oncoflow-caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) restart caddy
	@echo -e "$(CYAN)--> [5/5] Nettoyage des anciennes images Docker inutilisées...$(RESET)"
	@docker image prune -f >/dev/null 2>&1 || true
	@$(MAKE) status-prod
	@echo -e "$(GREEN)--> Mise à jour de production (prod-update) terminée avec succès !$(RESET)"

## Met à jour l'intégralité de la stack de production (y compris les images LLM, Milvus, MongoDB et Web M3)
prod-update-all:
	@echo -e "$(CYAN)--> Mise à jour complète de la stack de production (infra + LLM + UIs Streamlit + Web M3)...$(RESET)"
	git pull --ff-only
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) pull
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) pull --ignore-buildable
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) build oncoflow-web
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_MILVUS) up -d
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) up -d
	@docker exec oncoflow-caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) restart caddy
	@docker image prune -f >/dev/null 2>&1 || true
	@$(MAKE) status-prod

## Affiche l'état complet des services de production et de la VRAM GPU L4
status-prod:
	@echo -e "$(CYAN)=== État des services MedDataSyntis (PRODUCTION) ===$(RESET)"
	@echo -n "Caddy HTTPS (port 443)            : "
	@ss -tlnp 2>/dev/null | grep -q ":443 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "OAuth2 Proxy GitHub SSO (4180)    : "
	@ss -tlnp 2>/dev/null | grep -q ":4180 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "API Cross-Domains (port 8000)     : "
	@ss -tlnp 2>/dev/null | grep -q ":8000 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "Web M3 oncologic-new/sma-new(3000): "
	@ss -tlnp 2>/dev/null | grep -q ":3000 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "UI Oncology GHCR (port 8501)      : "
	@ss -tlnp 2>/dev/null | grep -q ":8501 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "UI SMA GHCR (port 8502)           : "
	@ss -tlnp 2>/dev/null | grep -q ":8502 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "LiteLLM Proxy (port 4000)         : "
	@ss -tlnp 2>/dev/null | grep -q ":4000 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "llama.cpp Chat L4 (port 8080)     : "
	@if curl -s -m 2 http://127.0.0.1:8080/health 2>/dev/null | grep -q '"status":"ok"'; then \
		echo -e "$(GREEN)PRÊT (Modèle chargé en VRAM)$(RESET)"; \
	elif ss -tlnp 2>/dev/null | grep -q ":8080 "; then \
		echo -e "$(YELLOW)CHARGEMENT EN COURS...$(RESET)"; \
	else \
		echo -e "$(RED)INACTIF$(RESET)"; \
	fi
	@echo -n "llama.cpp Embed (port 8081)       : "
	@if curl -s -m 2 http://127.0.0.1:8081/health 2>/dev/null | grep -q '"status":"ok"'; then \
		echo -e "$(GREEN)PRÊT$(RESET)"; \
	elif ss -tlnp 2>/dev/null | grep -q ":8081 "; then \
		echo -e "$(YELLOW)CHARGEMENT EN COURS...$(RESET)"; \
	else \
		echo -e "$(RED)INACTIF$(RESET)"; \
	fi
	@echo -n "Milvus Vector DB (port 19530)     : "
	@ss -tlnp 2>/dev/null | grep -q ":19530 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@echo -n "MongoDB ReplicaSet (27017)        : "
	@ss -tlnp 2>/dev/null | grep -q ":27017 " && echo -e "$(GREEN)ACTIF$(RESET)" || echo -e "$(RED)INACTIF$(RESET)"
	@if command -v nvidia-smi >/dev/null 2>&1; then \
		echo ""; \
		echo -e "$(CYAN)=== Utilisation GPU NVIDIA L4 ===$(RESET)"; \
		nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=table; \
	fi

## Affiche les journaux en temps réel de la stack de production
logs-prod:
	docker compose --env-file $(ENV_PROD) -f $(COMPOSE_PROD) logs -f --tail=100
