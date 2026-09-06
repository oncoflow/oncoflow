# ==============================================================================
# Oncoflow Makefile
# Outil de gestion des services, du développement et de l'infrastructure locale
# ==============================================================================

SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(PATH)

# Détection de l'exécutable uv
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

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

.PHONY: help install upgrade start-api start-ui cloudrun-proxy stop test lint format docker-up docker-down docker-status pull-models clean status api ui proxy dev

## Affiche l'aide et la liste des commandes disponibles
help:
	@echo -e "$(CYAN)Usage: make <commande>$(RESET)"
	@echo ""
	@echo -e "$(GREEN)Commandes principales :$(RESET)"
	@echo -e "  $(YELLOW)make install$(RESET)          Installe les dépendances via uv sync"
	@echo -e "  $(YELLOW)make upgrade$(RESET)          Met à jour toutes les dépendances (uv lock --upgrade && uv sync)"
	@echo -e "  $(YELLOW)make start-api$(RESET)        Démarre l'API FastAPI (port $(PORT_API))"
	@echo -e "  $(YELLOW)make start-ui$(RESET)         Démarre le dashboard Streamlit (port $(PORT_UI))"
	@echo -e "  $(YELLOW)make cloudrun-proxy$(RESET)   Lance le proxy Cloud Run pour $(CLOUDRUN_SERVICE) (port $(CLOUDRUN_PORT))"
	@echo -e "  $(YELLOW)make stop$(RESET)             Arrête l'UI, l'API et le proxy Cloud Run"
	@echo ""
	@echo -e "$(GREEN)Commandes de qualité & tests :$(RESET)"
	@echo -e "  $(YELLOW)make test$(RESET)             Exécute la suite de tests Pytest"
	@echo -e "  $(YELLOW)make lint$(RESET)             Vérifie le code avec Ruff"
	@echo -e "  $(YELLOW)make format$(RESET)           Formate le code avec Ruff"
	@echo ""
	@echo -e "$(GREEN)Commandes d'infrastructure & Ollama :$(RESET)"
	@echo -e "  $(YELLOW)make docker-up$(RESET)        Démarre Milvus et MongoDB via Docker Compose"
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

## Lance le proxy Cloud Run vers le service LLM distant
cloudrun-proxy:
	@echo -e "$(CYAN)--> Démarrage du proxy Cloud Run vers $(CLOUDRUN_SERVICE) sur le port $(CLOUDRUN_PORT)...$(RESET)"
	gcloud run services proxy $(CLOUDRUN_SERVICE) --port=$(CLOUDRUN_PORT)

# Raccourcis et alias
api: start-api
ui: start-ui
proxy: cloudrun-proxy

## Démarre l'API en arrière-plan puis Streamlit au premier plan
dev:
	@echo -e "$(CYAN)--> Démarrage du mode développement complet (API + UI)...$(RESET)"
	@$(MAKE) stop >/dev/null 2>&1
	@echo -e "  Démarrage de l'API en tâche de fond..."
	@nohup bash -c "cd $(APP_DIR) && $(UV) run python app-api.py" > /tmp/oncoflow-api.log 2>&1 &
	@sleep 2
	@$(MAKE) start-ui

## Arrête les processus actifs (Streamlit, API FastAPI, proxy Cloud Run)
stop:
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
	@if pgrep -f "[g]cloud.*run.*services.*proxy" >/dev/null 2>&1; then \
		pkill -f "[g]cloud.*run.*services.*proxy" 2>/dev/null && echo -e "  [$(RED)ARRÊTÉ$(RESET)] Cloud Run Proxy"; \
	else \
		echo -e "  [$(GREEN)OK$(RESET)] Cloud Run Proxy n'est pas actif"; \
	fi
	@echo -e "$(GREEN)Terminé.$(RESET)"

## Lance la suite de tests Pytest
test:
	@echo -e "$(CYAN)--> Exécution des tests Pytest...$(RESET)"
	cd $(APP_DIR) && $(UV) run pytest

## Analyse la qualité et le style du code avec Ruff
lint:
	@echo -e "$(CYAN)--> Vérification Ruff sur src/...$(RESET)"
	cd $(APP_DIR) && $(UV) run ruff check src/

## Applique le formatage automatique avec Ruff
format:
	@echo -e "$(CYAN)--> Formatage Ruff sur src/...$(RESET)"
	cd $(APP_DIR) && $(UV) run ruff format src/

## Démarre les services d'infrastructure Docker (Milvus & MongoDB)
docker-up:
	@echo -e "$(CYAN)--> Démarrage de Milvus Standalone...$(RESET)"
	docker compose -f dist/docker/compose/milvus-standalone-docker-compose.yml up -d
	@echo -e "$(CYAN)--> Démarrage des services communs (MongoDB)...$(RESET)"
	docker compose -f dist/docker/compose/docker-compose.yml up -d

## Arrête les services d'infrastructure Docker
docker-down:
	@echo -e "$(YELLOW)--> Arrêt des conteneurs Docker...$(RESET)"
	docker compose -f dist/docker/compose/milvus-standalone-docker-compose.yml down
	docker compose -f dist/docker/compose/docker-compose.yml down

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
