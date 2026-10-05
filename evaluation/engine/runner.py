"""Orchestrateur d'evaluation des agents Oncoflow (Unitaires et Debat Multi-Agents) avec MLflow."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import mlflow
import yaml

# Injection des repertoires necessaires dans sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
APP_DIR = BASE_DIR / "application"
EVAL_DIR = BASE_DIR / "evaluation"

# Nettoyage automatique du sous-dossier legacy evaluation/src
legacy_src = EVAL_DIR / "src"
if legacy_src.is_dir():
    shutil.rmtree(legacy_src, ignore_errors=True)

# Retrait d'EVAL_DIR de sys.path pour empecher toute interception de package
for eval_p in [str(EVAL_DIR), str(EVAL_DIR.resolve())]:
    while eval_p in sys.path:
        sys.path.remove(eval_p)

# Insertion prioritaire d'application (qui contient src) et de la racine
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(1, str(BASE_DIR))

from evaluation.engine.judge import (  # noqa: E402
    JudgeEvaluation,
    LLMJudge,
)
from evaluation.engine.metrics import (  # noqa: E402
    log_judge_evaluation_to_mlflow,
)
from evaluation.engine.prompt_optimizer import PromptOptimizer  # noqa: E402
from src.application.agent.collaborate import (  # noqa: E402
    collaborative_debate,
)
from src.application.config import AppConfig  # noqa: E402
from src.application.reader import DocumentReader  # noqa: E402

logger = logging.getLogger("OncoflowEval.Runner")


class EvaluationRunner:
    """Execute l'evaluation de bout en bout :

    1. Chargement de la configuration Oncoflow (domain oncology ou sma)
    2. Execution de l'agent unitaire ou du debat RCP complet
    3. Evaluation par le LLM Juge (sensibilise aux limites SLM)
    4. Journalisation dans MLflow
    """

    def __init__(self, config_path: Path | str | None = None):
        base_eval_dir = Path(__file__).resolve().parent.parent
        if config_path is None:
            config_path = base_eval_dir / "config/eval_config.yaml"

        with open(config_path, "r", encoding="utf-8") as f:
            self.eval_config = yaml.safe_load(f)

        self.judge = LLMJudge(config_path)

        # MLflow setup
        mlflow_cfg = self.eval_config.get("mlflow", {})
        tracking_uri = os.getenv(
            "MLFLOW_TRACKING_URI",
            mlflow_cfg.get("tracking_uri", "http://localhost:5000"),
        )
        experiment_name = mlflow_cfg.get(
            "experiment_name", "oncoflow-agents-evaluation"
        )

        mlflow.set_tracking_uri(tracking_uri)
        try:
            mlflow.set_experiment(experiment_name)
            logger.info(
                "MLflow configure : URI=%s, Experiment=%s",
                tracking_uri,
                experiment_name,
            )
        except Exception as e:
            local_artifacts_dir = base_eval_dir / "artifacts"
            local_artifacts_dir.mkdir(parents=True, exist_ok=True)
            local_db = local_artifacts_dir / "mlflow.db"
            fallback_uri = f"sqlite:///{local_db.resolve()}"
            logger.warning(
                "Serveur MLflow distant injoignable sur %s (%s). "
                "Basculement automatique sur le stockage local : %s",
                tracking_uri,
                e,
                fallback_uri,
            )
            mlflow.set_tracking_uri(fallback_uri)
            mlflow.set_experiment(experiment_name)

        # Initialisation de la telemetrie OpenTelemetry et autologging MLflow Tracing
        try:
            from src.infrastructure.telemetry.tracing import init_telemetry

            dummy_cfg = AppConfig()
            dummy_cfg.telemetry.endpoint = tracking_uri
            init_telemetry(dummy_cfg)
        except Exception as e:
            logger.warning("Initialisation telemetrie ignoree : %s", e)

    def load_domain_components(self, domain: str):
        """Charge dynamiquement les classes d'agents et le formulaire Pydantic cible selon le domaine."""
        if domain == "oncology":
            from src.domain.oncology.agents import Agents as OncoAgents
            from src.domain.oncology.patient_mdt_oncologic_form import (
                PatientMDTForm as OncoForm,
            )

            return OncoAgents(), OncoForm
        elif domain == "sma":
            from src.domain.sma.agents import Agents as SMAAgents
            from src.domain.sma.patient_mdt_sma_form import (
                PatientMDTForm as SMAForm,
            )

            return SMAAgents(), SMAForm
        else:
            raise ValueError(
                f"Domaine '{domain}' non supporte. Choisir 'oncology' ou 'sma'."
            )

    def load_manifest(self, domain: str) -> dict[str, Any]:
        manifest_path = (
            Path(__file__).resolve().parent.parent / f"datasets/{domain}/manifest.json"
        )
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifeste introuvable : {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def extract_mtd_text(self, reader: DocumentReader) -> str:
        """Extrait le texte brut ou markdown du lecteur MTD."""
        if hasattr(reader, "markdown_exporter") and reader.markdown_exporter:
            return reader.markdown_exporter[0].page_content
        elif hasattr(reader, "chunked_documents") and reader.chunked_documents:
            return "\n\n".join(doc.page_content for doc in reader.chunked_documents)
        return "Contenu du document patient non lisible."

    def run_case_evaluation(
        self,
        domain: str = "oncology",
        case_id: str | None = None,
        mode: str = "debate",
        target_agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute l'evaluation d'un cas ou de l'ensemble des cas du manifeste."""
        agents_container, form_cls = self.load_domain_components(domain)
        manifest = self.load_manifest(domain)
        cases = manifest.get("cases", [])

        if case_id:
            cases = [c for c in cases if c.get("id") == case_id]

        if not cases:
            logger.warning(
                "Aucun cas trouve pour le domaine '%s' (filtre: %s).",
                domain,
                case_id,
            )
            return []

        results = []

        # Instanciation de la configuration Oncoflow cible
        app_config = AppConfig()
        app_config.domain = domain

        for case_info in cases:
            cid = case_info["id"]
            pdf_filename = case_info["filename"]
            logger.info(
                "--- Debut de l'evaluation du cas : %s (%s) ---",
                cid,
                pdf_filename,
            )

            # Verification de l'existence du PDF
            pdf_path = Path(app_config.rcp.path) / pdf_filename
            if not pdf_path.exists():
                logger.error("Fichier patient introuvable : %s", pdf_path)
                continue

            # Initialisation du reader
            mtd_reader = DocumentReader(app_config, pdf_filename, document_type="mtd")
            try:
                mtd_reader.read_document()
            except Exception as e:
                logger.warning(
                    "Avertissement lors de la lecture du document %s: %s",
                    pdf_filename,
                    e,
                )

            mtd_text = self.extract_mtd_text(mtd_reader)

            session_id = f"eval-{domain}-{cid}"
            from src.infrastructure.telemetry.tracing import trace_session

            with mlflow.start_run(run_name=f"eval_{domain}_{mode}_{cid}"):
                mlflow.log_param("domain", domain)
                mlflow.log_param("mode", mode)
                mlflow.log_param("case_id", cid)
                mlflow.log_param("session_id", session_id)
                mlflow.set_tag("session_id", session_id)
                mlflow.set_tag("mlflow.trace.sessionId", session_id)
                mlflow.log_param("pdf_filename", pdf_filename)
                mlflow.log_param("model_engine", app_config.llm.type)
                mlflow.log_param("model_name", app_config.llm.models)
                mlflow.log_param("judge_model", self.judge.model_name)

                case_evaluations: list[JudgeEvaluation] = []

                with trace_session(session_id):
                    if mode == "debate":
                        logger.info(
                            "Lancement du workflow collaboratif de debat RCP (Session: %s)...",
                            session_id,
                        )
                        question = (
                            "Synthese complete du dossier medical pour decision de RCP/MDT : "
                            "extraire les donnees administratives, cliniques, stadification, resecabilite et bilans manquants."
                        )
                        debate_logger = app_config.set_logger("DebateEval")

                        try:
                            agent_output = collaborative_debate(
                                agents_classes=agents_container.expert_agents,
                                question=question,
                                output_format=form_cls,
                                config=app_config,
                                mtd=mtd_reader,
                                logger=debate_logger,
                                session_id=session_id,
                            )
                        except Exception as e:
                            logger.error("Echec du debat collaboratif : %s", e)
                            agent_output = {"error": str(e)}

                        current_prompt = "Debate Multi-Agents : Tour initial -> Tour croise -> Synthese coordinateur."

                        judge_eval = self.judge.evaluate(
                            domain=domain,
                            agent_name="MDT Coordinator (Debate Synthesis)",
                            case_id=cid,
                            patient_mtd_text=mtd_text,
                            agent_output=agent_output,
                            current_prompt=current_prompt,
                        )
                        case_evaluations.append(judge_eval)

                    elif mode == "single_agent":
                        eval_agents = (
                            [agents_container.list[target_agent_name]]
                            if target_agent_name
                            and target_agent_name in agents_container.list
                            else list(agents_container.list.values())
                        )

                        for agent_cls in eval_agents:
                            agent_instance = agent_cls(
                                config=app_config,
                                mtd=mtd_reader,
                                output_format=form_cls,
                            )
                            agent_display_name = getattr(
                                agent_instance, "agent_name", agent_cls.__name__
                            )
                            logger.info(
                                "Evaluation unitaire de l'agent : %s (Session: %s)",
                                agent_display_name,
                                session_id,
                            )

                            question = "Analyse ce dossier patient et extrait toutes les informations pertinentes pour ta specialite."
                            try:
                                output_obj = agent_instance.ask(
                                    question=question,
                                    session_id=session_id,
                                )
                                agent_output = (
                                    output_obj.model_dump()
                                    if hasattr(output_obj, "model_dump")
                                    else output_obj
                                )
                            except Exception as e:
                                logger.error(
                                    "Erreur d'execution de %s: %s",
                                    agent_display_name,
                                    e,
                                )
                                agent_output = {"error": str(e)}

                            current_prompt = getattr(
                                agent_instance, "system_prompt", ""
                            )

                        judge_eval = self.judge.evaluate(
                            domain=domain,
                            agent_name=agent_display_name,
                            case_id=cid,
                            patient_mtd_text=mtd_text,
                            agent_output=agent_output,
                            current_prompt=current_prompt,
                        )
                        case_evaluations.append(judge_eval)

                # Traitement des artefacts et journalisation MLflow
                artifacts_dir = Path(__file__).resolve().parent.parent / "artifacts"
                for idx, jeval in enumerate(case_evaluations):
                    artifacts = []
                    if jeval.prompt_optimization:
                        diff_md = PromptOptimizer.generate_diff_markdown(
                            agent_name=jeval.agent_name,
                            original_prompt=current_prompt,
                            suggested_prompt=jeval.prompt_optimization.suggested_prompt,
                            optimizations_applied=jeval.prompt_optimization.slm_optimizations_applied,
                            expected_gain=jeval.prompt_optimization.expected_gain,
                        )
                        art_file = PromptOptimizer.save_prompt_artifact(
                            output_dir=artifacts_dir,
                            agent_name=jeval.agent_name,
                            case_id=cid,
                            markdown_content=diff_md,
                        )
                        artifacts.append(art_file)

                    metrics_logged = log_judge_evaluation_to_mlflow(
                        jeval, artifacts=artifacts, step=idx
                    )
                    results.append(
                        {
                            "case_id": cid,
                            "agent": jeval.agent_name,
                            "metrics": metrics_logged,
                            "summary": jeval.overall_clinical_summary,
                        }
                    )

        return results
