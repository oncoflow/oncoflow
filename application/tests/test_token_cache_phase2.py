import os
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from pydantic import BaseModel, Field

from src.application.agent.agent import ChatResponse, OncowflowAgent
from src.application.reader import DocumentReader
from src.domain.oncology.agents import Agents as OncologyAgents


class SectionSchemaAlpha(BaseModel):
    tumor_site: str = Field(description="Primary tumor anatomical site")
    tnm_stage: str = Field(description="Clinical TNM classification")


class SectionSchemaBeta(BaseModel):
    biomarker_msi: bool = Field(description="Microsatellite instability status")
    kras_mutation: str | None = Field(default=None, description="KRAS mutation status")


class TestTokenCachePhase2PromptPrefix(unittest.TestCase):
    """Unit tests for Phase 2 KV-cache Longest Common Prefix (LCP) prompt structuring."""

    def setUp(self) -> None:
        self.mock_config = MagicMock()
        self.mock_config.language = "french"
        self.mock_config.llm.type = "llamacpp"
        self.mock_config.llm.models = "Qwen3.5-35B-A3B-Q4_K_M.gguf"
        self.mock_config.set_logger.return_value = MagicMock()

        self.sample_patient_markdown = (
            "# COMPTE RENDU DE FICHE RCP ONCOLOGIE DIGESTIVE\n"
            "Patient : Jean DUPONT, né le 14/05/1958.\n"
            "Adénocarcinome de la tête du pancréas cT3N1M0, bilirubine 45 µmol/L.\n"
            "OMS 1, CA 19-9 : 420 U/mL. Bilan d'extension TDM thoraco-abdomino-pelvien sans métastase.\n"
        ) * 20

        self.reader_with_markdown = MagicMock(spec=DocumentReader)
        self.reader_with_markdown.document = "rcp_dupont_2026.pdf"
        self.reader_with_markdown.markdown_exporter = [
            Document(
                page_content=self.sample_patient_markdown,
                metadata={"file": "rcp_dupont_2026.pdf"},
            )
        ]

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    def test_same_agent_different_schemas_share_full_document_and_persona_prefix(
        self,
        mock_create_agent: MagicMock,
        mock_get_llm_client: MagicMock,
    ) -> None:
        """
        Two Wave 2 extractions with different output schemas must share an identical
        system prompt prefix covering the global header, pre-loaded patient record
        Markdown, agent persona, and STEP 1 instructions, diverging only at the tail schema.
        """
        OncologyAgents.Administratives_agent(
            config=self.mock_config,
            mtd=self.reader_with_markdown,
            output_format=SectionSchemaAlpha,
        )
        prompt_alpha = mock_create_agent.call_args_list[0].kwargs["system_prompt"]

        OncologyAgents.Administratives_agent(
            config=self.mock_config,
            mtd=self.reader_with_markdown,
            output_format=SectionSchemaBeta,
        )
        prompt_beta = mock_create_agent.call_args_list[1].kwargs["system_prompt"]

        # Rule 1: Must start with the standard language instruction
        self.assertTrue(
            prompt_alpha.startswith(
                "Answer in French language, not mention it in the answer."
            )
        )
        self.assertIn("PATIENT RECORD CONTEXT (PRE-LOADED)", prompt_alpha)
        self.assertIn(self.sample_patient_markdown.strip(), prompt_alpha)

        # Document context must come BEFORE agent persona and BEFORE output schema
        doc_pos = prompt_alpha.index("PATIENT RECORD CONTEXT (PRE-LOADED)")
        persona_pos = prompt_alpha.index("medical administrative assistant")
        schema_pos = prompt_alpha.index("## STEP 3")
        self.assertLess(doc_pos, persona_pos)
        self.assertLess(persona_pos, schema_pos)

        # Common prefix must include both the full patient markdown and the persona
        common_prefix = os.path.commonprefix([prompt_alpha, prompt_beta])
        self.assertIn(self.sample_patient_markdown.strip(), common_prefix)
        self.assertIn("medical administrative assistant", common_prefix)
        self.assertIn("## STEP 1", common_prefix)

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    @patch("src.application.agent.agent.DocumentReader")
    def test_different_agent_personas_share_global_header_and_patient_record_prefix(
        self,
        mock_doc_reader_cls: MagicMock,
        mock_create_agent: MagicMock,
        mock_get_llm_client: MagicMock,
    ) -> None:
        """
        Administrative and specialist expert agents operating on the same `DocumentReader`
        must share an identical prefix from token 0 through the end of the pre-loaded
        patient record Markdown so `llama.cpp` reuses the document KV cache across waves.
        """
        OncologyAgents.Administratives_agent(
            config=self.mock_config,
            mtd=self.reader_with_markdown,
            output_format=SectionSchemaAlpha,
        )
        admin_prompt = mock_create_agent.call_args_list[0].kwargs["system_prompt"]

        OncologyAgents.Pancreas_expert_agent(
            config=self.mock_config,
            mtd=self.reader_with_markdown,
            output_format=SectionSchemaBeta,
        )
        pancreas_prompt = mock_create_agent.call_args_list[1].kwargs["system_prompt"]

        OncologyAgents.Oesophagus_expert_agent(
            config=self.mock_config,
            mtd=self.reader_with_markdown,
            output_format=SectionSchemaBeta,
        )
        oeso_prompt = mock_create_agent.call_args_list[2].kwargs["system_prompt"]

        common_prefix = os.path.commonprefix(
            [admin_prompt, pancreas_prompt, oeso_prompt]
        )
        self.assertIn(self.sample_patient_markdown.strip(), common_prefix)
        self.assertGreater(len(common_prefix), len(self.sample_patient_markdown))

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    def test_chat_response_mode_does_not_preinject_patient_markdown(
        self,
        mock_create_agent: MagicMock,
        mock_get_llm_client: MagicMock,
    ) -> None:
        """
        Interactive `ChatResponse` mode must NOT pre-inject the full patient record into
        the system prompt so short greetings or connectivity checks remain lightweight.
        """
        OncowflowAgent(
            config=self.mock_config,
            mtd=self.reader_with_markdown,
            output_format=ChatResponse,
        )
        chat_prompt = mock_create_agent.call_args.kwargs["system_prompt"]
        self.assertNotIn("PATIENT RECORD CONTEXT (PRE-LOADED)", chat_prompt)
        self.assertIn("no pre-initialized conversation", chat_prompt)
        self.assertIn("WITHOUT calling any tools", chat_prompt)

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    def test_patient_readers_preloads_multi_form_markdown_in_prefix(
        self,
        mock_create_agent: MagicMock,
        mock_get_llm_client: MagicMock,
    ) -> None:
        """
        When `patient_readers` all have loaded `markdown_exporter` documents in structured
        mode, their combined Markdown is placed in the invariant prefix before the persona.
        """
        reader_1 = MagicMock(spec=DocumentReader)
        reader_1.document = "rcp_2025_01.pdf"
        reader_1.markdown_exporter = [
            Document(page_content=" Première RCP : FOLFIRINOX ")
        ]

        reader_2 = MagicMock(spec=DocumentReader)
        reader_2.document = "rcp_2026_01.pdf"
        reader_2.markdown_exporter = [
            Document(page_content=" Deuxième RCP : Réévaluation ")
        ]

        OncologyAgents.Administratives_agent(
            config=self.mock_config,
            patient_readers=[reader_1, reader_2],
            output_format=SectionSchemaAlpha,
        )
        prompt = mock_create_agent.call_args.kwargs["system_prompt"]
        self.assertIn("PATIENT RECORD CONTEXT (PRE-LOADED)", prompt)
        self.assertIn("=== FICHE RCP : rcp_2025_01.pdf ===", prompt)
        self.assertIn("=== FICHE RCP : rcp_2026_01.pdf ===", prompt)
        self.assertLess(
            prompt.index("=== FICHE RCP : rcp_2025_01.pdf ==="),
            prompt.index("## STEP 3"),
        )

    @patch("src.application.agent.agent.get_llm_client")
    @patch("src.application.agent.agent.create_agent")
    def test_context_exceeded_retry_with_prefetched_markdown_avoids_duplicate_tool_call(
        self,
        mock_create_agent: MagicMock,
        mock_get_llm_client: MagicMock,
    ) -> None:
        """
        When patient record Markdown is already pre-loaded in the system prompt, a
        ContextWindowExceededError retry prompt must explicitly forbid calling
        `get_mtd_markdown` again.
        """
        agent = OncologyAgents.Administratives_agent(
            config=self.mock_config,
            mtd=self.reader_with_markdown,
            output_format=SectionSchemaAlpha,
        )
        correction = agent._build_correction_prompt(
            original_question="Extract tumor site",
            error=RuntimeError("litellm.ContextWindowExceededError: 72000 > 64000"),
            failed_output=None,
        )
        self.assertIn("Do NOT call `get_mtd_markdown`", correction)
        self.assertIn("already pre-loaded in the system prompt", correction)


if __name__ == "__main__":
    unittest.main()
