import os

# Set fallback implementation for older protobuf structures used by chromadb dependencies
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
