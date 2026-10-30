#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "google-cloud-storage>=3.12.0",
#     "requests>=2.34.2",
# ]
# ///
import sys

import requests
from google.cloud import storage

MODELS = {
    "qwen3-6-moe": (
        "models/Qwen3.6-35B-A3B-UD-IQ4_NL.gguf",
        "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/resolve/main/Qwen3.6-35B-A3B-UD-IQ4_NL.gguf",
    ),
    "ornith-moe": (
        "models/Ornith-1.5-35B-A3B-IQ4_XS.gguf",
        "https://huggingface.co/bartowski/Ornith-1.5-35B-A3B-GGUF/resolve/main/Ornith-1.5-35B-A3B-IQ4_XS.gguf",
    ),
}


def main():
    bucket_name = "oncoflow-models-cache"
    model_key = sys.argv[1] if len(sys.argv) > 1 else "ornith-moe"
    if model_key not in MODELS:
        print(f"Unknown model '{model_key}'. Available: {', '.join(MODELS.keys())}")
        sys.exit(1)
    blob_name, url = MODELS[model_key]

    print(f"Connecting to GCS bucket: {bucket_name}...")
    storage_client = storage.Client(project="oncowflow-ollama")
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    print(f"Requesting HF URL: {url}...")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    total_size = int(response.headers.get("content-length", 0))
    print(f"Total size to download: {total_size / 1e9:.2f} GB")

    # Set chunk size for GCS upload (default is 100MB to optimize upload)
    blob.chunk_size = 100 * 1024 * 1024

    print("Starting upload stream directly to GCS...")
    downloaded = 0

    with blob.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                percent = (downloaded / total_size) * 100
                sys.stdout.write(
                    f"\rProgress: {downloaded / 1e9:.2f} / {total_size / 1e9:.2f} GB ({percent:.2f}%)"
                )
                sys.stdout.flush()

    print("\nUpload complete!")


if __name__ == "__main__":
    main()
