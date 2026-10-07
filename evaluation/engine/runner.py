"""Orchestrateur d'evaluation des agents Oncoflow (Unitaires et Debat Multi-Agents) avec MLflow."""

from __future__ import annotations

from contextlib import nullcontext
import inspect
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import mlflow
import yaml

from evaluation.config.settings import EvaluationSettings

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
    LLMJudge,
)
from evaluation.engine.metrics import (  # noqa: E402
    log_judge_evaluation_to_mlflow,
    register_prompt_to_registry,
    safe_mlflow_log_text,
)
from evaluation.engine.prompt_optimizer import PromptOptimizer  # noqa: E402
from src.application.agent.collaborate import (  # noqa: E402
    collaborative_debate,
)
from src.application.config import AppConfig  # noqa: E402
from src.application.reader import DocumentReader  # noqa: E402
from src.infrastructure.telemetry.tracing import (  # noqa: E402
    ensure_tracing_destination,
    flush_telemetry_traces,
    trace_session,
)

logger = logging.getLogger("OncoflowEval.Runner")


def _configure_mlflow_artifact_storage() -> None:
    """Adapte le depot d'artefacts local de MLflow pour mapper les chemins de conteneur (/mlflow).

    Lorsque le serveur MLflow s'execute dans un conteneur Podman/Docker, l'emplacement par defaut
    declare est '/mlflow/artifacts/...'. Sur la machine hote, '/mlflow' n'est pas accessible en
    ecriture. Cette fonction redirige automatiquement ces acces vers le volume reel du conteneur
    ($HOME/.local/share/containers/storage/volumes/oncoflow-mlflow-data/_data) ou vers le dossier
    local d'artefacts d'evaluation.
    """
    try:
        from mlflow.store.artifact.local_artifact_repo import LocalArtifactRepository

        orig_init = LocalArtifactRepository.__init__
        host_vol = Path(
            os.path.expanduser(
                "~/.local/share/containers/storage/volumes/oncoflow-mlflow-data/_data"
            )
        )
        local_fallback = Path(__file__).resolve().parent.parent / "artifacts" / "mlflow"
        local_fallback.mkdir(parents=True, exist_ok=True)
        target_base = host_vol if host_vol.exists() else local_fallback

        def patched_init(self, artifact_uri, tracking_uri=None, registry_uri=None):
            if isinstance(artifact_uri, str) and artifact_uri.startswith("/mlflow"):
                artifact_uri = str(target_base) + artifact_uri[len("/mlflow") :]
            orig_init(self, artifact_uri, tracking_uri, registry_uri)

        LocalArtifactRepository.__init__ = patched_init
        logger.debug("Depot d'artefacts MLflow configure vers : %s", target_base)
    except Exception as e:
        logger.warning("Configuration stockage artefacts MLflow ignoree : %s", e)


class EvaluationRunner:
    """Execute l'evaluation de bout en bout :

    1. Chargement de la configuration Oncoflow (domain oncology ou sma)
    2. Execution de l'agent unitaire ou du debat RCP complet
    3. Evaluation par le LLM Juge (sensibilise aux limites SLM)
    4. Journalisation dans MLflow
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        settings: EvaluationSettings | None = None,
    ):
        base_eval_dir = Path(__file__).resolve().parent.parent
        if config_path is None:
            config_path = base_eval_dir / "config/eval_config.yaml"

        self.settings = settings or EvaluationSettings.from_yaml(config_path)

        # MLflow setup
        tracking_uri = self.settings.mlflow.tracking_uri
        experiment_name = self.settings.mlflow.experiment_name

        import os

        os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
        os.environ["MLFLOW_EXPERIMENT_NAME"] = experiment_name

        # Configuration du remappage des artefacts conteneur vers l'hote
        _configure_mlflow_artifact_storage()

        mlflow.set_tracking_uri(tracking_uri)
        try:
            exp = mlflow.set_experiment(experiment_name)
            self.experiment_id = str(exp.experiment_id)
            os.environ["MLFLOW_EXPERIMENT_ID"] = self.experiment_id
            logger.info(
                "MLflow configure : URI=%s, Experiment=%s (ID=%s)",
                tracking_uri,
                experiment_name,
                self.experiment_id,
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
            exp = mlflow.set_experiment(experiment_name)
            self.experiment_id = str(exp.experiment_id)
            os.environ["MLFLOW_EXPERIMENT_ID"] = self.experiment_id

        os.environ["MLFLOW_TRACING_DESTINATION"] = self.experiment_id

        # Configuration explicite et robuste de la destination des traces MLflow vers l'experience
        try:
            ensure_tracing_destination(
                experiment_id=self.experiment_id,
                experiment_name=experiment_name,
            )
            logger.info(
                "MLflow Tracing destination configuree vers l'experimentation %s (ID: %s)",
                experiment_name,
                self.experiment_id,
            )
        except Exception as e:
            logger.debug("Configuration destination trace MLflow : %s", e)

        # Initialisation de la telemetrie OpenTelemetry et autologging MLflow Tracing
        try:
            from src.infrastructure.telemetry.tracing import init_telemetry

            dummy_cfg = AppConfig()
            dummy_cfg.telemetry.endpoint = tracking_uri
            if hasattr(dummy_cfg.telemetry, "experiment_name"):
                dummy_cfg.telemetry.experiment_name = experiment_name
            init_telemetry(dummy_cfg)
        except Exception as e:
            logger.warning("Initialisation telemetrie ignoree : %s", e)

        # Initialisation du LLM Judge apres telemetrie pour que son client beneficie de l'autologging
        self.judge = LLMJudge(config_path=config_path, settings=self.settings)
        self.eval_config = {
            "mlflow": self.settings.mlflow.model_dump(),
            "judge": self.settings.judge.model_dump(),
            "execution": self.settings.execution.model_dump(),
        }

    def load_domain_components(self, domain: str):
        """Charge dynamiquement les classes d'agents et le formulaire Pydantic cible selon le domaine."""
        if domain == "oncology":
            from src.domain.oncology.agents import Agents as OncoAgents
            from src.domain.oncology.patient_mdt_oncologic_form import (
                PatientMDTOncologicForm as OncoForm,
            )

            return OncoAgents(), OncoForm
        elif domain == "sma":
            from src.domain.sma.agents import Agents as SMAAgents
            from src.domain.sma.patient_mdt_sma_form import (
                PatientMDTSmaForm as SMAForm,
            )

            return SMAAgents(), SMAForm
        else:
            raise ValueError(
                f"Domaine '{domain}' non supporte. Choisir 'oncology' ou 'sma'."
            )

    @staticmethod
    def get_form_submodels(form_cls) -> dict[str, type]:
        """Extrait tous les sous-modèles Pydantic déclarés dans le formulaire (dérivés de default_model)."""
        submodels: dict[str, type] = {}
        default_model = getattr(form_cls, "default_model", None)
        if default_model is None:
            return submodels

        for base in reversed(form_cls.__mro__):
            for name, attr in getattr(base, "__dict__", {}).items():
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, default_model)
                    and attr is not default_model
                    and attr.__name__ != "default_model"
                ):
                    submodels[attr.__name__] = attr
        return submodels

    @classmethod
    def resolve_form_submodel(
        cls, form_cls, target_name: str
    ) -> tuple[str, type] | None:
        """Trouve une classe cible dans le formulaire par nom exact, alias, ou préfixe (ex: RadiologicExamType -> RadiologicExams)."""
        submodels = cls.get_form_submodels(form_cls)
        if not submodels or not target_name:
            return None

        clean_target = target_name.strip().lower().replace("_", "").replace("-", "")

        # 1. Correspondance exacte (insensible à la casse)
        for name, model_cls in submodels.items():
            if name.lower().replace("_", "").replace("-", "") == clean_target:
                return name, model_cls

        # 2. Inclusion / Sous-chaîne
        for name, model_cls in submodels.items():
            clean_name = name.lower().replace("_", "").replace("-", "")
            if clean_target in clean_name or clean_name in clean_target:
                return name, model_cls

        # 3. Préfixe / Radical commun (ex: radiologicexam pour RadiologicExamType et RadiologicExams)
        for name, model_cls in submodels.items():
            clean_name = name.lower().replace("_", "").replace("-", "")
            common_prefix = os.path.commonprefix([clean_target, clean_name])
            if len(common_prefix) >= 8:
                return name, model_cls

        # 4. Inspection des annotations de champs (ex: si le nom cible est un enum/sous-type interne)
        for name, model_cls in submodels.items():
            for field_info in getattr(model_cls, "model_fields", {}).values():
                annotation_str = str(getattr(field_info, "annotation", ""))
                clean_annot = annotation_str.lower().replace("_", "").replace("-", "")
                if clean_target in clean_annot:
                    return name, model_cls

        return None

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

    def _evaluate_submodel_stream(
        self,
        domain: str,
        cid: str,
        pdf_filename: str,
        mtd_reader: DocumentReader,
        mtd_text: str,
        target_model_name: str,
        sub_model_cls: type,
        mode: str,
        agents_container: Any,
        target_agent_name: str | None,
        app_config: AppConfig,
        artifacts_dir: Path,
        parent_run: Any,
        step_state: dict[str, int],
    ) -> Iterator[dict[str, Any]]:
        """Evalue un sous-modele specifique (classe Pydantic) sur un cas patient donne.

        Conforme a la logique applicative (PatientMDTForm.read_model) :
        Le debat multi-agents n'est active que si le sous-modele declare collaborative=True
        ET possede plus d'un agent. Par exemple, PatientAdministrative (collaborative=False)
        est traite par l'agent administratif unique (Administratives_agent).
        """
        session_id = f"eval-{domain}-{cid}"
        domain_question = getattr(sub_model_cls, "question", "")
        if not domain_question or not domain_question.strip():
            domain_question = (
                sub_model_cls.__doc__.strip()
                if sub_model_cls.__doc__
                else f"Extract {target_model_name} from the patient record."
            )

        is_collab = getattr(sub_model_cls, "collaborative", False)
        class_agents = getattr(sub_model_cls, "agents", [])
        if not class_agents:
            class_agents = (
                agents_container.expert_agents
                if is_collab
                else [
                    getattr(
                        agents_container,
                        "Administratives_agent",
                        list(agents_container.list.values())[0],
                    )
                ]
            )

        # Determination du mode debat vs agent unitaire
        # Aligne sur PatientMDTForm.read_model : un sous-modele est en debat
        # ssi collaborative=True et len(agents) > 1.
        if mode == "debate":
            run_as_debate = True
        elif mode == "single_agent":
            run_as_debate = False
        else:  # mode == "auto" (par defaut)
            run_as_debate = is_collab and len(class_agents) > 1

        if run_as_debate:
            step_state["count"] += 1
            step_counter = step_state["count"]
            child_run_name = f"eval_{domain}_{cid}_{target_model_name.lower()}_debate"
            agent_display_name = f"MDT Debate ({target_model_name})"
            prompt_name = f"oncoflow_{domain}_{target_model_name.lower()}_debate_prompt"
            current_prompt = (
                f"### QUESTION D'EXTRACTION DU DOMAINE ({target_model_name})\n{domain_question}\n\n"
                f"### WORKFLOW MULTI-AGENTS\nTour initial -> Tour croise -> Synthese coordinateur\n\n"
                f"### FORMAT CIBLE SCHEMA\n{json.dumps(sub_model_cls.model_json_schema(), indent=2)}"
            )

            run_kwargs: dict[str, Any] = {
                "run_name": child_run_name,
                "experiment_id": getattr(self, "experiment_id", None),
            }
            if parent_run is not None:
                run_kwargs["nested"] = True

            with mlflow.start_run(**run_kwargs):
                mlflow.log_param("domain", domain)
                mlflow.log_param("mode", "debate")
                mlflow.log_param("target_class", target_model_name)
                mlflow.log_param("case_id", cid)
                mlflow.log_param("session_id", session_id)
                mlflow.set_tag("session_id", session_id)
                mlflow.set_tag("mlflow.trace.sessionId", session_id)
                mlflow.set_tag("target_class", target_model_name)
                mlflow.log_param("pdf_filename", pdf_filename)
                mlflow.log_param("model_engine", app_config.llm.type)
                mlflow.log_param("model_name", app_config.llm.models)
                mlflow.log_param("judge_model", self.judge.model_name)

                # Enregistrement IMMEDIAT du prompt dans le Prompt Registry MLflow 3 et comme artefact
                prompt_tags = {
                    "domain": domain,
                    "mode": "debate",
                    "case_id": cid,
                    "agent": agent_display_name,
                    "target_class": target_model_name,
                }
                prompt_ver = register_prompt_to_registry(
                    name=prompt_name,
                    template=current_prompt,
                    commit_message=f"Prompt debat pour {target_model_name} (cas {cid})",
                    tags=prompt_tags,
                )
                mlflow.set_tag("prompt.registry.name", prompt_name)
                if prompt_ver is not None and hasattr(prompt_ver, "version"):
                    mlflow.set_tag("prompt.registry.version", str(prompt_ver.version))
                safe_mlflow_log_text(current_prompt, f"prompts/{prompt_name}.txt")

                try:
                    with trace_session(session_id):
                        logger.info(
                            "Lancement de l'evaluation de %s (Debat) sur le cas %s...",
                            target_model_name,
                            cid,
                        )
                        debate_logger = app_config.set_logger("DebateEval")
                        debate_agents = (
                            class_agents
                            if len(class_agents) > 1
                            else agents_container.expert_agents
                        )
                        agent_output = collaborative_debate(
                            agents_classes=debate_agents,
                            question=domain_question,
                            output_format=sub_model_cls,
                            config=app_config,
                            mtd=mtd_reader,
                            logger=debate_logger,
                            session_id=session_id,
                        )

                        if hasattr(agent_output, "model_dump"):
                            try:
                                agent_output_dict = agent_output.model_dump(mode="json")
                            except TypeError:
                                agent_output_dict = agent_output.model_dump()
                        else:
                            agent_output_dict = agent_output
                        safe_mlflow_log_text(
                            json.dumps(
                                agent_output_dict,
                                indent=2,
                                ensure_ascii=False,
                                default=str,
                            ),
                            f"raw_outputs/{child_run_name}.json",
                        )

                        judge_eval = self.judge.evaluate(
                            domain=domain,
                            agent_name=agent_display_name,
                            case_id=cid,
                            patient_mtd_text=mtd_text,
                            agent_output=agent_output,
                            current_prompt=current_prompt,
                            session_id=session_id,
                        )

                    artifacts = []
                    if judge_eval.prompt_optimization:
                        diff_md = PromptOptimizer.generate_diff_markdown(
                            agent_name=judge_eval.agent_name,
                            original_prompt=current_prompt,
                            suggested_prompt=judge_eval.prompt_optimization.suggested_prompt,
                            optimizations_applied=judge_eval.prompt_optimization.slm_optimizations_applied,
                            expected_gain=judge_eval.prompt_optimization.expected_gain,
                        )
                        art_file = PromptOptimizer.save_prompt_artifact(
                            output_dir=artifacts_dir,
                            agent_name=judge_eval.agent_name,
                            case_id=cid,
                            markdown_content=diff_md,
                        )
                        artifacts.append(art_file)

                    metrics_logged = log_judge_evaluation_to_mlflow(
                        judge_eval,
                        artifacts=artifacts,
                        step=step_counter,
                        prompt_name=prompt_name,
                        prompt_template=current_prompt,
                        prompt_tags=prompt_tags,
                    )

                    flush_telemetry_traces()

                    avg = metrics_logged.get("judge_overall_average", 0.0)
                    mlflow.log_metric(
                        "running_overall_average",
                        avg,
                        step=step_counter,
                        run_id=parent_run.info.run_id
                        if parent_run is not None
                        else None,
                    )

                    yield {
                        "case_id": cid,
                        "agent": agent_display_name,
                        "metrics": metrics_logged,
                        "summary": judge_eval.overall_clinical_summary,
                        "prompt_name": prompt_name,
                        "target_class": target_model_name,
                        "status": "success",
                    }

                except Exception as e:
                    logger.error(
                        "Erreur evaluation %s (debat) cas %s : %s",
                        target_model_name,
                        cid,
                        e,
                    )
                    mlflow.set_tag("status", "FAILED")
                    mlflow.set_tag("error", str(e))
                    mlflow.log_metric("judge_overall_average", 0.0, step=step_counter)
                    flush_telemetry_traces()
                    yield {
                        "case_id": cid,
                        "agent": agent_display_name,
                        "metrics": {"judge_overall_average": 0.0},
                        "summary": f"Erreur : {e}",
                        "prompt_name": prompt_name,
                        "target_class": target_model_name,
                        "status": "error",
                    }

        else:
            eval_agents = (
                [agents_container.list[target_agent_name]]
                if target_agent_name and target_agent_name in agents_container.list
                else class_agents
            )

            for agent_cls in eval_agents:
                step_state["count"] += 1
                step_counter = step_state["count"]
                agent_instance = agent_cls(
                    config=app_config,
                    mtd=mtd_reader,
                    output_format=sub_model_cls,
                )
                agent_raw_name = getattr(
                    agent_instance, "agent_name", agent_cls.__name__
                )
                agent_display_name = f"{agent_raw_name} ({target_model_name})"
                agent_slug = (
                    agent_display_name.lower()
                    .replace(" ", "_")
                    .replace("/", "_")
                    .replace("(", "")
                    .replace(")", "")
                )
                child_run_name = f"eval_{domain}_{cid}_{agent_slug}"
                prompt_name = f"oncoflow_{domain}_{agent_slug}_prompt"

                agent_sys_prompt = getattr(agent_instance, "system_prompt", "")
                current_prompt = (
                    f"### SYSTEM PROMPT ({agent_cls.__name__})\n{agent_sys_prompt}\n\n"
                    f"### QUESTION D'EXTRACTION DU DOMAINE ({target_model_name})\n{domain_question}\n\n"
                    f"### FORMAT CIBLE SCHEMA\n{json.dumps(sub_model_cls.model_json_schema(), indent=2)}"
                )

                run_kwargs: dict[str, Any] = {
                    "run_name": child_run_name,
                    "experiment_id": getattr(self, "experiment_id", None),
                }
                if parent_run is not None:
                    run_kwargs["nested"] = True

                with mlflow.start_run(**run_kwargs):
                    mlflow.log_param("domain", domain)
                    mlflow.log_param("mode", "single_agent")
                    mlflow.log_param("target_class", target_model_name)
                    mlflow.log_param("case_id", cid)
                    mlflow.log_param("agent", agent_display_name)
                    mlflow.log_param("session_id", session_id)
                    mlflow.set_tag("session_id", session_id)
                    mlflow.set_tag("mlflow.trace.sessionId", session_id)
                    mlflow.set_tag("target_class", target_model_name)
                    mlflow.log_param("pdf_filename", pdf_filename)
                    mlflow.log_param("model_engine", app_config.llm.type)
                    mlflow.log_param("model_name", app_config.llm.models)
                    mlflow.log_param("judge_model", self.judge.model_name)

                    # Enregistrement IMMEDIAT du prompt dans le Prompt Registry MLflow 3 et comme artefact
                    prompt_tags = {
                        "domain": domain,
                        "mode": "single_agent",
                        "case_id": cid,
                        "agent": agent_display_name,
                        "target_class": target_model_name,
                    }
                    prompt_ver = register_prompt_to_registry(
                        name=prompt_name,
                        template=current_prompt,
                        commit_message=f"Prompt {agent_display_name} pour {target_model_name} (cas {cid})",
                        tags=prompt_tags,
                    )
                    mlflow.set_tag("prompt.registry.name", prompt_name)
                    if prompt_ver is not None and hasattr(prompt_ver, "version"):
                        mlflow.set_tag(
                            "prompt.registry.version", str(prompt_ver.version)
                        )
                    safe_mlflow_log_text(current_prompt, f"prompts/{prompt_name}.txt")

                    try:
                        with trace_session(session_id):
                            logger.info(
                                "Evaluation unitaire de %s pour %s sur le cas %s...",
                                agent_raw_name,
                                target_model_name,
                                cid,
                            )
                            eff_exp_id = str(
                                getattr(self, "experiment_id", None)
                                or os.environ.get("MLFLOW_EXPERIMENT_ID")
                                or "1"
                            )
                            ask_span_ctx = nullcontext()
                            try:
                                from mlflow.entities.trace_location import (
                                    MlflowExperimentLocation,
                                )

                                ask_span_ctx = mlflow.start_span(
                                    name=f"agent_ask_{agent_slug}",
                                    span_type="CHAIN",
                                    trace_destination=MlflowExperimentLocation(
                                        eff_exp_id
                                    ),
                                )
                            except Exception:
                                ask_span_ctx = nullcontext()

                            with ask_span_ctx:
                                output_obj = agent_instance.ask(
                                    question=domain_question,
                                    session_id=session_id,
                                )
                            if hasattr(output_obj, "model_dump"):
                                try:
                                    agent_output = output_obj.model_dump(mode="json")
                                except TypeError:
                                    agent_output = output_obj.model_dump()
                            else:
                                agent_output = output_obj

                            # Sauvegarde immediate de la reponse agent brute
                            safe_mlflow_log_text(
                                json.dumps(
                                    agent_output,
                                    indent=2,
                                    ensure_ascii=False,
                                    default=str,
                                ),
                                f"raw_outputs/{agent_slug}.json",
                            )

                            judge_eval = self.judge.evaluate(
                                domain=domain,
                                agent_name=agent_display_name,
                                case_id=cid,
                                patient_mtd_text=mtd_text,
                                agent_output=agent_output,
                                current_prompt=current_prompt,
                                session_id=session_id,
                                experiment_id=eff_exp_id,
                            )

                        artifacts = []
                        if judge_eval.prompt_optimization:
                            diff_md = PromptOptimizer.generate_diff_markdown(
                                agent_name=judge_eval.agent_name,
                                original_prompt=current_prompt,
                                suggested_prompt=judge_eval.prompt_optimization.suggested_prompt,
                                optimizations_applied=judge_eval.prompt_optimization.slm_optimizations_applied,
                                expected_gain=judge_eval.prompt_optimization.expected_gain,
                            )
                            art_file = PromptOptimizer.save_prompt_artifact(
                                output_dir=artifacts_dir,
                                agent_name=judge_eval.agent_name,
                                case_id=cid,
                                markdown_content=diff_md,
                            )
                            artifacts.append(art_file)

                        metrics_logged = log_judge_evaluation_to_mlflow(
                            judge_eval,
                            artifacts=artifacts,
                            step=step_counter,
                            prompt_name=prompt_name,
                            prompt_template=current_prompt,
                            prompt_tags=prompt_tags,
                        )

                        flush_telemetry_traces()

                        avg = metrics_logged.get("judge_overall_average", 0.0)
                        mlflow.log_metric(
                            "running_overall_average",
                            avg,
                            step=step_counter,
                            run_id=parent_run.info.run_id
                            if parent_run is not None
                            else None,
                        )

                        yield {
                            "case_id": cid,
                            "agent": agent_display_name,
                            "metrics": metrics_logged,
                            "summary": judge_eval.overall_clinical_summary,
                            "prompt_name": prompt_name,
                            "target_class": target_model_name,
                            "status": "success",
                        }

                    except Exception as e:
                        logger.error(
                            "Erreur evaluation %s (%s) cas %s : %s",
                            agent_raw_name,
                            target_model_name,
                            cid,
                            e,
                        )
                        mlflow.set_tag("status", "FAILED")
                        mlflow.set_tag("error", str(e))
                        mlflow.log_metric(
                            "judge_overall_average", 0.0, step=step_counter
                        )
                        flush_telemetry_traces()
                        yield {
                            "case_id": cid,
                            "agent": agent_display_name,
                            "metrics": {"judge_overall_average": 0.0},
                            "summary": f"Erreur : {e}",
                            "prompt_name": prompt_name,
                            "target_class": target_model_name,
                            "status": "error",
                        }

    def run_case_evaluation_stream(
        self,
        domain: str = "oncology",
        case_id: str | None = None,
        mode: str = "auto",
        target_agent_name: str | None = None,
        target_class: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Execute l'evaluation au fil de l'eau (question par question / cas par cas) et yield chaque resultat."""
        if target_class is None:
            target_class = getattr(self.settings.execution, "target_class", None)

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
            return

        resolved_class: tuple[str, type] | None = None
        if target_class:
            resolved_class = self.resolve_form_submodel(form_cls, target_class)
            if not resolved_class:
                available_classes = list(self.get_form_submodels(form_cls).keys())
                err_msg = (
                    f"Classe cible '{target_class}' introuvable dans le formulaire {form_cls.__name__}. "
                    f"Classes disponibles : {', '.join(available_classes)}"
                )
                logger.error(err_msg)
                yield {
                    "case_id": "N/A",
                    "agent": "N/A",
                    "metrics": {"judge_overall_average": 0.0},
                    "summary": err_msg,
                    "target_class": target_class,
                    "status": "error",
                }
                return
            target_model_name, sub_model_cls = resolved_class
            logger.info(
                "Evaluation ciblee activee sur la classe : %s (Modele: %s)",
                target_model_name,
                sub_model_cls.__name__,
            )

        app_config = AppConfig()
        app_config.domain = domain
        artifacts_dir = Path(__file__).resolve().parent.parent / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        session_timestamp = int(time.time())
        target_suffix = f"_{target_class}" if target_class else ""
        parent_run_name = (
            f"eval_session_{domain}_{mode}{target_suffix}_{session_timestamp}"
        )
        step_state = {"count": 0}

        # Pour une évaluation ciblée sur un cas unique (ou une classe unique),
        # on ne crée pas de run parent conteneur afin d'éviter d'afficher 2 runs dans l'UI MLflow.
        is_single_eval = (
            (resolved_class is not None and len(cases) == 1)
            or (target_class is not None and len(cases) == 1)
            or (mode == "debate" and len(cases) == 1)
        )

        parent_run_ctx = (
            nullcontext()
            if is_single_eval
            else mlflow.start_run(
                run_name=parent_run_name,
                experiment_id=getattr(self, "experiment_id", None),
            )
        )

        with parent_run_ctx as parent_run:
            if parent_run is not None:
                mlflow.log_param("domain", domain)
                mlflow.log_param("mode", mode)
                if target_class and resolved_class:
                    mlflow.log_param("target_class", resolved_class[0])
                    mlflow.set_tag("target_class", resolved_class[0])
                mlflow.log_param("total_cases", len(cases))
                mlflow.set_tag("domain", domain)
                mlflow.set_tag("mode", mode)
                mlflow.set_tag("evaluation_flow", "streaming_progressive")

            for case_info in cases:
                cid = case_info["id"]
                pdf_filename = case_info["filename"]
                logger.info(
                    "--- Debut de l'evaluation du cas : %s (%s) ---",
                    cid,
                    pdf_filename,
                )

                pdf_path = Path(app_config.rcp.path) / pdf_filename
                if not pdf_path.exists():
                    logger.error("Fichier patient introuvable : %s", pdf_path)
                    err_res = {
                        "case_id": cid,
                        "agent": "N/A",
                        "metrics": {"judge_overall_average": 0.0},
                        "summary": f"Fichier patient introuvable : {pdf_filename}",
                        "target_class": resolved_class[0] if resolved_class else None,
                        "status": "error",
                    }
                    yield err_res
                    continue

                mtd_reader = DocumentReader(
                    app_config, pdf_filename, document_type="mtd"
                )
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

                if resolved_class:
                    target_model_name, sub_model_cls = resolved_class
                    yield from self._evaluate_submodel_stream(
                        domain=domain,
                        cid=cid,
                        pdf_filename=pdf_filename,
                        mtd_reader=mtd_reader,
                        mtd_text=mtd_text,
                        target_model_name=target_model_name,
                        sub_model_cls=sub_model_cls,
                        mode=mode,
                        agents_container=agents_container,
                        target_agent_name=target_agent_name,
                        app_config=app_config,
                        artifacts_dir=artifacts_dir,
                        parent_run=parent_run,
                        step_state=step_state,
                    )

                elif mode == "auto":
                    # Mode auto par defaut : on evalue l'ensemble des sous-modeles du formulaire
                    # au fil de l'eau, chaque sous-modele determinant automatiquement son mode
                    # (debat collaboratif ou agent unique) selon ses metadonnees.
                    form_submodels = self.get_form_submodels(form_cls)
                    for target_model_name, sub_model_cls in form_submodels.items():
                        yield from self._evaluate_submodel_stream(
                            domain=domain,
                            cid=cid,
                            pdf_filename=pdf_filename,
                            mtd_reader=mtd_reader,
                            mtd_text=mtd_text,
                            target_model_name=target_model_name,
                            sub_model_cls=sub_model_cls,
                            mode="auto",
                            agents_container=agents_container,
                            target_agent_name=target_agent_name,
                            app_config=app_config,
                            artifacts_dir=artifacts_dir,
                            parent_run=parent_run,
                            step_state=step_state,
                        )

                elif mode == "debate":
                    step_state["count"] += 1
                    step_counter = step_state["count"]
                    child_run_name = f"eval_{domain}_{mode}_{cid}"
                    agent_display_name = "MDT Coordinator (Debate Synthesis)"
                    question = (
                        "Synthese complete du dossier medical pour decision de RCP/MDT : "
                        "extraire les donnees administratives, cliniques, stadification, resecabilite et bilans manquants."
                    )
                    prompt_name = f"oncoflow_{domain}_debate_prompt"
                    current_prompt = (
                        f"### QUESTION DU DEBAT RCP\n{question}\n\n"
                        f"### WORKFLOW MULTI-AGENTS\nTour initial -> Tour croise -> Synthese coordinateur\n\n"
                        f"### FORMAT CIBLE\n{form_cls.__name__}"
                    )

                    run_kwargs: dict[str, Any] = {
                        "run_name": child_run_name,
                        "experiment_id": getattr(self, "experiment_id", None),
                    }
                    if parent_run is not None:
                        run_kwargs["nested"] = True

                    with mlflow.start_run(**run_kwargs):
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

                        # Enregistrement IMMEDIAT du prompt dans le Prompt Registry MLflow 3 et comme artefact
                        prompt_tags = {
                            "domain": domain,
                            "mode": mode,
                            "case_id": cid,
                            "agent": agent_display_name,
                        }
                        prompt_ver = register_prompt_to_registry(
                            name=prompt_name,
                            template=current_prompt,
                            commit_message=f"Prompt debat global pour {domain} (cas {cid})",
                            tags=prompt_tags,
                        )
                        mlflow.set_tag("prompt.registry.name", prompt_name)
                        if prompt_ver is not None and hasattr(prompt_ver, "version"):
                            mlflow.set_tag(
                                "prompt.registry.version", str(prompt_ver.version)
                            )
                        safe_mlflow_log_text(
                            current_prompt, f"prompts/{prompt_name}.txt"
                        )

                        try:
                            with trace_session(session_id):
                                logger.info(
                                    "Lancement du debat RCP pour le cas %s (Session: %s)...",
                                    cid,
                                    session_id,
                                )
                                eff_exp_id = str(
                                    getattr(self, "experiment_id", None)
                                    or os.environ.get("MLFLOW_EXPERIMENT_ID")
                                    or "1"
                                )
                                debate_span_ctx = nullcontext()
                                try:
                                    from mlflow.entities.trace_location import (
                                        MlflowExperimentLocation,
                                    )

                                    debate_span_ctx = mlflow.start_span(
                                        name=f"mdt_debate_{cid}",
                                        span_type="CHAIN",
                                        trace_destination=MlflowExperimentLocation(
                                            eff_exp_id
                                        ),
                                    )
                                except Exception:
                                    debate_span_ctx = nullcontext()

                                with debate_span_ctx:
                                    debate_logger = app_config.set_logger("DebateEval")
                                    output_obj = collaborative_debate(
                                        agents_classes=agents_container.expert_agents,
                                        question=question,
                                        output_format=form_cls,
                                        config=app_config,
                                        mtd=mtd_reader,
                                        logger=debate_logger,
                                        session_id=session_id,
                                    )
                                if hasattr(output_obj, "model_dump"):
                                    try:
                                        agent_output = output_obj.model_dump(
                                            mode="json"
                                        )
                                    except TypeError:
                                        agent_output = output_obj.model_dump()
                                else:
                                    agent_output = output_obj

                                # Sauvegarde immediate de la reponse agent brute
                                safe_mlflow_log_text(
                                    json.dumps(
                                        agent_output,
                                        indent=2,
                                        ensure_ascii=False,
                                        default=str,
                                    ),
                                    f"raw_outputs/{child_run_name}.json",
                                )

                                judge_eval = self.judge.evaluate(
                                    domain=domain,
                                    agent_name=agent_display_name,
                                    case_id=cid,
                                    patient_mtd_text=mtd_text,
                                    agent_output=agent_output,
                                    current_prompt=current_prompt,
                                    session_id=session_id,
                                    experiment_id=eff_exp_id,
                                )

                            artifacts = []
                            if judge_eval.prompt_optimization:
                                diff_md = PromptOptimizer.generate_diff_markdown(
                                    agent_name=judge_eval.agent_name,
                                    original_prompt=current_prompt,
                                    suggested_prompt=judge_eval.prompt_optimization.suggested_prompt,
                                    optimizations_applied=judge_eval.prompt_optimization.slm_optimizations_applied,
                                    expected_gain=judge_eval.prompt_optimization.expected_gain,
                                )
                                art_file = PromptOptimizer.save_prompt_artifact(
                                    output_dir=artifacts_dir,
                                    agent_name=judge_eval.agent_name,
                                    case_id=cid,
                                    markdown_content=diff_md,
                                )
                                artifacts.append(art_file)

                            metrics_logged = log_judge_evaluation_to_mlflow(
                                judge_eval,
                                artifacts=artifacts,
                                step=step_counter,
                                prompt_name=prompt_name,
                                prompt_template=current_prompt,
                                prompt_tags=prompt_tags,
                            )

                            flush_telemetry_traces()

                            avg = metrics_logged.get("judge_overall_average", 0.0)
                            mlflow.log_metric(
                                "running_overall_average",
                                avg,
                                step=step_counter,
                                run_id=parent_run.info.run_id
                                if parent_run is not None
                                else None,
                            )

                            res_item = {
                                "case_id": cid,
                                "agent": agent_display_name,
                                "metrics": metrics_logged,
                                "summary": judge_eval.overall_clinical_summary,
                                "prompt_name": prompt_name,
                                "status": "success",
                            }
                            yield res_item

                        except Exception as e:
                            logger.error("Echec de l'evaluation du cas %s : %s", cid, e)
                            mlflow.set_tag("status", "FAILED")
                            mlflow.set_tag("error", str(e))
                            mlflow.log_metric(
                                "judge_overall_average", 0.0, step=step_counter
                            )
                            flush_telemetry_traces()
                            err_res = {
                                "case_id": cid,
                                "agent": agent_display_name,
                                "metrics": {"judge_overall_average": 0.0},
                                "summary": f"Erreur : {e}",
                                "prompt_name": prompt_name,
                                "status": "error",
                            }
                            yield err_res

                elif mode == "single_agent":
                    eval_agents = (
                        [agents_container.list[target_agent_name]]
                        if target_agent_name
                        and target_agent_name in agents_container.list
                        else list(agents_container.list.values())
                    )

                    for agent_cls in eval_agents:
                        step_state["count"] += 1
                        step_counter = step_state["count"]
                        agent_instance = agent_cls(
                            config=app_config,
                            mtd=mtd_reader,
                            output_format=form_cls,
                        )
                        agent_display_name = getattr(
                            agent_instance, "agent_name", agent_cls.__name__
                        )
                        agent_slug = (
                            agent_display_name.lower()
                            .replace(" ", "_")
                            .replace("/", "_")
                        )
                        child_run_name = f"eval_{domain}_single_{cid}_{agent_slug}"
                        prompt_name = f"oncoflow_{domain}_{agent_slug}_prompt"

                        run_kwargs: dict[str, Any] = {
                            "run_name": child_run_name,
                            "experiment_id": getattr(self, "experiment_id", None),
                        }
                        if parent_run is not None:
                            run_kwargs["nested"] = True

                        with mlflow.start_run(**run_kwargs):
                            mlflow.log_param("domain", domain)
                            mlflow.log_param("mode", mode)
                            mlflow.log_param("case_id", cid)
                            mlflow.log_param("agent", agent_display_name)
                            mlflow.log_param("session_id", session_id)
                            mlflow.set_tag("session_id", session_id)
                            mlflow.set_tag("mlflow.trace.sessionId", session_id)
                            mlflow.log_param("pdf_filename", pdf_filename)
                            mlflow.log_param("model_engine", app_config.llm.type)
                            mlflow.log_param("model_name", app_config.llm.models)
                            mlflow.log_param("judge_model", self.judge.model_name)

                            question = "Analyse ce dossier patient et extrait toutes les informations pertinentes pour ta specialite."
                            current_prompt = (
                                getattr(agent_instance, "system_prompt", "") or question
                            )
                            prompt_template = (
                                f"### SYSTEM PROMPT\n{current_prompt}\n\n"
                                f"### USER QUESTION\n{question}"
                            )

                            try:
                                with trace_session(session_id):
                                    logger.info(
                                        "Evaluation unitaire de %s sur le cas %s (Session: %s)...",
                                        agent_display_name,
                                        cid,
                                        session_id,
                                    )
                                    eff_exp_id = str(
                                        getattr(self, "experiment_id", None)
                                        or os.environ.get("MLFLOW_EXPERIMENT_ID")
                                        or "1"
                                    )
                                    ask_span_ctx = nullcontext()
                                    try:
                                        from mlflow.entities.trace_location import (
                                            MlflowExperimentLocation,
                                        )

                                        ask_span_ctx = mlflow.start_span(
                                            name=f"agent_ask_{agent_slug}",
                                            span_type="CHAIN",
                                            trace_destination=MlflowExperimentLocation(
                                                eff_exp_id
                                            ),
                                        )
                                    except Exception:
                                        ask_span_ctx = nullcontext()

                                    with ask_span_ctx:
                                        output_obj = agent_instance.ask(
                                            question=question,
                                            session_id=session_id,
                                        )
                                    if hasattr(output_obj, "model_dump"):
                                        try:
                                            agent_output = output_obj.model_dump(
                                                mode="json"
                                            )
                                        except TypeError:
                                            agent_output = output_obj.model_dump()
                                    else:
                                        agent_output = output_obj

                                    judge_eval = self.judge.evaluate(
                                        domain=domain,
                                        agent_name=agent_display_name,
                                        case_id=cid,
                                        patient_mtd_text=mtd_text,
                                        agent_output=agent_output,
                                        current_prompt=prompt_template,
                                        session_id=session_id,
                                        experiment_id=eff_exp_id,
                                    )

                                artifacts = []
                                if judge_eval.prompt_optimization:
                                    diff_md = PromptOptimizer.generate_diff_markdown(
                                        agent_name=judge_eval.agent_name,
                                        original_prompt=current_prompt,
                                        suggested_prompt=judge_eval.prompt_optimization.suggested_prompt,
                                        optimizations_applied=judge_eval.prompt_optimization.slm_optimizations_applied,
                                        expected_gain=judge_eval.prompt_optimization.expected_gain,
                                    )
                                    art_file = PromptOptimizer.save_prompt_artifact(
                                        output_dir=artifacts_dir,
                                        agent_name=judge_eval.agent_name,
                                        case_id=cid,
                                        markdown_content=diff_md,
                                    )
                                    artifacts.append(art_file)

                                metrics_logged = log_judge_evaluation_to_mlflow(
                                    judge_eval,
                                    artifacts=artifacts,
                                    step=step_counter,
                                    prompt_name=prompt_name,
                                    prompt_template=prompt_template,
                                    prompt_tags={
                                        "domain": domain,
                                        "mode": mode,
                                        "case_id": cid,
                                        "agent": agent_display_name,
                                    },
                                )

                                flush_telemetry_traces()

                                avg = metrics_logged.get("judge_overall_average", 0.0)
                                mlflow.log_metric(
                                    "running_overall_average",
                                    avg,
                                    step=step_counter,
                                    run_id=parent_run.info.run_id
                                    if parent_run is not None
                                    else None,
                                )

                                res_item = {
                                    "case_id": cid,
                                    "agent": agent_display_name,
                                    "metrics": metrics_logged,
                                    "summary": judge_eval.overall_clinical_summary,
                                    "prompt_name": prompt_name,
                                    "status": "success",
                                }
                                yield res_item

                            except Exception as e:
                                logger.error(
                                    "Erreur d'execution de %s sur le cas %s : %s",
                                    agent_display_name,
                                    cid,
                                    e,
                                )
                                mlflow.set_tag("status", "FAILED")
                                mlflow.set_tag("error", str(e))
                                flush_telemetry_traces()
                                err_res = {
                                    "case_id": cid,
                                    "agent": agent_display_name,
                                    "metrics": {"judge_overall_average": 0.0},
                                    "summary": f"Erreur : {e}",
                                    "prompt_name": prompt_name,
                                    "status": "error",
                                }
                                yield err_res

    def run_case_evaluation(
        self,
        domain: str = "oncology",
        case_id: str | None = None,
        mode: str = "auto",
        target_agent_name: str | None = None,
        target_class: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute l'evaluation de tous les cas selectionnes et retourne l'ensemble des resultats."""
        return list(
            self.run_case_evaluation_stream(
                domain=domain,
                case_id=case_id,
                mode=mode,
                target_agent_name=target_agent_name,
                target_class=target_class,
            )
        )
