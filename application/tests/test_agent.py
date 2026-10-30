import json
import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from src.application.agent.agent import OncowflowAgent
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
        self.mock_config = MagicMock()
        self.mock_config.llm.type = "ollama"
        self.mock_config.llm.models = "llama3,mistral"
        self.mock_config.set_logger.return_value = MagicMock()

        self.mock_reader = MagicMock(spec=DocumentReader)
        self.output_format = MockOutputSchema

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.DocumentReader")
    def test_init_success(
        self, mock_doc_reader_cls, mock_create_agent, mock_get_llm_client
    ):
        # Setup mocks
        mock_ollama_instance = mock_get_llm_client.return_value
        mock_ollama_instance.chat.return_value = "mock_llm_model"

        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        # Assertions
        mock_get_llm_client.assert_called_once_with(self.mock_config)
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
                output_format=self.output_format,
            )
        self.assertIn("not supported", str(cm.exception))

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_success(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor

        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
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
        self.assertEqual(result, self.output_format(**expected_dict))
        mock_agent_executor.invoke.assert_called_once()

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_skips_invalid_messages(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor

        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        # Prepare response: 1. ToolMessage (ignored), 2. AIMessage (invalid json/schema), 3. AIMessage (valid)
        expected_dict = {"response": "Valid answer"}

        msg1 = ToolMessage("some tool output")
        msg2 = AIMessage(content='{"wrong_field": "value"}')  # Validation error
        msg3 = AIMessage(content=json.dumps(expected_dict))  # Success

        mock_agent_executor.invoke.return_value = {"messages": [msg1, msg2, msg3]}

        # Execute
        result = agent.ask("My question")

        # Assert
        self.assertEqual(result, self.output_format(**expected_dict))

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_failure_no_valid_response(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor

        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        # Prepare response with no valid AIMessage
        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("question"), ToolMessage("tool output")]
        }

        # Execute
        with self.assertRaises(ValueError) as cm:
            agent.ask("My question")

        self.assertIn("AI response", str(cm.exception))

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_handles_list_content_and_thinking_blocks(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor

        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        # Content is a list of blocks (thinking block + text block)
        expected_dict = {"response": "Successful answer from block list"}
        list_content = [
            {
                "type": "thinking",
                "thinking": "Let me think about this question first...",
            },
            {"type": "text", "text": json.dumps(expected_dict)},
        ]
        valid_msg = AIMessage(content=list_content)

        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("question"), valid_msg]
        }

        # Execute
        result = agent.ask("My question")

        # Assert
        self.assertEqual(result, self.output_format(**expected_dict))

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_handles_malformed_json_with_garbage(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        # Setup agent
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor

        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        # Malformed JSON with thinking tags/unclosed trailing blocks
        expected_dict = {"response": "Cleaned response"}
        malformed_text = (
            f"{json.dumps(expected_dict)}</think>\n"
            "```json\n"
            f"{json.dumps(expected_dict)}\n"
            "```\n"
            "<tool_response>\n"
            '{"name": "another_tool", "arguments": {"query":'
        )
        valid_msg = AIMessage(content=malformed_text)

        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("question"), valid_msg]
        }

        # Execute
        result = agent.ask("My question")

        # Assert
        self.assertEqual(result, self.output_format(**expected_dict))

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.PatientContext")
    def test_init_and_ask_with_patient_readers(
        self, mock_patient_context_cls, mock_create_agent, mock_get_llm_client
    ):
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor

        reader1 = MagicMock(spec=DocumentReader)
        reader2 = MagicMock(spec=DocumentReader)

        agent = OncowflowAgent(
            config=self.mock_config,
            patient_readers=[reader1, reader2],
            output_format=self.output_format,
        )

        self.assertEqual(agent.patient_readers, [reader1, reader2])
        passed_tools = mock_create_agent.call_args.kwargs.get("tools", [])
        tool_names = [getattr(t, "name", str(t)) for t in passed_tools]
        self.assertIn("get_patient_mtds_markdown", tool_names)
        self.assertIn("get_patient_ai_history", tool_names)
        self.assertNotIn("get_mtd_markdown", tool_names)

        expected_dict = {"response": "Full dossier response"}
        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("question"), AIMessage(json.dumps(expected_dict))]
        }

        result = agent.ask("Summarize patient history")
        self.assertEqual(result, self.output_format(**expected_dict))
        mock_patient_context_cls.assert_called_once()

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.DocumentReader")
    def test_expert_model_init_with_patient_readers(
        self, mock_doc_reader_cls, mock_create_agent, mock_get_llm_client
    ):
        from src.domain.oncology.agents import Agents

        reader1 = MagicMock(spec=DocumentReader)
        reader2 = MagicMock(spec=DocumentReader)

        agent = Agents.Pancreas_expert_agent(
            config=self.mock_config,
            patient_readers=[reader1, reader2],
        )

        self.assertEqual(agent.patient_readers, [reader1, reader2])
        self.assertIn("pancreas diseases", agent.system_prompt)
        passed_tools = mock_create_agent.call_args.kwargs.get("tools", [])
        tool_names = [getattr(t, "name", str(t)) for t in passed_tools]
        self.assertIn("get_patient_mtds_markdown", tool_names)
        self.assertIn("get_patient_ai_history", tool_names)
        self.assertIn("search_on_ressources", tool_names)

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_prefers_final_ai_message(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        intermediate = AIMessage(content=json.dumps({"response": "draft"}))
        final = AIMessage(content=json.dumps({"response": "final"}))
        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("q"), intermediate, ToolMessage("t"), final]
        }

        result = agent.ask("My question")
        self.assertEqual(result, self.output_format(response="final"))

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_retry_prompt_is_bounded_and_keeps_question(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        huge_tool_output = "PATIENT RECORD " * 10_000
        invalid = AIMessage(content='{"wrong_field": "' + "x" * 50_000 + '"}')
        valid = AIMessage(content=json.dumps({"response": "ok"}))
        mock_agent_executor.invoke.side_effect = [
            {"messages": [HumanMessage("q"), ToolMessage(huge_tool_output), invalid]},
            {"messages": [HumanMessage("q"), valid]},
        ]

        result = agent.ask("Original clinical question")

        self.assertEqual(result, self.output_format(response="ok"))
        self.assertEqual(mock_agent_executor.invoke.call_count, 2)
        retry_prompt = mock_agent_executor.invoke.call_args_list[1].args[0]["messages"][
            0
        ]["content"]
        # The original task is preserved...
        self.assertIn("Original clinical question", retry_prompt)
        # ...but neither tool outputs nor the full invalid answer are replayed.
        self.assertNotIn("PATIENT RECORD", retry_prompt)
        max_len = (
            OncowflowAgent.RETRY_MAX_OUTPUT_CHARS
            + OncowflowAgent.RETRY_MAX_ERROR_CHARS
            + 1000
        )
        self.assertLess(len(retry_prompt), max_len)

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_failure_message_does_not_dump_tool_outputs(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )
        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("q"), ToolMessage("SECRET PATIENT DATA")]
        }

        with self.assertRaises(ValueError) as cm:
            agent.ask("My question")

        self.assertNotIn("SECRET PATIENT DATA", str(cm.exception))

    def test_extract_json_str_repairs_common_llm_malformations(self):
        from src.application.agent.agent import extract_json_str

        # Trailing comma + single quotes + unclosed brace repaired by json-repair
        for raw in (
            '```json\n{"response": "trailing comma",}\n```',
            "{'response': 'single quotes'}",
            '{"response": "unclosed object"',
        ):
            repaired = extract_json_str(raw)
            parsed = self.output_format.model_validate_json(repaired)
            self.assertTrue(parsed.response)

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.Context")
    def test_ask_handles_orphan_think_and_multiple_json_candidates(
        self, mock_context_cls, mock_create_agent, mock_get_llm_client
    ):
        mock_agent_executor = MagicMock()
        mock_create_agent.return_value = mock_agent_executor
        agent = OncowflowAgent(
            config=self.mock_config,
            mtd=self.mock_reader,
            output_format=self.output_format,
        )

        # Orphan closing </think> with braces inside thinking + intermediate JSON snippet
        # before the final schema-valid JSON object.
        content = (
            'Thinking about format {"draft": "ignore"} and {Sexe} [Age]\n'
            "</think>\n"
            'Note: intermediate {"wrong_key": 123}\n'
            '{"response": "Valid final answer"}'
        )
        mock_agent_executor.invoke.return_value = {
            "messages": [HumanMessage("q"), AIMessage(content=content)]
        }

        result = agent.ask("My question")
        self.assertEqual(result, self.output_format(response="Valid final answer"))
        mock_agent_executor.invoke.assert_called_once()
