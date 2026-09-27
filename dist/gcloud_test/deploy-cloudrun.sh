#!/bin/bash
set -e

# ─── Usage ─────────────────────────────────────────────────────────────────────
usage() {
    echo ""
    echo "Usage: $0 <model>"
    echo ""
    echo "Available models:"
    echo "  qwen3-14b   Qwen3-14B Q4_K_M  — ~20 T/s — Qualité maximale (référence)"
    echo "  qwen3-8b    Qwen3-8B  Q4_K_M  — ~40 T/s — ✅ Recommandé vitesse/qualité"
    echo "  gemma4-12b  Gemma4-12B Q4_K_M — ~26 T/s — ⚠️  Limité par SWA (pas recommandé)"
    echo "  qwen3-6-moe Qwen3.6-35B-A3B IQ4_NL — ~80-120 T/s — 🧪 Expérimental MoE (vérifier repo HF)"
    echo ""
    echo "Examples:"
    echo "  $0 qwen3-8b"
    echo "  $0 gemma4-12b"
    echo "  $0 qwen3-6-moe"
    echo ""
    exit 1
}

# ─── Model selection ───────────────────────────────────────────────────────────
MODEL="${1:-}"
if [ -z "$MODEL" ]; then
    echo "❌ Error: model argument required."
    usage
fi

case "$MODEL" in
    qwen3-14b)
        SERVICE_YAML="cloud-run-service-qwen3-14b.yaml"
        MODEL_LABEL="Qwen3-14B Q4_K_M"
        LITELLM_MODEL="openai/Qwen3-14B-GGUF"
        ;;
    qwen3-8b)
        SERVICE_YAML="cloud-run-service-qwen3-8b.yaml"
        MODEL_LABEL="Qwen3-8B Q4_K_M"
        LITELLM_MODEL="openai/Qwen3-8B-GGUF"
        ;;
    gemma4-12b)
        SERVICE_YAML="cloud-run-service-gemma4-12b.yaml"
        MODEL_LABEL="Gemma4-12B Q4_K_M"
        LITELLM_MODEL="openai/google_gemma-4-12b-it-GGUF"
        ;;
    qwen3-6-moe)
        SERVICE_YAML="cloud-run-service-qwen3-6-moe.yaml"
        MODEL_LABEL="Qwen3.6-35B-A3B UD-IQ4_NL + MTP (MoE)"
        LITELLM_MODEL="openai/Qwen3.6-35B-A3B-MTP-GGUF"
        ;;
    *)
        echo "❌ Error: unknown model '$MODEL'."
        usage
        ;;
esac

# ─── Ensure executing from the script's directory ──────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "${SCRIPT_DIR}"

# Check the YAML file exists
if [ ! -f "$SERVICE_YAML" ]; then
    echo "❌ Error: service file '$SERVICE_YAML' not found in $SCRIPT_DIR"
    exit 1
fi

# ─── Configuration variables ───────────────────────────────────────────────────
REGION="europe-west1"
SERVICE_NAME="llama-cpp-chat"
BUCKET_NAME="oncoflow-models-cache"
REPO_NAME="oncoflow-images"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         Oncoflow — Cloud Run LLM Deployment                  ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║  Model   : %-50s ║\n" "$MODEL_LABEL"
printf "║  YAML    : %-50s ║\n" "$SERVICE_YAML"
printf "║  Region  : %-50s ║\n" "$REGION"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ─── Prerequisites ─────────────────────────────────────────────────────────────
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI is not installed."
    exit 1
fi

PROJECT_ID=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: No active GCP project. Run: gcloud config set project <PROJECT_ID>"
    exit 1
fi
echo "✅ GCP Project: ${PROJECT_ID}"

# Resolve container tool
if command -v podman &> /dev/null; then
    CONTAINER_TOOL="podman"
elif command -v docker &> /dev/null; then
    CONTAINER_TOOL="docker"
else
    echo "❌ Error: Neither podman nor docker found."
    exit 1
fi
echo "✅ Container tool: ${CONTAINER_TOOL}"

echo ""
echo "Prerequisites:"
echo "  1. GCS bucket '${BUCKET_NAME}' must exist:"
echo "     gcloud storage buckets create gs://${BUCKET_NAME} --location=${REGION}"
echo "  2. Cloud Run service account must have read access to the bucket."
echo ""

read -p "Deploy model '$MODEL_LABEL' to region '$REGION'? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# ─── Step 1: Artifact Registry ─────────────────────────────────────────────────
echo ""
echo "🔧 [1/4] Checking Artifact Registry '${REPO_NAME}'..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" &>/dev/null; then
    echo "  Creating repository '${REPO_NAME}'..."
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="Docker images for Oncoflow"
fi
echo "  ✅ Repository ready."

# ─── Step 2: Credentials ───────────────────────────────────────────────────────
echo ""
echo "🔧 [2/4] Configuring container registry credentials..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
echo "  ✅ Credentials configured."

# ─── Step 3: Push image ────────────────────────────────────────────────────────
TARGET_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/llama-cpp:server-cuda12"
echo ""
echo "🔧 [3/4] Syncing llama.cpp server image..."
${CONTAINER_TOOL} pull ghcr.io/ggml-org/llama.cpp:server-cuda12
${CONTAINER_TOOL} tag ghcr.io/ggml-org/llama.cpp:server-cuda12 "${TARGET_IMAGE}"
${CONTAINER_TOOL} push "${TARGET_IMAGE}"
echo "  ✅ Image pushed: ${TARGET_IMAGE}"

# ─── Step 4: Deploy ────────────────────────────────────────────────────────────
RESOLVED_YAML="resolved-cloud-run-service.yaml"
echo ""
echo "🔧 [4/4] Deploying Cloud Run service with model: ${MODEL_LABEL}..."
sed "s|image:.*|image: ${TARGET_IMAGE}|g" "${SERVICE_YAML}" > "${RESOLVED_YAML}"
sed -i "s|bucketName:.*|bucketName: ${BUCKET_NAME}|g" "${RESOLVED_YAML}"

gcloud beta run services replace "${RESOLVED_YAML}" --region="${REGION}"
rm -f "${RESOLVED_YAML}"

# ─── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ Deployment complete!                                      ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║  Model  : %-51s ║\n" "$MODEL_LABEL"
printf "║  LiteLLM: %-51s ║\n" "$LITELLM_MODEL"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Next steps:                                                  ║"
echo "║  1. Update litellm-config.yaml with the model name above      ║"
echo "║  2. Update APP_CONFIGLLM_MODELS env var in your .env          ║"
echo "║  3. Check service status:                                     ║"
printf "║     gcloud run services describe %-27s ║\n" "${SERVICE_NAME}"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  LiteLLM model identifier to use: ${LITELLM_MODEL}"
