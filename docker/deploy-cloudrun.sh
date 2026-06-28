#!/bin/bash
set -e

# Ensure executing from the script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "${SCRIPT_DIR}"

# Configuration variables
REGION="europe-west1"
SERVICE_NAME="llama-cpp-chat"
BUCKET_NAME="oncoflow-models-cache"
REPO_NAME="oncoflow-images"

echo "============================================="
echo "Deploying ${SERVICE_NAME} to GCP Cloud Run..."
echo "============================================="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI is not installed. Please install it first."
    exit 1
fi

# Get current project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT_ID" ]; then
    echo "Error: No active GCP project configured. Run 'gcloud config set project <PROJECT_ID>'."
    exit 1
fi
echo "Using GCP Project: ${PROJECT_ID}"

# Resolve container tool (podman or docker)
if command -v podman &> /dev/null; then
    CONTAINER_TOOL="podman"
elif command -v docker &> /dev/null; then
    CONTAINER_TOOL="docker"
else
    echo "Error: Neither podman nor docker was found."
    exit 1
fi
echo "Using container tool: ${CONTAINER_TOOL}"

echo ""
echo "Prerequisites Check:"
echo "1. Ensure GCS bucket '${BUCKET_NAME}' exists."
echo "   Command: gcloud storage buckets create gs://${BUCKET_NAME} --location=${REGION}"
echo ""
echo "2. Ensure the Cloud Run service account has permissions on the bucket."
echo ""

read -p "Do you want to proceed with deployment in region '${REGION}'? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# 1. Create Artifact Registry if it doesn't exist
echo "Checking Artifact Registry repository '${REPO_NAME}'..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" &>/dev/null; then
    echo "Creating Artifact Registry repository '${REPO_NAME}'..."
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="Docker images for Oncoflow"
fi

# 2. Configure credentials
echo "Configuring container registry credentials..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# 3. Pull, tag, and push image
TARGET_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/llama-cpp:server-cuda12"
echo "Pulling llama.cpp server image from GHCR..."
${CONTAINER_TOOL} pull ghcr.io/ggml-org/llama.cpp:server-cuda12
echo "Tagging image for Google Artifact Registry..."
${CONTAINER_TOOL} tag ghcr.io/ggml-org/llama.cpp:server-cuda12 "${TARGET_IMAGE}"
echo "Pushing image to Google Artifact Registry (this may take a minute)..."
${CONTAINER_TOOL} push "${TARGET_IMAGE}"

# 4. Generate resolved service YAML pointing to GCS bucket and GAR image
RESOLVED_YAML="resolved-cloud-run-service.yaml"
echo "Generating resolved service configuration..."
sed "s|image:.*|image: ${TARGET_IMAGE}|g" cloud-run-service.yaml > "${RESOLVED_YAML}"
# Replace bucket name if different (optional but robust)
sed -i "s|bucketName:.*|bucketName: ${BUCKET_NAME}|g" "${RESOLVED_YAML}"

# 5. Deploy Cloud Run service
echo "Deploying Cloud Run service..."
gcloud beta run services replace "${RESOLVED_YAML}" --region="${REGION}"

# Clean up temporary file
rm -f "${RESOLVED_YAML}"

echo ""
echo "Deployment triggered successfully!"
echo "You can check status using: gcloud run services describe ${SERVICE_NAME} --region=${REGION}"
