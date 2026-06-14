import unittest
from unittest.mock import MagicMock, patch
import httpx

from src.application.config import AppConfig
from src.infrastructure.llm.litellm import LiteLLMConnect


class TestLiteLLMConnection(unittest.TestCase):
    def setUp(self):
        # Configure a mock config
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.llm.url = "http://localhost"
        self.mock_config.llm.port = "4000"
        self.mock_config.llm.uri = "/v1"
        self.mock_config.llm.embeddings = "bge-m3"
        self.mock_config.llm.temp = 0.7
        self.mock_config.llm.api_key = "test-api-key"
        self.mock_config.llm.models = "qwen3:14b"

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("src.infrastructure.llm.litellm.LiteLLMEmbeddings")
    @patch("src.infrastructure.llm.litellm.httpx.get")
    def test_init_success(self, mock_get, mock_embeddings_cls):
        # Mock connection test
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        LiteLLMConnect(self.mock_config)

        # Assert connection test was called
        mock_get.assert_called_once_with(
            "http://localhost:4000/v1/models",
            headers={"Authorization": "Bearer test-api-key"},
            timeout=5.0,
        )
        mock_embeddings_cls.assert_called_once_with(
            api_base="http://localhost:4000/v1",
            api_key="test-api-key",
            model="bge-m3",
        )
        self.mock_logger.info.assert_called_with(
            "Succesfully connected to LiteLLM proxy"
        )

    @patch("src.infrastructure.llm.litellm.LiteLLMEmbeddings")
    @patch("src.infrastructure.llm.litellm.httpx.get")
    def test_get_models(self, mock_get, mock_embeddings_cls):
        # Mock connection check during init, then list models check
        mock_response_init = MagicMock(spec=httpx.Response)
        mock_response_init.status_code = 200

        mock_response_models = MagicMock(spec=httpx.Response)
        mock_response_models.status_code = 200
        mock_response_models.json.return_value = {
            "data": [{"id": "qwen3:14b"}, {"id": "bge-m3"}]
        }
        mock_get.side_effect = [mock_response_init, mock_response_models]

        conn = LiteLLMConnect(self.mock_config)
        models = conn.get_models()

        self.assertEqual(models, ["qwen3:14b", "bge-m3"])

    @patch("src.infrastructure.llm.litellm.ChatLiteLLM")
    @patch("src.infrastructure.llm.litellm.LiteLLMEmbeddings")
    @patch("src.infrastructure.llm.litellm.httpx.get")
    def test_chat_creation(self, mock_get, mock_embeddings_cls, mock_chat_litellm_cls):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        conn = LiteLLMConnect(self.mock_config)

        mock_output = MagicMock()
        chat_instance = conn.chat(model="qwen3:14b", output=mock_output, reasoning=True)

        mock_chat_litellm_cls.assert_called_once_with(
            api_base="http://localhost:4000/v1",
            api_key="test-api-key",
            model="qwen3:14b",
            temperature=0.7,
            model_kwargs={
                "response_format": {"type": "json_object"},
                "reasoning": {"effort": "low"},
            },
            reasoning={"effort": "low"},
            streaming=True,
        )
        self.assertEqual(chat_instance._output_schema, mock_output)
