import ast
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.application.app_functions import (
    enqueue_rcp_batch,
    enqueue_rcp_rerun,
    get_rcp_active_jobs_state,
)
from src.application.config import AppConfig
from src.application.patient import extract_card_metrics, is_rcp_visible_in_cards
from src.domain.patient import Patient
from src.domain.worker import JobStatus, JobType, RCPProcessingStatus
from src.infrastructure.queue import (
    InMemoryQueueManager,
    QueueBroker,
    reset_global_queue_manager,
)


class _FakeCollection:
    def __init__(self):
        self._docs: list[dict] = []

    def find_one(self, query: dict | None = None):
        for doc in self._docs:
            if not query or all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    def find(self, query: dict | None = None, projection: dict | None = None):
        results = []
        for doc in self._docs:
            if not query:
                results.append(dict(doc))
                continue
            match = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                results.append(dict(doc))
        return results

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                return
        if upsert:
            new_doc = dict(query)
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            if "$set" in update:
                new_doc.update(update["$set"])
            self._docs.append(new_doc)


class _FakeDatabase:
    def __init__(self):
        self._collections: dict[str, _FakeCollection] = {}

    def __getitem__(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = _FakeCollection()
        return self._collections[name]


class _FakeMongoClient:
    def __init__(self):
        self._dbs: dict[str, _FakeDatabase] = {}

    def __getitem__(self, name: str) -> _FakeDatabase:
        if name not in self._dbs:
            self._dbs[name] = _FakeDatabase()
        return self._dbs[name]

    def close(self):
        pass


@pytest.fixture
def mock_mongo_Env():
    """Provide an isolated fake Mongo client shared across Mongodb instances and reset the PriorityQueue singleton."""
    mongo_client = _FakeMongoClient()

    def _init_mock_mongodb(self, config: AppConfig):
        self.config = config
        self.logger = config.set_logger("test_mongo")
        self.client = mongo_client
        self.database = self.client[config.mongodb.database]
        self.vectordatabase = self.client[config.mongodb.vectordatabase]

    with patch(
        "src.infrastructure.documents.mongodb.Mongodb.__init__",
        new=_init_mock_mongodb,
    ):
        conf = AppConfig(
            domain="oncology",
            allowed_domains="oncology,sma",
        )
        conf.rcp.display_type = "mongodb"
        conf.queue.enabled = True
        conf.queue.batch_size = 1
        conf.queue.max_retries = 1
        conf.queue.api_url = ""
        reset_global_queue_manager(conf, auto_start_workers=False)
        yield conf, mongo_client
        reset_global_queue_manager(conf, auto_start_workers=False)


class TestPriorityQueueAndCrossDomainAPI:
    def test_two_wave_priority_ordering_and_dependency(self, mock_mongo_Env):
        conf, _ = mock_mongo_Env
        broker = QueueBroker(conf)

        res1 = broker.enqueue_import_file(
            filename="fiche_a.pdf",
            batch_id="batch_1",
            include_clinical=True,
            total_clinical_models=3,
        )
        res2 = broker.enqueue_import_file(
            filename="fiche_b.pdf",
            batch_id="batch_1",
            include_clinical=True,
            total_clinical_models=3,
        )
        assert not res1["already_queued"]
        assert not res2["already_queued"]

        # Wave 1 jobs (priority 100) must always be claimed from PriorityQueue before Wave 2 (priority 50)
        job1, lease1 = broker.claim_next_job("worker_1")
        assert job1 is not None
        assert job1["job_type"] == JobType.WAVE1_ADMIN.value
        assert job1["filename"] == "fiche_a.pdf"
        broker.complete_job(
            job1["job_id"], lease_id=lease1, resolved_patient_id="pat_a"
        )

        # Even though fiche_a's Wave 1 is done, fiche_b's Wave 1 (priority 100) must run before fiche_a's Wave 2 (priority 50)!
        job2, lease2 = broker.claim_next_job("worker_1")
        assert job2 is not None
        assert job2["job_type"] == JobType.WAVE1_ADMIN.value
        assert job2["filename"] == "fiche_b.pdf"
        broker.complete_job(
            job2["job_id"], lease_id=lease2, resolved_patient_id="pat_b"
        )

        # Now Wave 2 jobs are claimed in FIFO order
        job3, lease3 = broker.claim_next_job("worker_1")
        assert job3 is not None
        assert job3["job_type"] == JobType.WAVE2_CLINICAL.value
        assert job3["filename"] == "fiche_a.pdf"
        assert job3["resolved_patient_id"] == "pat_a"
        broker.complete_job(job3["job_id"], lease_id=lease3)

        job4, lease4 = broker.claim_next_job("worker_1")
        assert job4 is not None
        assert job4["job_type"] == JobType.WAVE2_CLINICAL.value
        assert job4["filename"] == "fiche_b.pdf"
        broker.complete_job(job4["job_id"], lease_id=lease4)

    def test_strict_deduplication_on_import_and_rerun(self, mock_mongo_Env):
        conf, _ = mock_mongo_Env

        batch_res1 = enqueue_rcp_batch(
            conf,
            [{"filename": "dup_test.pdf", "patient_id": None}],
            run_full_ai=True,
        )
        assert batch_res1["enqueued_count"] == 1
        assert batch_res1["already_queued_count"] == 0

        # Re-importing the same file while already PENDING must NOT create duplicate jobs
        batch_res2 = enqueue_rcp_batch(
            conf,
            [{"filename": "dup_test.pdf", "patient_id": None}],
            run_full_ai=True,
        )
        assert batch_res2["enqueued_count"] == 0
        assert batch_res2["already_queued_count"] == 1

        # Triggering a full rerun or single-model rerun while full job is active must be rejected
        rerun_full = enqueue_rcp_rerun(conf, "dup_test.pdf", model_name=None)
        assert rerun_full["already_queued"] is True

        rerun_single = enqueue_rcp_rerun(
            conf, "dup_test.pdf", model_name="TumorLocation"
        )
        assert rerun_single["already_queued"] is True

        state = get_rcp_active_jobs_state(conf, "dup_test.pdf")
        assert state["has_full_job"] is True
        assert state["has_any_job"] is True

        # Clean the queue, then test single-model deduplication
        broker = QueueBroker(conf)
        broker.clean_queue(mode="all")

        s1 = enqueue_rcp_rerun(conf, "dup_test.pdf", model_name="TumorLocation")
        assert s1["already_queued"] is False
        s2 = enqueue_rcp_rerun(conf, "dup_test.pdf", model_name="TumorLocation")
        assert s2["already_queued"] is True
        # A different section on the same file is allowed
        s3 = enqueue_rcp_rerun(conf, "dup_test.pdf", model_name="TumorBiology")
        assert s3["already_queued"] is False

    def test_cross_domain_priority_queue_respects_batch_size(self, mock_mongo_Env):
        conf_onco, _ = mock_mongo_Env
        conf_sma = conf_onco.for_domain("sma")

        broker_onco = QueueBroker(conf_onco)
        broker_sma = QueueBroker(conf_sma)

        broker_onco.enqueue_import_file("onco_1.pdf", include_clinical=False)
        broker_sma.enqueue_import_file("sma_1.pdf", include_clinical=False)

        # Oncology claims the single execution slot (batch_size=1)
        job_onco, lease_onco = broker_onco.claim_next_job("worker_onco")
        assert job_onco is not None
        assert lease_onco is not None

        # SMA cannot claim a job while the execution slot is held
        job_sma_blocked, lease_sma_blocked = broker_sma.claim_next_job("worker_sma")
        assert job_sma_blocked is None
        assert lease_sma_blocked is None

        # Once Oncology finishes and releases the slot, SMA can claim its job
        broker_onco.complete_job(job_onco["job_id"], lease_id=lease_onco)
        job_sma_ok, lease_sma_ok = broker_sma.claim_next_job("worker_sma")
        assert job_sma_ok is not None
        assert job_sma_ok["filename"] == "sma_1.pdf"
        broker_sma.complete_job(job_sma_ok["job_id"], lease_id=lease_sma_ok)

    def test_admin_clean_queue_modes(self, mock_mongo_Env):
        conf, _ = mock_mongo_Env
        broker = QueueBroker(conf)

        broker.enqueue_import_file("file1.pdf", include_clinical=False)
        broker.enqueue_import_file("file2.pdf", include_clinical=False)

        # Claim file1 so it is PROCESSING with an active lease
        job1, lease1 = broker.claim_next_job("worker_1")
        assert job1["status"] == JobStatus.PROCESSING.value
        assert len(broker.get_all_gpu_leases()) == 1

        # Admin reset_stuck moves PROCESSING back to PENDING and releases locks
        res_stuck = broker.clean_queue(mode="reset_stuck")
        assert res_stuck["affected_jobs"] == 1
        assert len(broker.get_all_gpu_leases()) == 0
        assert broker.get_queue_stats()["pending"] == 2

        # Admin purge all removes everything
        res_all = broker.clean_queue(mode="all")
        assert res_all["affected_jobs"] == 2
        stats = broker.get_queue_stats()
        assert stats["pending"] == 0
        assert stats["processing"] == 0

    def test_cards_visibility_and_progressive_wave2_saving(self, mock_mongo_Env):
        conf, mongo_client = mock_mongo_Env
        db = mongo_client[conf.mongodb.database]

        # 1. File in PENDING_ADMIN is hidden from cards
        doc_pending_admin = {
            "file": "patient_x.pdf",
            "processing_status": RCPProcessingStatus.PENDING_ADMIN.value,
        }
        assert is_rcp_visible_in_cards(doc_pending_admin) is False

        # 2. File after Wave 1 (PENDING_CLINICAL with PatientAdministrative) IS visible in cards
        doc_after_wave1 = {
            "file": "patient_x.pdf",
            "patient_id": "jean_dupont_1960-01-01",
            "processing_status": RCPProcessingStatus.PENDING_CLINICAL.value,
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_birth": "1960-01-01",
                "gender": "Male",
            },
        }
        assert is_rcp_visible_in_cards(doc_after_wave1) is True
        metrics = extract_card_metrics(doc_after_wave1)
        assert (
            metrics["processing_status"] == RCPProcessingStatus.PENDING_CLINICAL.value
        )
        assert metrics["missing"] == []

        # 3. Test InMemoryQueueManager Wave 1 + Wave 2 execution with mocked form
        fake_form = MagicMock()
        fake_form.mtd_datas = {"experts": {}}

        def _fake_read_model(model_cls, upsert=False):
            db["rcp_info"].update_one(
                {"file": "patient_x.pdf"},
                {"$set": {model_cls.__name__: {"mocked": True}}},
                upsert=True,
            )

        fake_form.read_model.side_effect = _fake_read_model

        with (
            patch(
                "src.infrastructure.queue.memory_queue.get_domain_mdt_form_cls",
                return_value=MagicMock(return_value=fake_form),
            ),
            patch(
                "src.infrastructure.queue.memory_queue.process_patient_association",
                return_value=Patient(
                    patient_id="jean_dupont_1960-01-01",
                    first_name="Jean",
                    last_name="Dupont",
                    files=["patient_x.pdf"],
                ),
            ),
            patch("src.infrastructure.queue.memory_queue.unload_active_models"),
        ):
            enqueue_rcp_batch(
                conf,
                [{"filename": "patient_x.pdf", "patient_id": None}],
                run_full_ai=True,
            )
            manager: InMemoryQueueManager = QueueBroker(conf)._manager

            # First step executes Wave 1 (Identification)
            assert manager.run_once() is True
            rcp_after_w1 = db["rcp_info"].find_one({"file": "patient_x.pdf"})
            assert (
                rcp_after_w1["processing_status"]
                == RCPProcessingStatus.PENDING_CLINICAL.value
            )
            assert rcp_after_w1["patient_id"] == "jean_dupont_1960-01-01"

            # Second step executes Wave 2 (Clinical models progressively saved)
            assert manager.run_once() is True
            rcp_after_w2 = db["rcp_info"].find_one({"file": "patient_x.pdf"})
            assert (
                rcp_after_w2["processing_status"] == RCPProcessingStatus.COMPLETED.value
            )

    def test_cross_domain_fastapi_endpoints(self, mock_mongo_Env):
        from importlib import import_module

        app_api = import_module("app-api")
        client = TestClient(app_api.app)

        # 1. Check /api/v1/queue/domains
        resp_domains = client.get("/api/v1/queue/domains")
        assert resp_domains.status_code == 200
        assert "oncology" in resp_domains.json()["allowed_domains"]
        assert "sma" in resp_domains.json()["allowed_domains"]

        # 2. Check /api/v1/agents across domains (oncology vs sma vs forbidden domain)
        resp_onco_agents = client.get("/api/v1/agents", params={"domain": "oncology"})
        assert resp_onco_agents.status_code == 200
        onco_names = [a["name"] for a in resp_onco_agents.json()]
        assert len(onco_names) > 0

        resp_sma_agents = client.get("/api/v1/agents", params={"domain": "sma"})
        assert resp_sma_agents.status_code == 200
        sma_names = [a["name"] for a in resp_sma_agents.json()]
        assert len(sma_names) > 0
        assert onco_names != sma_names

        resp_invalid = client.get("/api/v1/agents", params={"domain": "cardiology"})
        assert resp_invalid.status_code == 400
        assert "non autorisé" in resp_invalid.json()["detail"]

        # Check X-Oncoflow-Domain header validation in AllowedDomainMiddleware
        resp_invalid_header = client.get(
            "/api/v1/rcp", headers={"X-Oncoflow-Domain": "neurology"}
        )
        assert resp_invalid_header.status_code == 400
        assert resp_sma_agents.headers.get("X-Oncoflow-Domain") == "sma"

        # 3. Enqueue via API for SMA domain and verify domain-filtered stats
        resp_enq = client.post(
            "/api/v1/queue/enqueue-import",
            params={"domain": "sma"},
            json={
                "filename": "sma_api_patient.pdf",
                "include_clinical": True,
                "total_clinical_models": 4,
            },
        )
        assert resp_enq.status_code == 200
        assert resp_enq.json()["domain"] == "sma"
        assert resp_enq.json()["already_queued"] is False

        stats_sma = client.get("/api/v1/queue/stats", params={"domain": "sma"}).json()
        stats_onco = client.get(
            "/api/v1/queue/stats", params={"domain": "oncology"}
        ).json()
        assert stats_sma["pending"] == 2
        assert stats_onco["pending"] == 0

        # 4. Check /health, /api/v1/queue/jobs, /api/v1/queue/rerun, /api/v1/queue/clean, /api/v1/rcp
        resp_health = client.get("/health")
        assert resp_health.status_code == 200
        assert resp_health.json()["status"] == "ok"

        resp_jobs_sma = client.get(
            "/api/v1/queue/jobs",
            params={"domain": "sma", "filename": "sma_api_patient.pdf"},
        )
        assert resp_jobs_sma.status_code == 200
        assert len(resp_jobs_sma.json()) == 2

        resp_rcp_onco = client.get(
            "/api/v1/rcp", headers={"X-Oncoflow-Domain": "oncology"}
        )
        assert resp_rcp_onco.status_code == 200
        assert resp_rcp_onco.headers.get("X-Oncoflow-Domain") == "oncology"

        resp_clean = client.post(
            "/api/v1/queue/clean",
            params={"domain": "sma"},
            json={"mode": "all"},
        )
        assert resp_clean.status_code == 200
        assert resp_clean.json()["affected_jobs"] == 2

    def test_startup_recovery_and_dev_standalone_fallback(self, mock_mongo_Env):
        conf, mongo_client = mock_mongo_Env
        # Seed an unfinished RCP in oncology and one in sma
        mongo_client["Oncoflow_oncology"]["rcp_info"].update_one(
            {"file": "recover_onco.pdf"},
            {
                "$set": {
                    "file": "recover_onco.pdf",
                    "processing_status": RCPProcessingStatus.PENDING_ADMIN.value,
                }
            },
            upsert=True,
        )
        mongo_client["Oncoflow_sma"]["rcp_info"].update_one(
            {"file": "recover_sma.pdf"},
            {
                "$set": {
                    "file": "recover_sma.pdf",
                    "processing_status": RCPProcessingStatus.PENDING_CLINICAL.value,
                    "PatientAdministrative": {
                        "first_name": "Lea",
                        "last_name": "Martin",
                    },
                }
            },
            upsert=True,
        )

        manager = QueueBroker(conf)._manager
        recovered_count = manager.recover_unfinished_from_mongodb()
        assert recovered_count == 2
        assert manager.get_queue_stats(domain="oncology")["pending"] == 2
        assert manager.get_queue_stats(domain="sma")["pending"] == 1

        # Verify standalone dev fallback when api_url is unreachable
        dev_conf = conf.model_copy(deep=True)
        dev_conf.queue.api_url = "http://127.0.0.1:59999"
        dev_broker = QueueBroker(dev_conf)
        res = dev_broker.enqueue_import_file(
            "standalone_dev.pdf", include_clinical=False
        )
        assert res["already_queued"] is False
        assert manager._workers_started is True
        manager.shutdown()

    def test_fresh_process_imports_no_circular_dependency(self):
        """
        Verify in isolated Python subprocesses that importing `app-api`,
        `src.infrastructure.queue`, or `src.application.app_functions` first
        never triggers a circular ImportError.
        """
        app_dir = Path(__file__).resolve().parent.parent
        import_snippets = [
            "import importlib; importlib.import_module('app-api')",
            "import src.infrastructure.queue; import src.application.app_functions",
            "import src.application.app_functions; import src.infrastructure.queue",
            "import src.routers.queue; import src.routers.rcp; import src.routers.agents; import src.routers.resources",
        ]
        for snippet in import_snippets:
            proc = subprocess.run(
                [sys.executable, "-c", snippet],
                cwd=str(app_dir),
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert proc.returncode == 0, (
                f"Fresh import failed for `{snippet}`:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
            )

    def test_no_streamlit_imports_outside_ui(self):
        """Ensure architectural rule: no `import streamlit` outside `src/ui/`."""
        src_root = Path(__file__).resolve().parent.parent / "src"
        violations = []
        for py_file in src_root.rglob("*.py"):
            rel_parts = py_file.relative_to(src_root).parts
            if rel_parts and rel_parts[0] == "ui":
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "streamlit" or alias.name.startswith(
                            "streamlit."
                        ):
                            violations.append(str(py_file))
                elif isinstance(node, ast.ImportFrom):
                    if node.module and (
                        node.module == "streamlit"
                        or node.module.startswith("streamlit.")
                    ):
                        violations.append(str(py_file))
        assert violations == [], (
            f"Forbidden streamlit imports outside src/ui/: {violations}"
        )

    def test_logger_includes_service_field_for_ui_and_api(self):
        import io
        import json
        import logging

        with patch.object(sys, "argv", ["streamlit", "run", "app-ui.py"]):
            conf_ui = AppConfig()
            assert conf_ui.logs.service == "ui"
            assert conf_ui.rcp.docling_device == "cpu"
            conf_ui.logs.type = "text"
            logger_ui = conf_ui.set_logger("test_ui_logger")
            stream_ui = io.StringIO()
            logger_ui.handlers[0].stream = stream_ui
            logger_ui.info("Hello from UI")
            assert "[UI]" in stream_ui.getvalue()

        with patch.object(sys, "argv", ["uvicorn", "app-api:app"]):
            conf_api = AppConfig()
            assert conf_api.logs.service == "api"
            conf_api.logs.type = "json"
            logger_api = conf_api.set_logger("test_api_logger")
            stream_api = io.StringIO()
            logger_api.handlers[0].stream = stream_api
            logger_api.info("Hello from API")
            payload = json.loads(stream_api.getvalue().strip())
            assert payload["service"] == "api"
            assert payload["context"]["service"] == "api"

        AppConfig.set_runtime_override(language="english")
        try:
            assert AppConfig().language == "english"
        finally:
            AppConfig.clear_runtime_overrides()

        logging.getLogger("test_ui_logger").handlers.clear()
        logging.getLogger("test_api_logger").handlers.clear()

    def test_json_logs_stay_valid_with_quotes(self):
        import io
        import json
        import logging

        with patch.object(sys, "argv", ["uvicorn", "app-api:app"]):
            conf = AppConfig()
            conf.logs.type = "json"
            logger = conf.set_logger("test_json_quotes_logger")
            stream = io.StringIO()
            logger.handlers[0].stream = stream
            logger.info('Message with "quotes" and \\ backslash')
            payload = json.loads(stream.getvalue().strip())
            assert payload["message"] == 'Message with "quotes" and \\ backslash'
        logging.getLogger("test_json_quotes_logger").handlers.clear()

    def test_runtime_override_does_not_leak_to_other_threads(self):
        import threading

        seen: dict[str, str] = {}
        AppConfig.set_runtime_override(language="english")
        try:
            worker = threading.Thread(
                target=lambda: seen.setdefault("lang", AppConfig().language)
            )
            worker.start()
            worker.join()
            assert AppConfig().language == "english"
            assert seen["lang"] != "english"
        finally:
            AppConfig.clear_runtime_overrides()

    def test_expired_gpu_lease_is_reclaimed_and_job_requeued(self, mock_mongo_Env):
        from datetime import datetime, timedelta

        conf, _ = mock_mongo_Env
        broker = QueueBroker(conf)
        queue_manager = broker._manager

        res = broker.enqueue_import_file(
            filename="lease_expire.pdf",
            include_clinical=False,
        )
        job_id = res["jobs"][0]["job_id"]
        claimed_job, lease_id = queue_manager.claim_next_job(worker_id="dead_worker")
        assert claimed_job is not None
        assert claimed_job["job_id"] == job_id

        # Simulate expired lease timestamp
        queue_manager._active_leases[lease_id]["expires_at"] = (
            datetime.now() - timedelta(seconds=60)
        )

        reclaimed_job, new_lease_id = queue_manager.claim_next_job(
            worker_id="live_worker"
        )
        assert reclaimed_job is not None
        assert reclaimed_job["job_id"] == job_id
        assert reclaimed_job["worker_id"] == "live_worker"
        assert new_lease_id != lease_id

    def test_stale_worker_run_id_cannot_overwrite_requeued_job(self, mock_mongo_Env):
        conf, _ = mock_mongo_Env
        broker = QueueBroker(conf)
        queue_manager = broker._manager

        res = broker.enqueue_import_file(
            filename="stale_worker.pdf",
            include_clinical=False,
        )
        job_id = res["jobs"][0]["job_id"]
        first_job, stale_lease_id = queue_manager.claim_next_job(worker_id="worker_1")
        stale_run_id = first_job["run_id"]

        # Admin retries the job -> old lease released, job requeued and claimed by worker_2
        queue_manager.retry_job(job_id)
        second_job, _ = queue_manager.claim_next_job(worker_id="worker_2")
        assert second_job is not None
        assert second_job["run_id"] != stale_run_id

        # Stale worker_1 finishes late: its completion must be ignored (returns None)
        stale_result = queue_manager.complete_job(
            job_id=job_id,
            lease_id=stale_lease_id,
            run_id=stale_run_id,
        )
        assert stale_result is None
        current = queue_manager.get_job(job_id)
        assert current["status"] == JobStatus.PROCESSING.value
        assert current["worker_id"] == "worker_2"

    def test_wave2_revives_when_failed_wave1_is_retried(self, mock_mongo_Env):
        conf, _ = mock_mongo_Env
        broker = QueueBroker(conf)
        queue_manager = broker._manager

        res = broker.enqueue_import_file(
            filename="retry_wave.pdf",
            include_clinical=True,
        )
        wave1_id = res["jobs"][0]["job_id"]
        wave2_id = res["jobs"][1]["job_id"]

        # Fail wave1 exhausting retries (max_retries=0) -> wave2 becomes cancelled
        with queue_manager._lock:
            queue_manager._jobs[wave1_id]["max_retries"] = 0
        _, lease1 = queue_manager.claim_next_job(worker_id="w1")
        queue_manager.fail_job(
            job_id=wave1_id,
            error_message="transient error",
            lease_id=lease1,
        )
        assert queue_manager.get_job(wave1_id)["status"] == JobStatus.FAILED.value
        assert queue_manager.get_job(wave2_id)["status"] == JobStatus.CANCELLED.value

        # Now manual retry of wave1 revives wave2 back to pending
        queue_manager.retry_job(wave1_id)
        assert queue_manager.get_job(wave1_id)["status"] == JobStatus.PENDING.value
        assert queue_manager.get_job(wave2_id)["status"] == JobStatus.PENDING.value

    def test_delete_locks_endpoint_requires_explicit_filter(self, mock_mongo_Env):
        from fastapi import FastAPI
        from src.routers.queue import get_queue_manager, router as queue_router

        conf, _ = mock_mongo_Env
        queue_manager = QueueBroker(conf)._manager

        test_app = FastAPI()
        test_app.dependency_overrides[get_queue_manager] = lambda: queue_manager
        test_app.include_router(queue_router, prefix="/api/v1")
        client = TestClient(test_app)

        resp = client.delete("/api/v1/queue/locks")
        assert resp.status_code == 400
        assert client.delete("/api/v1/queue/locks?force_all=true").status_code == 200
