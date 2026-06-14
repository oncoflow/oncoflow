import unittest
from unittest.mock import MagicMock, patch

from src.application.config import AppConfig
from src.infrastructure.llm.vllm import VllmConnect


class TestVllmConnection(unittest.TestCase):
    def setUp(self):
        # Configure a mock config
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.llm.url = "http://127.0.0.1"
        self.mock_config.llm.port = "8080"
        self.mock_config.llm.uri = "/v1"
        self.mock_config.llm.embeddings = "bge-m3"
        self.mock_config.llm.temp = 0.1
        self.mock_config.llm.api_key = "test-api-key"

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("src.infrastructure.llm.vllm.OllamaEmbeddings")
    @patch("src.infrastructure.llm.vllm.openai.OpenAI")
    def test_init_success_with_ollama_fallback(
        self, mock_vllm_client_cls, mock_ollama_embeddings_cls
    ):
        mock_client = mock_vllm_client_cls.return_value

        # Setup mock for models.list()
        mock_model = MagicMock()
        mock_model.id = "gemma4-local"
        mock_data = MagicMock()
        mock_data.data = [mock_model]
        mock_client.models.list.return_value = mock_data

        VllmConnect(self.mock_config)

        # Assert client initialization
        mock_vllm_client_cls.assert_called_once_with(
            base_url="http://127.0.0.1:8080/v1", api_key="test-api-key"
        )

        # Verify it fallback-routes the embedding model "bge-m3" to Ollama port 11434
        # because "bge-m3" is not in the hosted models list ["gemma4-local"] of vLLM
        mock_ollama_embeddings_cls.assert_called_once_with(
            base_url="http://127.0.0.1:11434",
            model="bge-m3",
        )
        self.mock_logger.info.assert_any_call("Successfully connected to vLLM server")

    @patch("src.infrastructure.llm.vllm.ChatOpenAI")
    @patch("src.infrastructure.llm.vllm.OllamaEmbeddings")
    @patch("src.infrastructure.llm.vllm.openai.OpenAI")
    def test_chat_creation(
        self, mock_vllm_client_cls, mock_ollama_embeddings_cls, mock_chat_vllm_cls
    ):
        mock_client = mock_vllm_client_cls.return_value
        mock_client.models.list.return_value = MagicMock()

        conn = VllmConnect(self.mock_config)

        mock_output = MagicMock()
        mock_output.model_json_schema.return_value = {"type": "object"}

        conn.chat(model="gemma4-local", output=mock_output)

        mock_chat_vllm_cls.assert_called_once_with(
            base_url="http://127.0.0.1:8080/v1",
            api_key="test-api-key",
            model="gemma4-local",
            tools=[],
            reasoning={"effort": "medium"},
            temperature=0.1,
            model_kwargs={"response_format": {"type": "json_object"}},
            streaming=True,
        )
