import ast
import copy
from datetime import datetime
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.application.patient import (
    extract_card_metrics,
    is_rcp_visible_in_cards,
)
from src.application.queue_worker import DomainQueueWorker
from src.domain.worker import (
    JobPriority,
    JobStatus,
    JobType,
    QueueJob,
    RCPProcessingStatus,
)
from src.infrastructure.queue import SqliteQueueBroker


class TestSqliteQueueBrokerAndWorker(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_queue.db")

        self.config = MagicMock()
        self.config.domain = "oncology"
        self.config.rcp.display_type = "local"
        self.config.queue.enabled = True
        self.config.queue.hardware_profile = "l4_24gb"
        self.config.queue.batch_size = 1
        self.config.queue.global_gpu_lock = True
        self.config.queue.poll_interval = 1
        self.config.queue.lease_ttl_seconds = 900
        self.config.queue.max_retries = 2
        self.config.queue.db_path = self.db_path
        self.config.set_logger.return_value = MagicMock()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _make_broker(
        self,
        domain: str = "oncology",
        batch_size: int = 1,
        global_gpu_lock: bool = True,
    ) -> SqliteQueueBroker:
        cfg = copy.deepcopy(self.config)
        cfg.domain = domain
        cfg.queue.batch_size = batch_size
        cfg.queue.global_gpu_lock = global_gpu_lock
        return SqliteQueueBroker(cfg, sync_mongodb=False)

    def test_two_wave_priority_ordering_and_dependency(self):
        """
        Uploading 3 files in a batch must process all 3 WAVE1_ADMIN jobs (priority 100)
        before any WAVE2_CLINICAL job (priority 50).
        """
        broker = self._make_broker(batch_size=3)
        try:
            for fn in ["rcp1.pdf", "rcp2.pdf", "rcp3.pdf"]:
                res = broker.enqueue_import_file(
                    filename=fn,
                    target_patient_id=None,
                    batch_id="batch_test",
                    include_clinical=True,
                )
                self.assertFalse(res["already_queued"])
                self.assertEqual(len(res["jobs"]), 2)

            # Claim 3 jobs sequentially -> all 3 must be WAVE1_ADMIN
            claimed_wave1 = []
            for _ in range(3):
                job = broker.claim_next_ready_job(worker_id="w1")
                self.assertIsNotNone(job)
                self.assertEqual(job["job_type"], JobType.WAVE1_ADMIN.value)
                self.assertEqual(job["priority"], JobPriority.WAVE1_ADMIN_IMPORT)
                claimed_wave1.append(job)

            # Before WAVE1 jobs complete, no WAVE2 job can be claimed
            self.assertIsNone(broker.claim_next_ready_job(worker_id="w1"))

            # Complete WAVE1 for rcp1.pdf -> now WAVE2 for rcp1.pdf becomes ready and lease slot frees up
            broker.complete_job(
                job_id=claimed_wave1[0]["job_id"],
                filename="rcp1.pdf",
                lease_id=claimed_wave1[0]["lease_id"],
            )
            next_job = broker.claim_next_ready_job(worker_id="w1")
            self.assertIsNotNone(next_job)
            self.assertEqual(next_job["filename"], "rcp1.pdf")
            self.assertEqual(next_job["job_type"], JobType.WAVE2_CLINICAL.value)
        finally:
            broker.close()

    def test_strict_deduplication_on_import_and_rerun(self):
        """
        A file with an active job in the queue must never be queued a second time.
        """
        broker = self._make_broker()
        try:
            first = broker.enqueue_import_file(
                filename="dup.pdf",
                target_patient_id=None,
                batch_id="b1",
                include_clinical=True,
            )
            self.assertFalse(first["already_queued"])

            # Attempting to re-import the same file while PENDING must be rejected
            second = broker.enqueue_import_file(
                filename="dup.pdf",
                target_patient_id=None,
                batch_id="b2",
                include_clinical=True,
            )
            self.assertTrue(second["already_queued"])

            # Attempting a full rerun or single section rerun while full import is pending must also be rejected
            rerun_full = broker.enqueue_rcp_rerun(filename="dup.pdf", model_name=None)
            self.assertTrue(rerun_full["already_queued"])

            rerun_sec = broker.enqueue_rcp_rerun(
                filename="dup.pdf", model_name="ExpertAnswer"
            )
            self.assertTrue(rerun_sec["already_queued"])

            # Once jobs are cleaned, single-section rerun can be queued, but not duplicated for the same section
            broker.clean_queue(mode="all")
            sec1 = broker.enqueue_rcp_rerun(
                filename="dup.pdf", model_name="ExpertAnswer"
            )
            self.assertFalse(sec1["already_queued"])
            sec1_dup = broker.enqueue_rcp_rerun(
                filename="dup.pdf", model_name="ExpertAnswer"
            )
            self.assertTrue(sec1_dup["already_queued"])

            # Another distinct section on the same file can still be queued
            sec2 = broker.enqueue_rcp_rerun(
                filename="dup.pdf", model_name="MTDCompleted"
            )
            self.assertFalse(sec2["already_queued"])
        finally:
            broker.close()

    def test_cross_domain_gpu_lease_respects_batch_size(self):
        """
        With batch_size=1 (L4 24GB), if oncology worker holds a lease in the shared SQLite WAL db,
        sma worker cannot acquire one until oncology releases it or admin force-unlocks it.
        """
        broker_onco = self._make_broker(
            domain="oncology", batch_size=1, global_gpu_lock=True
        )
        broker_sma = self._make_broker(domain="sma", batch_size=1, global_gpu_lock=True)
        broker_sma_a100 = self._make_broker(
            domain="sma", batch_size=2, global_gpu_lock=True
        )
        try:
            lease1 = broker_onco.acquire_gpu_lease(
                worker_id="worker-onco",
                job_id="job-onco-1",
                filename="onco.pdf",
                job_type=JobType.WAVE1_ADMIN.value,
            )
            self.assertIsNotNone(lease1)

            # Second worker on SMA domain tries to acquire lease with batch_size=1 -> blocked
            lease2 = broker_sma.acquire_gpu_lease(
                worker_id="worker-sma",
                job_id="job-sma-1",
                filename="sma.pdf",
                job_type=JobType.WAVE1_ADMIN.value,
            )
            self.assertIsNone(lease2)

            # If batch_size=2 (e.g. A100 80GB), second worker can acquire a lease
            lease2_a100 = broker_sma_a100.acquire_gpu_lease(
                worker_id="worker-sma",
                job_id="job-sma-1",
                filename="sma.pdf",
                job_type=JobType.WAVE1_ADMIN.value,
            )
            self.assertIsNotNone(lease2_a100)

            # Admin force-unlocks all leases
            removed = broker_onco.release_gpu_lease(force_all=True)
            self.assertEqual(removed, 2)
            self.assertEqual(len(broker_onco.get_all_gpu_leases()), 0)
        finally:
            broker_onco.close()
            broker_sma.close()
            broker_sma_a100.close()

    def test_admin_clean_queue_modes(self):
        """
        Verify admin clean_queue modes: completed, reset_stuck, retry_failed, pending, all.
        """
        broker = self._make_broker(batch_size=2)
        try:
            broker.enqueue_import_file("f1.pdf", include_clinical=False)
            broker.enqueue_import_file("f2.pdf", include_clinical=False)

            job1 = broker.claim_next_ready_job("w1")
            self.assertIsNotNone(job1)
            self.assertEqual(len(broker.get_all_gpu_leases()), 1)

            # reset_stuck puts PROCESSING job back to PENDING and releases locks
            res_stuck = broker.clean_queue(mode="reset_stuck")
            self.assertEqual(res_stuck["affected_jobs"], 1)
            self.assertEqual(len(broker.get_all_gpu_leases()), 0)

            # Force fail job1, then retry_failed
            job1_again = broker.claim_next_ready_job("w1")
            broker.fail_job(
                job_id=job1_again["job_id"],
                filename="f1.pdf",
                error_message="GPU timeout",
                lease_id=job1_again["lease_id"],
                force_fail=True,
            )
            stats = broker.get_queue_stats()
            self.assertEqual(stats["failed"], 1)

            res_retry = broker.clean_queue(mode="retry_failed")
            self.assertEqual(res_retry["affected_jobs"], 1)
            self.assertEqual(broker.get_queue_stats()["pending"], 2)

            # Complete one job and purge completed
            j_comp = broker.claim_next_ready_job("w1")
            broker.complete_job(
                job_id=j_comp["job_id"],
                filename=j_comp["filename"],
                lease_id=j_comp["lease_id"],
            )
            self.assertEqual(broker.get_queue_stats()["completed"], 1)
            res_comp = broker.clean_queue(mode="completed")
            self.assertEqual(res_comp["affected_jobs"], 1)

            # Clean all
            res_all = broker.clean_queue(mode="all")
            self.assertGreaterEqual(res_all["affected_jobs"], 1)
            self.assertEqual(broker.get_queue_stats()["pending"], 0)
        finally:
            broker.close()

    def test_cards_visibility_and_progressive_wave2_saving(self):
        """
        - PENDING_ADMIN / PROCESSING_ADMIN files are hidden from cards.py.
        - PENDING_CLINICAL / PROCESSING_CLINICAL files are visible in cards.py without a false 'no data' missing warning.
        - DomainQueueWorker saves each clinical model progressively (upsert=True).
        """
        doc_pending_admin = {
            "file": "new_upload.pdf",
            "processing_status": RCPProcessingStatus.PENDING_ADMIN.value,
        }
        doc_proc_admin = {
            "file": "scanning_admin.pdf",
            "processing_status": RCPProcessingStatus.PROCESSING_ADMIN.value,
        }
        doc_pending_clinical = {
            "file": "step1_done.pdf",
            "patient_id": "dupont_jean_1960_01_01",
            "ui_date": datetime(2026, 5, 10),
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_birth": datetime(1960, 1, 1),
                "date_rcp": datetime(2026, 5, 10),
            },
            "processing_status": RCPProcessingStatus.PENDING_CLINICAL.value,
        }

        self.assertFalse(is_rcp_visible_in_cards(doc_pending_admin))
        self.assertFalse(is_rcp_visible_in_cards(doc_proc_admin))
        self.assertTrue(is_rcp_visible_in_cards(doc_pending_clinical))

        metrics = extract_card_metrics(doc_pending_clinical)
        self.assertEqual(metrics["patient"], "Jean Dupont")
        self.assertEqual(metrics["missing"], [])
        self.assertEqual(
            metrics["processing_status"],
            RCPProcessingStatus.PENDING_CLINICAL.value,
        )

        # Progressive Wave 2 execution test
        broker = self._make_broker()
        try:
            wave2_job = QueueJob(
                filename="step1_done.pdf",
                domain="oncology",
                job_type=JobType.WAVE2_CLINICAL,
                priority=JobPriority.WAVE2_CLINICAL_IMPORT,
                status=JobStatus.PROCESSING,
            )
            job_dict = broker._insert_job(wave2_job)
        finally:
            broker.close()

        class ModelA:
            """Rubrique Clinique A"""

        class ModelB:
            """Rubrique Clinique B"""

        call_log = []

        class FakeReader:
            def __init__(self, config, document):
                self.document = document
                self.basemodel_list = [ModelA, ModelB]
                self.mtd_datas = {"patient_id": "dupont_jean_1960_01_01"}

            def read_model(self, model_cls, upsert=False):
                call_log.append((model_cls.__name__, upsert))

        with patch("src.application.queue_worker.PatientMDTForm", FakeReader):
            worker = DomainQueueWorker(self.config, worker_id="test-worker")
            ok = worker.process_single_job(job_dict)
            self.assertTrue(ok)

        self.assertEqual(call_log, [("ModelA", True), ("ModelB", True)])

        broker_check = self._make_broker()
        try:
            finished_job = broker_check.get_job(wave2_job.job_id)
            self.assertIsNotNone(finished_job)
            self.assertEqual(finished_job["status"], JobStatus.COMPLETED.value)
            self.assertEqual(finished_job["completed_models"], ["ModelA", "ModelB"])
            self.assertEqual(finished_job["progress_pct"], 100.0)
        finally:
            broker_check.close()

    def test_no_streamlit_imports_outside_ui(self):
        """
        CRITICAL ARCHITECTURAL RULE: No file under src/application/, src/domain/,
        src/infrastructure/, or src/routers/ may import streamlit.
        """
        src_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
        forbidden_imports = []
        for root, _, files in os.walk(src_root):
            rel_dir = os.path.relpath(root, src_root)
            if rel_dir == "ui" or rel_dir.startswith(f"ui{os.sep}"):
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full_path = os.path.join(root, fn)
                with open(full_path, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=full_path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "streamlit" or alias.name.startswith(
                                "streamlit."
                            ):
                                forbidden_imports.append(full_path)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and (
                            node.module == "streamlit"
                            or node.module.startswith("streamlit.")
                        ):
                            forbidden_imports.append(full_path)

        self.assertEqual(
            forbidden_imports,
            [],
            f"Forbidden streamlit imports outside src/ui/: {forbidden_imports}",
        )


if __name__ == "__main__":
    unittest.main()
