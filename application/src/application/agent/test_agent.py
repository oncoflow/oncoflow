import json
import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from src.application.agent.agent import OncowflowAgent
from src.application.config import AppConfig
from src.application.reader import DocumentReader

# Mock classes to simulate LangChain message types
class AIMessage:
    def __init__(self, content):
        self.content = content

class HumanMessage:
    def __init__(self, content):
        self.content = content

class ToolMessage:
    def __init__(self, content):
        self.content = content

# Mock Output Schema
class MockOutputSchema(BaseModel):
    response: str

class TestOncowflowAgent(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.llm.type = "ollama"
        self.mock_config.llm.models = "llama3,mistral"
        self.mock_config.set_logger.return_value = MagicMock()
        
        self.mock_reader = MagicMock(spec=DocumentReader)
        self.output_format = MockOutputSchema

    @patch("src.application.agent.agent.OllamaConnect")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.DocumentReader")
    def test_init_success(self, mock_doc_reader_cls, mock_create_agent, mock_ollama_cls):
        # Setup mocks
        mock_ollama_instance = mock_ollama_cls.return_value
        mock_ollama_instance.chat.return_value = "mock_llm_model"
        
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format
        )
        
        # Assertions
        mock_ollama_cls.assert_called_once_with(self.mock_config)
        mock_create_agent.assert_called_once()
        self.assertEqual(agent.reader, self.mock_reader)
        self.assertIsNotNone(agent.agent)
        self.assertEqual(agent.output_format, self.output_format)

    def test_init_unsupported_llm(self):
        self.mock_config.llm.type = "gpt-4"
        
        with self.assertRaises(ValueError) as cm:
            OncowflowAgent(
                config=self.mock_config,
                mtd=self.mock_reader,
                output_format=self.output_format
            )
        self.assertIn("gpt-4 not yet supported", str(cm.exception))

    @patch("src.application.agent.agent.OllamaConnect")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_success(self, mock_context_cls, mock_create_agent, mock_ollama_cls):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor
        
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format
        )
        
        # Prepare successful response
        expected_dict = {"response": "Successful answer"}
        valid_msg = AIMessage(content=json.dumps(expected_dict))
        
        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("question"), valid_msg]
        }
        
        # Execute
        result = agent.ask("My question")
        
        # Assert
        self.assertEqual(result, expected_dict)
        mock_agent_executor.invoke.assert_called_once()

    @patch("src.application.agent.agent.OllamaConnect")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_skips_invalid_messages(self, mock_context_cls, mock_create_agent, mock_ollama_cls):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor
        
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format
        )
        
        # Prepare response: 1. ToolMessage (ignored), 2. AIMessage (invalid json/schema), 3. AIMessage (valid)
        expected_dict = {"response": "Valid answer"}
        
        msg1 = ToolMessage("some tool output")
        msg2 = AIMessage(content='{"wrong_field": "value"}') # Validation error
        msg3 = AIMessage(content=json.dumps(expected_dict)) # Success
        
        mock_agent_executor.invoke.return_value = {
            "messages": [msg1, msg2, msg3]
        }
        
        # Execute
        result = agent.ask("My question")
        
        # Assert
        self.assertEqual(result, expected_dict)

    @patch("src.application.agent.agent.OllamaConnect")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_failure_no_valid_response(self, mock_context_cls, mock_create_agent, mock_ollama_cls):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor
        
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format
        )
        
        # Prepare response with no valid AIMessage
        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("question"), ToolMessage("tool output")]
        }
        
        # Execute
        with self.assertRaises(ValueError) as cm:
            agent.ask("My question")
        
        self.assertIn("AI response", str(cm.exception))
