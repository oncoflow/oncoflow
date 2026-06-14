import unittest
from unittest.mock import MagicMock, patch

from src.application.config import AppConfig
from src.infrastructure.llm.openai import OpenAIConnect


class TestOpenAIConnection(unittest.TestCase):
    def setUp(self):
        # Configure a mock config
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.llm.url = "https://api.openai.com/v1"
        self.mock_config.llm.port = ""
        self.mock_config.llm.uri = ""
        self.mock_config.llm.embeddings = "text-embedding-3-large"
        self.mock_config.llm.temp = 0.7
        self.mock_config.llm.api_key = "test-api-key"

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("src.infrastructure.llm.openai.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.openai.openai.OpenAI")
    def test_init_success(self, mock_openai_client_cls, mock_embeddings_cls):
        mock_client = mock_openai_client_cls.return_value
        mock_client.models.list.return_value = MagicMock()

        OpenAIConnect(self.mock_config)

        # Assert client initialization
        mock_openai_client_cls.assert_called_once_with(
            base_url="https://api.openai.com/v1", api_key="test-api-key"
        )
        mock_embeddings_cls.assert_called_once_with(
            base_url="https://api.openai.com/v1",
            api_key="test-api-key",
            model="text-embedding-3-large",
        )
        self.mock_logger.info.assert_called_with("Succesfully connected")

    @patch("src.infrastructure.llm.openai.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.openai.openai.OpenAI")
    def test_get_models(self, mock_openai_client_cls, mock_embeddings_cls):
        mock_client = mock_openai_client_cls.return_value

        mock_model1 = MagicMock()
        mock_model1.id = "gpt-4o"
        mock_model2 = MagicMock()
        mock_model2.id = "gpt-4-turbo"

        mock_data = MagicMock()
        mock_data.data = [mock_model1, mock_model2]
        mock_client.models.list.return_value = mock_data

        conn = OpenAIConnect(self.mock_config)
        models = conn.get_models()

        self.assertEqual(models, ["gpt-4o", "gpt-4-turbo"])

    @patch("src.infrastructure.llm.openai.StrictChatOpenAI")
    @patch("src.infrastructure.llm.openai.OllamaCompatibleOpenAIEmbeddings")
    @patch("src.infrastructure.llm.openai.openai.OpenAI")
    def test_chat_creation(
        self, mock_openai_client_cls, mock_embeddings_cls, mock_chat_openai_cls
    ):
        conn = OpenAIConnect(self.mock_config)

        mock_output = MagicMock()
        mock_output.model_json_schema.return_value = {"type": "object"}

        conn.chat(model="gpt-4o", output=mock_output)

        mock_chat_openai_cls.assert_called_once_with(
            base_url="https://api.openai.com/v1",
            api_key="test-api-key",
            model="gpt-4o",
            tools=[],
            reasoning={"effort": "medium"},
            temperature=0.7,
            model_kwargs={"response_format": {"type": "json_object"}},
            streaming=True,
        )

    @patch("src.infrastructure.llm.openai.ChatOpenAI.bind_tools")
    def test_strict_chat_openai_bind_tools(self, mock_super_bind_tools):
        from src.infrastructure.llm.openai import StrictChatOpenAI

        model = StrictChatOpenAI(
            api_key="test-api-key",
            model="gpt-4o",
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        mock_output = MagicMock()
        model.__dict__["_output_schema"] = mock_output

        tools = ["mock_tool"]
        model.bind_tools(tools)

        # Verify that response_format was popped from model_kwargs
        self.assertNotIn("response_format", model.model_kwargs)

        # Verify that super().bind_tools was called with response_format
        mock_super_bind_tools.assert_called_once_with(
            tools, strict=True, response_format=mock_output
        )
