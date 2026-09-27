import unittest
from unittest.mock import MagicMock, patch

from src.infrastructure.llm.bifrost import BifrostConnect
from src.infrastructure.llm.factory import get_llm_client


class TestBifrostConnection(unittest.TestCase):
    def setUp(self):
        # Configure a mock config matching a homelab Bifrost deployment
        self.mock_config = MagicMock()
        self.mock_config.llm.type = "Bifrost"
        self.mock_config.llm.url = "http://bifrost.homelab.lan"
        self.mock_config.llm.port = "8080"
        self.mock_config.llm.uri = "/v1"
        self.mock_config.llm.embeddings = "ollama/bge-m3"
        self.mock_config.llm.temp = 0.2
        self.mock_config.llm.api_key = "test-api-key"
        self.mock_config.llm.virtual_key = "sk-bf-test"
        self.mock_config.llm.models = "ollama/qwen3:14b"

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_init_success(self, mock_openai_client_cls, mock_embeddings_cls):
        conn = BifrostConnect(self.mock_config)

        self.assertEqual(conn.base_url, "http://bifrost.homelab.lan:8080/v1")
        mock_openai_client_cls.assert_called_once_with(
            base_url="http://bifrost.homelab.lan:8080/v1",
            api_key="test-api-key",
            default_headers={"x-bf-vk": "sk-bf-test"},
        )
        mock_openai_client_cls.return_value.models.list.assert_called_once()
        mock_embeddings_cls.assert_called_once_with(
            base_url="http://bifrost.homelab.lan:8080/v1",
            api_key="test-api-key",
            model="ollama/bge-m3",
            default_headers={"x-bf-vk": "sk-bf-test"},
        )
        self.mock_logger.info.assert_called_with(
            "Succesfully connected to Bifrost gateway"
        )

    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_default_uri_and_no_virtual_key(
        self, mock_openai_client_cls, mock_embeddings_cls
    ):
        # Port already in URL, empty URI and no virtual key
        self.mock_config.llm.url = "http://bifrost:8080/"
        self.mock_config.llm.uri = "/"
        self.mock_config.llm.virtual_key = ""

        conn = BifrostConnect(self.mock_config)

        self.assertEqual(conn.base_url, "http://bifrost:8080/v1")
        self.assertIsNone(conn.default_headers)

    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_connection_failure_exits(
        self, mock_openai_client_cls, mock_embeddings_cls
    ):
        mock_openai_client_cls.return_value.models.list.side_effect = ConnectionError(
            "unreachable"
        )

        with self.assertRaises(SystemExit) as cm:
            BifrostConnect(self.mock_config)
        self.assertEqual(cm.exception.code, 254)

    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_get_models(self, mock_openai_client_cls, mock_embeddings_cls):
        mock_model1 = MagicMock()
        mock_model1.id = "ollama/qwen3:14b"
        mock_model2 = MagicMock()
        mock_model2.id = "ollama/bge-m3"
        mock_openai_client_cls.return_value.models.list.return_value = MagicMock(
            data=[mock_model1, mock_model2]
        )

        conn = BifrostConnect(self.mock_config)

        self.assertEqual(conn.get_models(), ["ollama/qwen3:14b", "ollama/bge-m3"])

    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_get_models_fallback_to_config(
        self, mock_openai_client_cls, mock_embeddings_cls
    ):
        conn = BifrostConnect(self.mock_config)
        mock_openai_client_cls.return_value.models.list.side_effect = RuntimeError(
            "boom"
        )

        self.assertEqual(conn.get_models(), ["ollama/qwen3:14b"])

    @patch("src.infrastructure.llm.bifrost.StrictChatOpenAI")
    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_chat_creation(
        self, mock_openai_client_cls, mock_embeddings_cls, mock_chat_cls
    ):
        conn = BifrostConnect(self.mock_config)

        mock_output = MagicMock()
        chat_instance = conn.chat(model="ollama/qwen3:14b", output=mock_output)

        mock_chat_cls.assert_called_once_with(
            base_url="http://bifrost.homelab.lan:8080/v1",
            api_key="test-api-key",
            default_headers={"x-bf-vk": "sk-bf-test"},
            model="ollama/qwen3:14b",
            use_responses_api=False,
            reasoning_effort="low",
            temperature=0.2,
            model_kwargs={"response_format": {"type": "json_object"}},
            streaming=True,
        )
        self.assertEqual(chat_instance.__dict__["_output_schema"], mock_output)

    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_chat_uses_chat_completions_api(
        self, mock_openai_client_cls, mock_embeddings_cls
    ):
        # Real LangChain model: must not switch to the Responses API
        conn = BifrostConnect(self.mock_config)
        chat_instance = conn.chat(model="ollama/qwen3:14b", reasoning=False)

        self.assertFalse(chat_instance._use_responses_api({}))
        self.assertIsNone(chat_instance.reasoning_effort)
        self.assertEqual(chat_instance.default_headers, {"x-bf-vk": "sk-bf-test"})

    @patch("src.infrastructure.llm.bifrost.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.bifrost.openai.OpenAI")
    def test_factory_returns_bifrost(self, mock_openai_client_cls, mock_embeddings_cls):
        self.assertIsInstance(get_llm_client(self.mock_config), BifrostConnect)


if __name__ == "__main__":
    unittest.main()
