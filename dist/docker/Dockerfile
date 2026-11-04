# Utilisation d'une image Python basée sur Debian 13 (Trixie)
FROM python:3.14-slim-trixie

# Installation de uv et des outils de compilation / librairies graphiques et système
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    libxcb1 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/* \
    && uv pip uninstall --system pip

# Création d'un utilisateur non-root pour l'exécution et du répertoire /app
RUN groupadd -g 1002 appuser && \
    useradd -u 1002 -g appuser -m -d /home/appuser -s /bin/bash appuser && \
    mkdir -p /app && chown -R appuser:appuser /app /home/appuser

ENV UV_PYTHON_DOWNLOADS=never
ENV UV_NO_MANAGED_PYTHON=1
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV UV_CACHE_DIR=/tmp/.uv-cache
ENV HOME=/home/appuser

WORKDIR /app
USER appuser

# Copie des fichiers de définition de projet
COPY --chown=appuser:appuser application/pyproject.toml application/uv.lock ./

# Installation des dépendances (socle + groupe ui, sans les outils de dev) avec purge du cache
RUN uv sync --frozen --no-dev --group ui --no-install-project && rm -rf /tmp/.uv-cache

# Copie du code de l'application
COPY --chown=appuser:appuser application application

# Installation du projet et configuration du PATH pour utiliser le venv créé par uv
RUN uv sync --frozen --no-dev --group ui && rm -rf /tmp/.uv-cache
ENV PATH="/app/.venv/bin:$PATH"
ENV UV_PYTHON=/app/.venv/bin/python

WORKDIR /app/application

EXPOSE 8501

# Lancement de l'application Streamlit
CMD ["uv", "run", "--no-sync", "--no-build", "streamlit", "run", "app-ui.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
