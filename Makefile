# ==============================================================================
# Oncoflow Makefile
# Outil de gestion des services, du développement et de l'infrastructure locale
# ==============================================================================

SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(HOME)/google-cloud-sdk/bin:$(PATH)

# Détection de l'exécutable uv et gcloud
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
GCLOUD := $(shell command -v gcloud 2>/dev/null || echo $(HOME)/google-cloud-sdk/bin/gcloud)

# Dossier de l'application
APP_DIR := application

# Ports et configurations configurables
PORT_UI ?= 8501
PORT_API ?= 8000
HOST_API ?= 127.0.0.1
CLOUDRUN_SERVICE ?= llama-cpp-chat
CLOUDRUN_PORT ?= 8080

# Couleurs pour le terminal
CYAN  := \033[36m
GREEN := \033[32m
YELLOW:= \033[33m
RED   := \033[31m
RESET := \033[0m

.DEFAULT_GOAL := help

.PHONY: help install upgrade start-api start-ui start-ui-dev cloudrun-proxy cloudrun-proxy-stop stop test eval-rcp lint format docker-up docker-up-proxy docker-down docker-status pull-models clean status api ui ui-dev proxy proxy-stop dev

## Affiche l'aide et la liste des commandes disponibles
help:
	@echo -e "$(CYAN)Usage: make <commande>$(RESET)"
	@echo ""
	@echo -e "$(GREEN)Commandes principales :$(RESET)"
	@echo -e "  $(YELLOW)make install$(RESET)             Installe les dépendances via uv sync"
	@echo -e "  $(YELLOW)make upgrade$(RESET)             Met à jour toutes les dépendances (uv lock --upgrade && uv sync)"
	@echo -e "  $(YELLOW)make start-api$(RESET)           Démarre l'API FastAPI (port $(PORT_API))"
	@echo -e "  $(YELLOW)make start-ui$(RESET)            Démarre le dashboard Streamlit (port $(PORT_UI))"
	@echo -e "  $(YELLOW)make start-ui-dev$(RESET)        Démarre Docker en mode proxy, proxy GCP et Streamlit UI"
	@echo -e "  $(YELLOW)make cloudrun-proxy$(RESET)      Lance le proxy Cloud Run en tâche de fond (port $(CLOUDRUN_PORT))"
	@echo -e "  $(YELLOW)make cloudrun-proxy-stop$(RESET) Arrête le proxy Cloud Run"
	@echo -e "  $(YELLOW)make stop$(RESET)                Arrête l'UI, l'API et le proxy Cloud Run"
	@echo ""
	@echo -e "$(GREEN)Commandes de qualité & tests :$(RESET)"
	@echo -e "  $(YELLOW)make test$(RESET)             Exécute la suite de tests Pytest"
	@echo -e "  $(YELLOW)make eval-rcp$(RESET)         Évalue le LLM configuré sur les fiches RCP synthétiques (ex. via Bifrost)"
	@echo -e "  $(YELLOW)make lint$(RESET)             Vérifie le code avec Ruff"
	@echo -e "  $(YELLOW)make format$(RESET)           Formate le code avec Ruff"
	@echo ""
	@echo -e "$(GREEN)Commandes d'infrastructure & Ollama :$(RESET)"
	@echo -e "  $(YELLOW)make docker-up$(RESET)        Démarre Milvus et MongoDB via Docker Compose"
	@echo -e "  $(YELLOW)make docker-up-proxy$(RESET)  Démarre Docker en mode proxy (Milvus + MongoDB + embeddings)"
	@echo -e "  $(YELLOW)make docker-down$(RESET)      Arrête les conteneurs Milvus et MongoDB"
	@echo -e "  $(YELLOW)make docker-status$(RESET)    Vérifie l'état des conteneurs Docker"
	@echo -e "  $(YELLOW)make pull-models$(RESET)      Télécharge les modèles recommandés dans Ollama local"
	@echo -e "  $(YELLOW)make status$(RESET)           Affiche l'état des services et des ports"
	@echo -e "  $(YELLOW)make clean$(RESET)            Nettoie les caches (__pycache__, .pytest_cache, .ruff_cache)"
	@echo ""

## Installe l'environnement virtuel et les dépendances du projet
install:
	@echo -e "$(CYAN)--> Installation des dépendances avec uv sync...$(RESET)"
	cd $(APP_DIR) && $(UV) sync

## Met à jour l'ensemble des paquets et synchronise l'environnement
upgrade:
	@echo -e "$(CYAN)--> Mise à jour des paquets avec uv lock --upgrade && uv sync...$(RESET)"
	cd $(APP_DIR) && $(UV) lock --upgrade && $(UV) sync

## Démarre l'API FastAPI (src/routers, uvicorn)
start-api:
	@echo -e "$(CYAN)--> Démarrage de l'API FastAPI sur http://$(HOST_API):$(PORT_API)...$(RESET)"
	cd $(APP_DIR) && $(UV) run python app-api.py

## Démarre l'interface utilisateur Streamlit
start-ui:
	@echo -e "$(CYAN)--> Démarrage de Streamlit UI sur http://localhost:$(PORT_UI)...$(RESET)"
	cd $(APP_DIR) && $(UV) run streamlit run app-ui.py --server.port=$(PORT_UI)

## Démarre Streamlit UI connecté au proxy GCP Cloud Run avec l'infrastructure Docker en mode proxy (sans chat local)
start-ui-dev: docker-up-proxy cloudrun-proxy
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

## Lance le proxy Cloud Run en arrière-plan (ou le réutilise s'il est déjà actif)
cloudrun-proxy:
	@if ss -tlnp 2>/dev/null | grep -q ":$(CLOUDRUN_PORT) "; then \
		echo -e "  [$(GREEN)OK$(RESET)] Proxy Cloud Run déjà actif sur le port $(CLOUDRUN_PORT)"; \
	else \
		echo -e "$(CYAN)--> Lancement du proxy Cloud Run vers $(CLOUDRUN_SERVICE) sur le port $(CLOUDRUN_PORT) en arrière-plan...$(RESET)"; \
		nohup $(GCLOUD) run services proxy $(CLOUDRUN_SERVICE) --port=$(CLOUDRUN_PORT) > /tmp/oncoflow-cloudrun-proxy.log 2>&1 & \
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
			echo -e "\n  [$(YELLOW)ATTENTION$(RESET)] Le proxy n'a pas encore répondu sur le port $(CLOUDRUN_PORT). Logs : /tmp/oncoflow-cloudrun-proxy.log"; \
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
ui-dev: start-ui-dev
start: start-ui
proxy: cloudrun-proxy
proxy-stop: cloudrun-proxy-stop

## Démarre l'API en arrière-plan puis Streamlit au premier plan
dev:
	@echo -e "$(CYAN)--> Démarrage du mode développement complet (API + UI)...$(RESET)"
	@$(MAKE) stop >/dev/null 2>&1
	@echo -e "  Démarrage de l'API en tâche de fond..."
	@nohup bash -c "cd $(APP_DIR) && $(UV) run python app-api.py" > /tmp/oncoflow-api.log 2>&1 &
	@sleep 2
	@$(MAKE) start-ui

## Arrête les processus actifs (Streamlit, API FastAPI, proxy Cloud Run)
stop: cloudrun-proxy-stop docker-down
	@echo -e "$(YELLOW)--> Arrêt des processus applicatifs...$(RESET)"
	@if pgrep -f "[s]treamlit run app-ui.py" >/dev/null 2>&1; then \
		pkill -f "[s]treamlit run app-ui.py" 2>/dev/null && echo -e "  [$(RED)ARRÊTÉ$(RESET)] Streamlit UI"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Streamlit UI n'est pas actif"; \
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

## Évalue le LLM configuré (APP_CONFIGLLM_*) sur les fiches RCP synthétiques
eval-rcp:
	@echo -e "$(CYAN)--> Évaluation RCP avec le modèle configuré...$(RESET)"
	cd $(APP_DIR) && PYTHONPATH=. $(UV) run python -m src.application.evaluation.rcp_eval tests/fixtures/rcp

## Analyse la qualité et le style du code avec Ruff
lint:
	@echo -e "$(CYAN)--> Vérification Ruff sur src/...$(RESET)"
	cd $(APP_DIR) && $(UV) run ruff check src/

## Applique le formatage automatique avec Ruff
format:
	@echo -e "$(CYAN)--> Formatage Ruff sur src/...$(RESET)"
	cd $(APP_DIR) && $(UV) run ruff format src/

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
	@echo -e "$(CYAN)--> Démarrage de Milvus Standalone...$(RESET)"
	docker compose -f dist/docker/compose/milvus-standalone-docker-compose.yml up -d
	@echo -e "$(CYAN)--> Démarrage des services communs (MongoDB)...$(RESET)"
	docker compose -f dist/docker/compose/docker-compose.yml up -d
	@$(MAKE) mongo-init

## Démarre les conteneurs en mode proxy (Milvus, MongoDB, embeddings - sans chat local)
docker-up-proxy:
	@echo -e "$(CYAN)--> Démarrage de Milvus Standalone...$(RESET)"
	docker compose -f dist/docker/compose/milvus-standalone-docker-compose.yml up -d
	@echo -e "$(CYAN)--> Démarrage des services en mode proxy (MongoDB + embeddings, sans chat local)...$(RESET)"
	docker compose -f dist/docker/compose/docker-compose.yml --profile llamacpp up -d
	@$(MAKE) mongo-init

## Arrête les services d'infrastructure Docker
docker-down:
	@echo -e "$(YELLOW)--> Arrêt des conteneurs Docker...$(RESET)"
	docker compose -f dist/docker/compose/milvus-standalone-docker-compose.yml down --remove-orphans
	docker compose -f dist/docker/compose/docker-compose.yml down --remove-orphans

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
	@echo -e "$(GREEN)Caches nettoyés avec succès.$(RESET)"
