# 🌉 Oncoflow derrière une passerelle LLM Bifrost (homelab)

Oncoflow peut envoyer tous ses appels LLM (chat + embeddings) à une passerelle [Bifrost](https://github.com/maximhq/bifrost) déjà présente dans le homelab. Bifrost expose une API compatible OpenAI (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`) et route vers les fournisseurs configurés.

> [!CAUTION]
> **Données patients** : le routage Bifrost utilisé par Oncoflow ne doit pointer **que vers des fournisseurs locaux** (Ollama, vLLM, llama.cpp…). N'associez jamais un fournisseur cloud public à la clé virtuelle d'Oncoflow.

## 1. Côté Bifrost

- Déclarer le fournisseur local (par exemple Ollama sur `http://ollama:11434`) dans Bifrost.
- Les modèles s'adressent en `<fournisseur>/<modèle>` : `ollama/qwen3:14b` pour le raisonnement, `ollama/bge-m3` pour les embeddings.
- Optionnel : créer une clé virtuelle (gouvernance) dédiée à Oncoflow, limitée aux fournisseurs locaux. Oncoflow l'envoie dans l'en-tête `x-bf-vk`.
- Vérifier : `curl http://bifrost:8080/v1/models`.

## 2. Côté Oncoflow

| Variable | Exemple | Rôle |
| :-- | :-- | :-- |
| `APP_CONFIGLLM_TYPE` | `Bifrost` | Sélectionne le client `BifrostConnect` |
| `APP_CONFIGLLM_URL` | `http://bifrost` | Hôte de la passerelle (nom du conteneur sur le réseau homelab) |
| `APP_CONFIGLLM_PORT` | `8080` | Port de Bifrost |
| `APP_CONFIGLLM_URI` | `/v1` | Préfixe de l'API OpenAI (`/v1` par défaut si vide) |
| `APP_CONFIGLLM_MODELS` | `ollama/qwen3:14b` | Modèle de raisonnement |
| `APP_CONFIGLLM_EMBEDDINGS` | `ollama/bge-m3` | Modèle d'embeddings |
| `APP_CONFIGLLM_VIRTUAL_KEY` | `sk-bf-…` | Clé virtuelle Bifrost (optionnelle, en-tête `x-bf-vk`) |
| `APP_CONFIGLLM_API_KEY` | `bifrost` | Seulement si l'authentification Bifrost est activée |

Le client reste sur `/v1/chat/completions` (pas d'API *Responses*, que tous les fournisseurs routés ne supportent pas) et envoie `reasoning_effort=low` quand le raisonnement est activé.

## 3. Déploiement Docker

`dist/docker/compose/bifrost/` contient une stack prête à l'emploi : Oncoflow (Streamlit), MongoDB et ChromaDB. Bifrost n'y est **pas** démarré : Oncoflow rejoint le réseau Docker externe du homelab (`homelab` par défaut, surchargeable avec `HOMELAB_NETWORK`).

```bash
cd dist/docker/compose/bifrost
cp oncoflow-bifrost.env.example oncoflow-bifrost.env   # à adapter, jamais commité
docker network create homelab                          # s'il n'existe pas déjà
HOMELAB_NETWORK=homelab docker compose up -d --build
# UI : http://<hôte>:8501 (ONCOFLOW_PORT pour changer le port)
```

Les données (fiches PDF déposées, MongoDB, ChromaDB) sont conservées dans `./data` (`ONCOFLOW_DATA_DIR`).

## 4. Évaluer un modèle sur les fiches RCP synthétiques

Des fiches RCP fictives avec leurs documents annexes (`application/tests/fixtures/rcp/`) servent à mesurer la qualité des réponses aux quatre questions de relecture (`application/src/domain/oncology/rcp_review.py`) :

1. faut-il discuter le dossier pour une résection chirurgicale ?
2. manque-t-il des données pour discuter la résection ?
3. la fiche RCP présente-t-elle des incohérences ?
4. les documents annexes sont-ils discordants avec la fiche RCP ?

```bash
cd application
# Tests unitaires (sans LLM, exécutés en CI)
PYTHONPATH=. uv run pytest tests/test_rcp_review.py tests/test_bifrost.py

# Évaluation réelle à travers Bifrost (tableau PASS/FAIL par cas et par question)
export APP_CONFIGLLM_TYPE=Bifrost APP_CONFIGLLM_URL=http://bifrost APP_CONFIGLLM_PORT=8080 \
       APP_CONFIGLLM_URI=/v1 APP_CONFIGLLM_MODELS=ollama/qwen3:14b APP_CONFIGLLM_EMBEDDINGS=ollama/bge-m3
PYTHONPATH=. uv run python -m src.application.evaluation.rcp_eval tests/fixtures/rcp
# ou depuis la racine du dépôt : make eval-rcp
# ou via pytest
ONCOFLOW_LLM_EVAL=1 PYTHONPATH=. uv run pytest tests/test_rcp_eval_llm.py -v
```

Changer `APP_CONFIGLLM_MODELS` permet de comparer plusieurs modèles routés par Bifrost sur le même jeu de cas.
