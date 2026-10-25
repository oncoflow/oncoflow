import os

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["DOCLING_DEVICE"] = "cpu"

from src.application.queue_worker import run_worker_main  # noqa: E402

if __name__ == "__main__":
    run_worker_main()
