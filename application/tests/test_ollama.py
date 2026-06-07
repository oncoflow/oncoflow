import unittest
from unittest.mock import MagicMock, patch

from src.application.config import AppConfig
from src.infrastructure.llm.ollama import OllamaConnect


class TestOllamaConnection(unittest.TestCase):
    def setUp(self):
        # Configure a mock config
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.llm.url = "http://127.0.0.1"
        self.mock_config.llm.port = "11434"
        self.mock_config.llm.embeddings = "all-MiniLM-L6-v2"
        self.mock_config.llm.temp = 0.7

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("src.infrastructure.llm.ollama.OllamaEmbeddings")
    @patch("src.infrastructure.llm.ollama.ollama.Client")
    def test_init_success(self, mock_ollama_client_cls, mock_embeddings_cls):
        mock_client = mock_ollama_client_cls.return_value
        mock_client.list.return_value = {"models": []}

        OllamaConnect(self.mock_config)

        # Assert client host name
        mock_ollama_client_cls.assert_called_once_with(host="http://127.0.0.1:11434")
        mock_embeddings_cls.assert_called_once_with(
            base_url="http://127.0.0.1:11434",
            model="all-MiniLM-L6-v2",
        )
        self.mock_logger.info.assert_called_with("Succesfully connected")

    @patch("src.infrastructure.llm.ollama.OllamaEmbeddings")
    @patch("src.infrastructure.llm.ollama.ollama.Client")
    def test_get_models(self, mock_ollama_client_cls, mock_embeddings_cls):
        mock_client = mock_ollama_client_cls.return_value
        mock_client.list.return_value = {
            "models": [
                {"model": "llama3:latest"},
                {"model": "mistral:latest"},
                {"model": "all-minilm:latest"},  # Should be filtered out
            ]
        }

        conn = OllamaConnect(self.mock_config)
        models = conn.get_models()

        self.assertEqual(models, ["llama3:latest", "mistral:latest"])

    @patch("src.infrastructure.llm.ollama.ChatOllama")
    @patch("src.infrastructure.llm.ollama.OllamaEmbeddings")
    @patch("src.infrastructure.llm.ollama.ollama.Client")
    def test_chat_creation(
        self, mock_ollama_client_cls, mock_embeddings_cls, mock_chat_ollama_cls
    ):
        conn = OllamaConnect(self.mock_config)

        mock_output = MagicMock()
        mock_output.model_json_schema.return_value = {"type": "object"}

        conn.chat(model="llama3", output=mock_output)

        mock_chat_ollama_cls.assert_called_once_with(
            base_url="http://127.0.0.1:11434",
            format={"type": "object"},
            model="llama3",
            tools=[],
            reasoning=False,
            temperature=0.7,
            validate_model_on_init=True,
        )
