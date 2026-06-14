import unittest
from unittest.mock import MagicMock, patch
import httpx

from src.application.config import AppConfig
from src.infrastructure.llm.llamacpp import LlamaCppConnect


class TestLlamaCppConnection(unittest.TestCase):
    def setUp(self):
        # Configure a mock config matching llama.cpp direct connection
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.llm.url = "http://localhost"
        self.mock_config.llm.port = "8081"
        self.mock_config.llm.embeddings_port = "8082"
        self.mock_config.llm.uri = "/v1"
        self.mock_config.llm.embeddings = "bge-m3"
        self.mock_config.llm.temp = 0.7
        self.mock_config.llm.api_key = "not-needed"
        self.mock_config.llm.models = "Qwen3-14B-GGUF"

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_init_success(self, mock_get, mock_embeddings_cls):
        # Mock connection test (/health returns 200)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        conn = LlamaCppConnect(self.mock_config)

        # Assert /health endpoint was called for connection test
        mock_get.assert_any_call(
            "http://localhost:8081/health",
            timeout=5.0,
        )
        # Assert embeddings initialized with embeddings_port from config
        mock_embeddings_cls.assert_called_once_with(
            base_url="http://localhost:8082/v1",
            api_key="not-needed",
            model="bge-m3",
        )
        self.mock_logger.info.assert_called_with(
            "Successfully connected to llama.cpp server"
        )
        self.assertEqual(conn.base_url, "http://localhost:8081/v1")

    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_get_models(self, mock_get, mock_embeddings_cls):
        # First call: /health for init, second call: /models for get_models
        mock_health_response = MagicMock(spec=httpx.Response)
        mock_health_response.status_code = 200

        mock_models_response = MagicMock(spec=httpx.Response)
        mock_models_response.status_code = 200
        mock_models_response.json.return_value = {"data": [{"id": "Qwen3-14B-GGUF"}]}
        mock_get.side_effect = [mock_health_response, mock_models_response]

        conn = LlamaCppConnect(self.mock_config)
        models = conn.get_models()

        self.assertEqual(models, ["Qwen3-14B-GGUF"])

    @patch("src.infrastructure.llm.llamacpp.ChatOpenAI")
    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_chat_creation_with_output(
        self, mock_get, mock_embeddings_cls, mock_chat_openai_cls
    ):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        conn = LlamaCppConnect(self.mock_config)

        mock_output = MagicMock()
        conn.chat(model="Qwen3-14B-GGUF", output=mock_output)

        mock_chat_openai_cls.assert_called_once_with(
            base_url="http://localhost:8081/v1",
            api_key="not-needed",
            model="Qwen3-14B-GGUF",
            tools=[],
            temperature=0.7,
            max_tokens=4096,
            model_kwargs={
                "response_format": {"type": "json_object"},
            },
            streaming=True,
        )

    @patch("src.infrastructure.llm.llamacpp.ChatOpenAI")
    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_chat_creation_with_tools_no_json_mode(
        self, mock_get, mock_embeddings_cls, mock_chat_openai_cls
    ):
        """When tools are provided, JSON mode must NOT be forced."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        conn = LlamaCppConnect(self.mock_config)

        mock_tool = MagicMock()
        mock_output = MagicMock()
        conn.chat(model="Qwen3-14B-GGUF", output=mock_output, tools=[mock_tool])

        mock_chat_openai_cls.assert_called_once_with(
            base_url="http://localhost:8081/v1",
            api_key="not-needed",
            model="Qwen3-14B-GGUF",
            tools=[mock_tool],
            temperature=0.7,
            max_tokens=4096,
            model_kwargs={},
            streaming=True,
        )

    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_connection_failure_exits(self, mock_get, mock_embeddings_cls):
        """Connection failure should call exit(254)."""
        mock_get.side_effect = Exception("Connection refused")

        with self.assertRaises(SystemExit) as cm:
            LlamaCppConnect(self.mock_config)

        self.assertEqual(cm.exception.code, 254)

    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_get_models_fallback_on_error(self, mock_get, mock_embeddings_cls):
        """If /models fails, should return config fallback."""
        mock_health_response = MagicMock(spec=httpx.Response)
        mock_health_response.status_code = 200

        mock_get.side_effect = [
            mock_health_response,
            Exception("Network error"),
        ]

        conn = LlamaCppConnect(self.mock_config)
        models = conn.get_models()

        self.assertEqual(models, ["Qwen3-14B-GGUF"])

    @patch("src.infrastructure.llm.llamacpp.ChatOpenAI")
    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_chat_without_output_no_json_mode(
        self, mock_get, mock_embeddings_cls, mock_chat_openai_cls
    ):
        """When output is None, JSON mode should NOT be set."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        conn = LlamaCppConnect(self.mock_config)
        conn.chat(model="Qwen3-14B-GGUF")

        mock_chat_openai_cls.assert_called_once_with(
            base_url="http://localhost:8081/v1",
            api_key="not-needed",
            model="Qwen3-14B-GGUF",
            tools=[],
            temperature=0.7,
            max_tokens=4096,
            model_kwargs={},
            streaming=True,
        )

    @patch("src.infrastructure.llm.llamacpp.LlamaCppCompatibleEmbeddings")
    @patch("src.infrastructure.llm.llamacpp.httpx.get")
    def test_health_fallback_to_models(self, mock_get, mock_embeddings_cls):
        """If /health returns non-200, should fall back to /models endpoint."""
        mock_health_fail = MagicMock(spec=httpx.Response)
        mock_health_fail.status_code = 404

        mock_models_ok = MagicMock(spec=httpx.Response)
        mock_models_ok.status_code = 200

        mock_get.side_effect = [mock_health_fail, mock_models_ok]

        # Should not raise/exit because /models succeeds
        conn = LlamaCppConnect(self.mock_config)
        self.assertIsNotNone(conn)


if __name__ == "__main__":
    unittest.main()
