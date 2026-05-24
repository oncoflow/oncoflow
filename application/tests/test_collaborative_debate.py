import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel, Field

from src.application.config import AppConfig
from src.domain.patient_mdt_oncologic_form import PatientMDTOncologicForm
from src.application.agent.agent import DebateTurn


# Mock Output Schema for testing
class MockDebateModel(PatientMDTOncologicForm.default_model):
    class MTDComplete(BaseModel):
        complete: bool
        comment: str

    complete_data: MTDComplete = Field(description="Mock completeness data")
    collaborative = True
    agents_memory = True
    question = "Is the record complete?"


class TestCollaborativeDebate(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.rcp.display_type = "stdout"
        self.mock_config.llm.type = "ollama"
        self.mock_config.llm.models = "llama3"
        self.mock_config.llm.url = "http://127.0.0.1"
        self.mock_config.llm.port = "11434"
        self.mock_config.llm.embeddings = "all-MiniLM-L6-v2"
        self.mock_config.llm.temp = 0.7
        self.mock_config.set_logger.return_value = MagicMock()

        # Define mock agents
        self.mock_agent1_cls = MagicMock()
        self.mock_agent1_cls.agent_name = "Agent 1"
        self.mock_agent1_cls.expert_type = "diseases 1"

        self.mock_agent2_cls = MagicMock()
        self.mock_agent2_cls.agent_name = "Agent 2"
        self.mock_agent2_cls.expert_type = "diseases 2"

        MockDebateModel.agents = [self.mock_agent1_cls, self.mock_agent2_cls]

    @patch("src.application.reader.get_llm_client")
    @patch("src.domain.patient_mdt_oncologic_form.Mongodb")
    @patch("src.domain.patient_mdt_oncologic_form.DocumentReader.read_document")
    @patch("src.application.reader.VectorialDataBaseClient")
    def test_dict_to_models_collaborative(
        self, mock_vecdb, mock_read_doc, mock_mongodb, mock_get_llm
    ):
        mock_get_llm.return_value = MagicMock()
        form = PatientMDTOncologicForm(self.mock_config, "test_doc.pdf")
        form.basemodel_list = [MockDebateModel]

        # In collaborative mode, DB data is single structured dict matching the model
        db_data = {
            "MockDebateModel": {
                "complete_data": {"complete": True, "comment": "All good"}
            }
        }
        form.dict_to_models(db_data)

        # Assert that it populated the form without nesting by agent
        self.assertIn("MockDebateModel", form.mtd_datas)
        self.assertEqual(form.mtd_datas["MockDebateModel"].complete_data.complete, True)
        self.assertEqual(
            form.mtd_datas["MockDebateModel"].complete_data.comment, "All good"
        )

    @patch("src.application.reader.get_llm_client")
    @patch("src.domain.patient_mdt_oncologic_form.Mongodb")
    @patch("src.domain.patient_mdt_oncologic_form.DocumentReader.read_document")
    @patch("src.application.reader.VectorialDataBaseClient")
    def test_dict_to_models_collaborative_backward_compatibility(
        self, mock_vecdb, mock_read_doc, mock_mongodb, mock_get_ll
    ):
        mock_get_ll.return_value = MagicMock()
        form = PatientMDTOncologicForm(self.mock_config, "test_doc.pdf")
        form.basemodel_list = [MockDebateModel]

        # Old nested format keyed by agent name
        db_data = {
            "MockDebateModel": {
                "Agent 1": {
                    "complete_data": {
                        "complete": True,
                        "comment": "Anticipated nested comment",
                    }
                }
            }
        }
        form.dict_to_models(db_data)

        # Assert that it extracted and populated it successfully
        self.assertIn("MockDebateModel", form.mtd_datas)
        self.assertEqual(form.mtd_datas["MockDebateModel"].complete_data.complete, True)
        self.assertEqual(
            form.mtd_datas["MockDebateModel"].complete_data.comment,
            "Anticipated nested comment",
        )

    @patch("src.application.reader.get_llm_client")
    @patch("src.domain.patient_mdt_oncologic_form.Mongodb")
    @patch("src.domain.patient_mdt_oncologic_form.DocumentReader.read_document")
    @patch("src.application.reader.VectorialDataBaseClient")
    def test_read_model_collaborative_debate_flow(
        self, mock_vecdb, mock_read_doc, mock_mongodb, mock_get_llm
    ):
        mock_get_llm.return_value = MagicMock()
        form = PatientMDTOncologicForm(self.mock_config, "test_doc.pdf")

        # Create instances of mocked agents
        agent1_instance = MagicMock()
        agent2_instance = MagicMock()
        coordinator_instance = MagicMock()

        self.mock_agent1_cls.return_value = agent1_instance
        self.mock_agent2_cls.return_value = agent2_instance

        # Return values for round 1 (Opinions)
        opinion1 = DebateTurn(response="Initial opinion from Agent 1")
        opinion2 = DebateTurn(response="Initial opinion from Agent 2")
        agent1_instance.ask.return_value = opinion1
        agent2_instance.ask.return_value = opinion2

        # When coordinator is instantiated, mock it separately or use agent1_instance
        # In step 3, coordinator_agent_cls = model.agents[0] (which is mock_agent1_cls)
        # It gets re-instantiated with output_format=model.
        # We side_effect mock_agent1_cls so that:
        # First call (round 1): agent1_instance
        # Second call (round 2): agent1_instance
        # Third call (synthesis): coordinator_instance
        self.mock_agent1_cls.side_effect = [
            agent1_instance,
            agent1_instance,
            coordinator_instance,
        ]
        self.mock_agent2_cls.side_effect = [agent2_instance, agent2_instance]

        # Return values for round 2 (Debate update)
        opinion1_updated = DebateTurn(response="Refined opinion from Agent 1")
        opinion2_updated = DebateTurn(response="Refined opinion from Agent 2")
        agent1_instance.ask.return_value = opinion1_updated
        agent2_instance.ask.return_value = opinion2_updated

        # Return value for synthesis (Round 3)
        final_consensus = MockDebateModel(
            complete_data={"complete": True, "comment": "Consensus reached"}
        )
        coordinator_instance.ask.return_value = final_consensus

        # Execute
        form.read_model(MockDebateModel, upsert=False)

        # Assertions
        # 1. 5 calls in total to ask (Round 1: 2, Round 2: 2, Round 3: 1)
        self.assertEqual(agent1_instance.ask.call_count, 2)
        self.assertEqual(agent2_instance.ask.call_count, 2)
        coordinator_instance.ask.assert_called_once()

        # Check synthesis prompt contains final opinions of both agents
        synthesis_prompt = coordinator_instance.ask.call_args[0][0]
        self.assertIn("Refined opinion from Agent 1", synthesis_prompt)
        self.assertIn("Refined opinion from Agent 2", synthesis_prompt)

        # Verify mtd_datas has the final synthesized non-nested consensus dict
        self.assertIn("MockDebateModel", form.mtd_datas)
        self.assertEqual(
            form.mtd_datas["MockDebateModel"]["complete_data"]["complete"], True
        )
        self.assertEqual(
            form.mtd_datas["MockDebateModel"]["complete_data"]["comment"],
            "Consensus reached",
        )
