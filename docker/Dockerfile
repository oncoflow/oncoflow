# Utilisation d'une image Python (version alignée avec votre projet)
FROM python:3.13-slim

# Installation de uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copie des fichiers de définition de projet
COPY pyproject.toml uv.lock ./

# Installation des dépendances (sans les outils de dev)
RUN uv sync --frozen --no-dev --no-install-project

# Copie du code de l'application
COPY application application

# Installation du projet et configuration du PATH pour utiliser le venv créé par uv
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Lancement de l'application
CMD ["python", "application/main.py"]
