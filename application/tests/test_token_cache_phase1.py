from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel, Field

from src.application.agent.agent import DebateTurn
from src.application.agent.collaborate import collaborative_debate
from src.infrastructure.llm import factory as llm_factory
from src.infrastructure.llm import base as llm_base


class _DummyConsensusSchema(BaseModel):
    summary: str = Field(description="Consensus summary")


class TestTokenCachePhase1(unittest.TestCase):
    """Unit tests for Phase 1 low-footprint LLM token & embedding caching (Volet A)."""

    def setUp(self) -> None:
        if hasattr(llm_factory, "clear_llm_client_cache"):
            llm_factory.clear_llm_client_cache()
        from src.application.agent import collaborate as collab_mod

        if hasattr(collab_mod, "clear_debate_checkpoint_cache"):
            collab_mod.clear_debate_checkpoint_cache()

    def _make_config(
        self, port: str = "4000", models: str = "openai/agents"
    ) -> MagicMock:
        cfg = MagicMock()
        cfg.llm.type = "litellm"
        cfg.llm.url = "http://litellm"
        cfg.llm.port = port
        cfg.llm.embeddings_port = port
        cfg.llm.uri = "/v1"
        cfg.llm.models = models
        cfg.llm.embeddings = "openai/embeddings"
        cfg.llm.temp = 0.6
        cfg.llm.api_key = "secret-key"
        cfg.set_logger.return_value = MagicMock()
        return cfg

    @patch("src.infrastructure.llm.factory.LiteLLMConnect")
    def test_get_llm_client_caches_instance_for_identical_config(
        self, mock_litellm_cls: MagicMock
    ) -> None:
        """Repeated get_llm_client(config) calls with identical settings must reuse the cached client."""

        def _build_instance(_cfg: MagicMock) -> MagicMock:
            raw_embedding = MagicMock()
            raw_embedding.embed_query.side_effect = lambda text: [float(len(text)), 0.5]
            inst = MagicMock()
            inst.embedding = raw_embedding
            return inst

        mock_litellm_cls.side_effect = _build_instance

        cfg1 = self._make_config(port="4000")
        cfg2 = self._make_config(port="4000")
        cfg_other = self._make_config(port="4001")

        client1 = llm_factory.get_llm_client(cfg1)
        client2 = llm_factory.get_llm_client(cfg2)
        self.assertIs(client1, client2)
        self.assertIsInstance(client1.embedding, llm_base.CachedEmbeddingsProxy)
        self.assertEqual(mock_litellm_cls.call_count, 1)

        client3 = llm_factory.get_llm_client(cfg_other)
        self.assertEqual(mock_litellm_cls.call_count, 2)
        self.assertIsNot(client1, client3)

        llm_factory.clear_llm_client_cache()
        llm_factory.get_llm_client(cfg1)
        self.assertEqual(mock_litellm_cls.call_count, 3)

    def test_cached_embeddings_proxy_deduplicates_queries_and_protects_vectors(
        self,
    ) -> None:
        """CachedEmbeddingsProxy must cache embed_query calls with bounded LRU and return defensive copies."""
        raw_emb = MagicMock()
        raw_emb.model = "bge-m3"
        raw_emb.embed_query.side_effect = lambda q: [1.0, 2.0, float(len(q))]
        raw_emb.embed_documents.return_value = [[0.1, 0.2]]

        proxy = llm_base.CachedEmbeddingsProxy(raw_emb, model_key="bge-m3", maxsize=2)

        # First call -> miss
        v1 = proxy.embed_query("  posologie risdiplam  ")
        self.assertEqual(v1, [1.0, 2.0, 19.0])
        self.assertEqual(raw_emb.embed_query.call_count, 1)

        # Mutate caller's list -> must not corrupt cached vector
        v1.append(999.0)

        # Second call with same normalized query -> hit
        v2 = proxy.embed_query("posologie risdiplam")
        self.assertEqual(v2, [1.0, 2.0, 19.0])
        self.assertEqual(raw_emb.embed_query.call_count, 1)

        info = proxy.cache_info()
        self.assertEqual(info["hits"], 1)
        self.assertEqual(info["misses"], 1)

        # Fill bounded LRU (maxsize=2) and trigger eviction of oldest entry
        proxy.embed_query("query two")
        proxy.embed_query("query three")
        self.assertEqual(proxy.cache_info()["currsize"], 2)

        # "posologie risdiplam" was evicted -> recomputed
        proxy.embed_query("posologie risdiplam")
        self.assertEqual(raw_emb.embed_query.call_count, 4)

        # Transparent attribute delegation and LangChain Embeddings ABC conformance
        from langchain_core.embeddings import Embeddings

        self.assertIsInstance(proxy, Embeddings)
        self.assertEqual(proxy.model, "bge-m3")
        self.assertEqual(proxy.embed_documents(["doc"]), [[0.1, 0.2]])

    @patch("src.application.agent.collaborate.Agents.Coordinator_agent")
    def test_collaborative_debate_reuses_rounds_1_and_2_when_coordinator_retries(
        self,
        mock_coordinator_cls: MagicMock,
    ) -> None:
        """If Coordinator_agent fails in Round 3, retrying collaborative_debate must reuse Round 1 & 2 opinions."""
        mock_config = self._make_config()
        mock_config.domain = None
        mock_logger = MagicMock()

        mock_reader = MagicMock()
        mock_reader.document = "patient_rcp_01.pdf"
        mock_reader.file_hash = "abc123hash"

        agent1_instance = MagicMock()
        agent1_instance.agent_name = "Expert 1"
        agent1_instance.expert_type = "Oncology"
        agent1_instance.response_language = "french"
        agent1_instance.ask.side_effect = [
            DebateTurn(response="Round 1 opinion E1"),
            DebateTurn(response="Round 2 opinion E1"),
        ]
        agent1_cls = MagicMock(return_value=agent1_instance)
        agent1_cls.agent_name = "Expert 1"

        agent2_instance = MagicMock()
        agent2_instance.agent_name = "Expert 2"
        agent2_instance.expert_type = "Surgery"
        agent2_instance.response_language = "french"
        agent2_instance.ask.side_effect = [
            DebateTurn(response="Round 1 opinion E2"),
            DebateTurn(response="Round 2 opinion E2"),
        ]
        agent2_cls = MagicMock(return_value=agent2_instance)
        agent2_cls.agent_name = "Expert 2"

        coordinator_instance = MagicMock()
        coordinator_instance.agent_name = "MDT Coordinator"
        coordinator_instance.response_language = "french"
        coordinator_instance.latest_thinking = "Synthesizing..."
        # Attempt 1 fails in Round 3; Attempt 2 succeeds
        coordinator_instance.ask.side_effect = [
            ValueError("Malformed JSON from coordinator on attempt 1"),
            _DummyConsensusSchema(summary="Final consensus after retry"),
        ]
        mock_coordinator_cls.return_value = coordinator_instance

        # Attempt 1 -> raises ValueError in Round 3 after completing Rounds 1 & 2
        with self.assertRaises(ValueError):
            collaborative_debate(
                agents_classes=[agent1_cls, agent2_cls],
                question="Is treatment urgent?",
                output_format=_DummyConsensusSchema,
                config=mock_config,
                mtd=mock_reader,
                logger=mock_logger,
            )

        self.assertEqual(agent1_instance.ask.call_count, 2)
        self.assertEqual(agent2_instance.ask.call_count, 2)
        self.assertEqual(coordinator_instance.ask.call_count, 1)

        # Attempt 2 (retry) -> reuses Round 1 & Round 2 from checkpoint without calling experts again
        res = collaborative_debate(
            agents_classes=[agent1_cls, agent2_cls],
            question="Is treatment urgent?",
            output_format=_DummyConsensusSchema,
            config=mock_config,
            mtd=mock_reader,
            logger=mock_logger,
        )
        self.assertEqual(res["summary"], "Final consensus after retry")
        # Specialist agents were NOT called again!
        self.assertEqual(agent1_instance.ask.call_count, 2)
        self.assertEqual(agent2_instance.ask.call_count, 2)
        self.assertEqual(coordinator_instance.ask.call_count, 2)

    def test_docker_compose_prod_configures_llama_cpp_cache_ram(self) -> None:
        """Production docker-compose.prod.yml must enable --cache-ram on llama-cpp-chat."""
        compose_path = (
            Path(__file__).resolve().parent.parent.parent
            / "dist"
            / "docker"
            / "compose"
            / "docker-compose.prod.yml"
        )
        content = compose_path.read_text(encoding="utf-8")
        self.assertIn("--cache-ram", content)
        self.assertIn("LLM_CACHE_RAM_MIB", content)


if __name__ == "__main__":
    unittest.main()
