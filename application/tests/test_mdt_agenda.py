"""Unit and API contract tests for the Next MDT Agenda domain scheduler, use cases, and router."""

from datetime import date, datetime
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.use_cases.mdt_agenda import MDTAgendaService
from src.application.use_cases.patient_record import PatientRecordService
from src.domain.mdt_agenda import (
    MDTAgenda,
    MDTAgendaCandidateSnapshot,
    MDTAgendaEntry,
    MDTAgendaScheduler,
    MDTAgendaSortStrategy,
)
from src.domain.repositories import MDTAgendaRepository
from src.infrastructure.documents.repositories import (
    InMemoryMDTAgendaRepository,
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
)
from src.routers.mdt_agenda import get_mdt_agenda_service

APP_API_PATH = Path(__file__).resolve().parent.parent / "app-api.py"


def _make_snapshot(
    patient_id: str,
    patient_name: str,
    urgency_score: int = 0,
    required_experts: list[str] | None = None,
    is_complete: bool = True,
    missing_items: list[str] | None = None,
    care_adaptation_suggested: bool = False,
) -> MDTAgendaCandidateSnapshot:
    urgency_map = {2: "Urgent", 1: "Semi-urgent", 0: "Standard"}
    prio_map = {2: "high", 1: "medium", 0: "low"}
    missing = list(missing_items or ([] if is_complete else ["IRM hépatique"]))
    return MDTAgendaCandidateSnapshot(
        patient_id=patient_id,
        filename=f"{patient_id}.pdf",
        patient_name=patient_name,
        first_name=patient_name.split()[0],
        last_name=patient_name.split()[-1],
        urgency=urgency_map.get(urgency_score, "Standard"),
        urgency_score=urgency_score,
        priority_level=prio_map.get(urgency_score, "low"),  # type: ignore[arg-type]
        is_complete=is_complete,
        missing_count=len(missing),
        missing_items=missing,
        care_adaptation_suggested=care_adaptation_suggested,
        required_experts=list(required_experts or []),
    )


class TestMDTAgendaDomainAndScheduler:
    """Test pure domain scheduling strategies, expert windows, and quorum alerts."""

    def test_in_memory_repository_satisfies_protocol(self):
        repo = InMemoryMDTAgendaRepository(domain="oncology")
        assert isinstance(repo, MDTAgendaRepository)

    def test_hybrid_strategy_prioritizes_urgent_then_expert_clusters_and_defers_incomplete(
        self,
    ):
        experts = ["pancreas expert", "oesophagus expert", "hepatocellular expert"]
        snapshots = {
            "p_std_panc_1": _make_snapshot(
                "p_std_panc_1",
                "Alice StandardPanc1",
                urgency_score=0,
                required_experts=["pancreas expert"],
            ),
            "p_semi_oeso": _make_snapshot(
                "p_semi_oeso",
                "Bruno SemiOeso",
                urgency_score=1,
                required_experts=["oesophagus expert"],
                care_adaptation_suggested=True,
            ),
            "p_urg_panc": _make_snapshot(
                "p_urg_panc",
                "Claire UrgentPanc",
                urgency_score=2,
                required_experts=["pancreas expert"],
                care_adaptation_suggested=True,
            ),
            "p_std_panc_2": _make_snapshot(
                "p_std_panc_2",
                "David StandardPanc2",
                urgency_score=1,
                required_experts=["pancreas expert"],
            ),
            "p_incomp_urg": _make_snapshot(
                "p_incomp_urg",
                "Eva IncompleteUrgent",
                urgency_score=2,
                required_experts=["pancreas expert"],
                is_complete=False,
                missing_items=["Biopsie", "Scanner"],
            ),
        }

        agenda = MDTAgenda(
            agenda_id="next_mdt_oncology",
            domain="oncology",
            session_date=date(2026, 11, 15),
            sort_strategy=MDTAgendaSortStrategy.HYBRID,
            defer_incomplete_files=True,
            attending_experts=experts,
            entries=[
                MDTAgendaEntry(patient_id=pid, filename=f"{pid}.pdf", manual_order=i)
                for i, pid in enumerate(snapshots.keys())
            ],
        )

        res = MDTAgendaScheduler.schedule(
            agenda=agenda,
            snapshots_by_patient=snapshots,
            available_experts=experts,
        )

        ordered_ids = [item.patient_id for item in res.items]
        # 1. Complete Urgent first: p_urg_panc
        assert ordered_ids[0] == "p_urg_panc"
        # 2. Chained pancreas cluster (p_std_panc_2, p_std_panc_1) stays contiguous right after p_urg_panc!
        assert ordered_ids[1:3] == ["p_std_panc_2", "p_std_panc_1"]
        # 3. Oesophagus cluster next
        assert ordered_ids[3] == "p_semi_oeso"
        # 4. Incomplete file deferred to the end despite urgency_score=2
        assert ordered_ids[4] == "p_incomp_urg"
        assert "Relégué en fin de séance" in res.items[4].rank_reason

        # Check pancreas expert window (#1..#3 for complete cases, plus #5 incomplete)
        panc_win = next(
            w for w in res.expert_windows if w.expert_name == "pancreas expert"
        )
        assert panc_win.case_count == 4
        assert panc_win.urgent_case_count == 2
        assert panc_win.first_position == 1

    def test_expert_grouping_strategy_groups_all_specialist_cases_across_urgency_tiers(
        self,
    ):
        experts = ["pancreas expert", "oesophagus expert"]
        snapshots = {
            "p_urg_oeso": _make_snapshot(
                "p_urg_oeso",
                "Patient UrgOeso",
                urgency_score=2,
                required_experts=["oesophagus expert"],
            ),
            "p_urg_panc": _make_snapshot(
                "p_urg_panc",
                "Patient UrgPanc",
                urgency_score=2,
                required_experts=["pancreas expert"],
            ),
            "p_std_oeso": _make_snapshot(
                "p_std_oeso",
                "Patient StdOeso",
                urgency_score=0,
                required_experts=["oesophagus expert"],
            ),
            "p_std_panc": _make_snapshot(
                "p_std_panc",
                "Patient StdPanc",
                urgency_score=0,
                required_experts=["pancreas expert"],
            ),
        }
        agenda = MDTAgenda(
            agenda_id="next_mdt_oncology",
            domain="oncology",
            sort_strategy=MDTAgendaSortStrategy.EXPERT_GROUPING,
            defer_incomplete_files=True,
            attending_experts=experts,
            entries=[
                MDTAgendaEntry(patient_id=pid, filename=f"{pid}.pdf", manual_order=i)
                for i, pid in enumerate(snapshots.keys())
            ],
        )

        res = MDTAgendaScheduler.schedule(
            agenda=agenda,
            snapshots_by_patient=snapshots,
            available_experts=experts,
        )
        # Both oesophagus cases are contiguous, and both pancreas cases are contiguous
        for win in res.expert_windows:
            assert win.is_contiguous is True
            assert (win.last_position - win.first_position + 1) == win.case_count  # type: ignore[operator]

    def test_attending_experts_quorum_detection(self):
        experts = ["pancreas expert", "hepatocellular expert"]
        snapshots = {
            "p_needs_both": _make_snapshot(
                "p_needs_both",
                "Jean QuorumMissing",
                urgency_score=2,
                required_experts=["pancreas expert", "hepatocellular expert"],
            ),
            "p_needs_panc": _make_snapshot(
                "p_needs_panc",
                "Marie QuorumFull",
                urgency_score=2,
                required_experts=["pancreas expert"],
            ),
        }
        agenda = MDTAgenda(
            agenda_id="next_mdt_oncology",
            domain="oncology",
            sort_strategy=MDTAgendaSortStrategy.URGENCY_FIRST,
            # hepatocellular expert is absent
            attending_experts=["pancreas expert"],
            entries=[
                MDTAgendaEntry(
                    patient_id="p_needs_both", filename="a.pdf", manual_order=0
                ),
                MDTAgendaEntry(
                    patient_id="p_needs_panc", filename="b.pdf", manual_order=1
                ),
            ],
        )

        res = MDTAgendaScheduler.schedule(
            agenda=agenda,
            snapshots_by_patient=snapshots,
            available_experts=experts,
        )
        assert res.quorum_warning_count == 1
        # Full quorum case is scheduled before the case missing a required expert
        assert res.items[0].patient_id == "p_needs_panc"
        assert res.items[0].quorum_met is True
        assert res.items[1].patient_id == "p_needs_both"
        assert res.items[1].quorum_met is False
        assert res.items[1].absent_required_experts == ["hepatocellular expert"]
        assert res.items[1].expert_coverage_ratio == 0.5
        assert "Quorum incomplet" in res.items[1].rank_reason


class TestMDTAgendaServiceAndRouter:
    """Test `MDTAgendaService` and `/api/v1/mdt-agenda` FastAPI endpoints."""

    def _build_seeded_service(self) -> MDTAgendaService:
        patient_repo = InMemoryPatientRepository()
        mdt_form_repo = InMemoryPatientMDTFormRepository()
        agenda_repo = InMemoryMDTAgendaRepository(domain="oncology")

        mock_conf = MagicMock()
        mock_conf.domain = "oncology"
        mock_conf.rcp.path = "/tmp"
        mock_conf.queue.enabled = False

        record_service = PatientRecordService(
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            config=mock_conf,
        )

        # Seed 3 patients
        patients_seed = [
            (
                "rcp_1.pdf",
                "Martin",
                "Dupont",
                datetime(1960, 4, 10),
                "Patient is not urgent",
                ["pancreas expert"],
                True,
                [],
            ),
            (
                "rcp_2.pdf",
                "Sophie",
                "Laurent",
                datetime(1972, 8, 22),
                "Patient must be treated urgently",
                ["pancreas expert"],
                True,
                [],
            ),
            (
                "rcp_3.pdf",
                "Paul",
                "Bernard",
                datetime(1955, 1, 5),
                "Patient must be treated as soon as possible",
                ["oesophagus expert"],
                False,
                ["Scanner thoracique"],
            ),
        ]
        for (
            fname,
            fn,
            ln,
            dob,
            prio,
            exps,
            is_comp,
            missing,
        ) in patients_seed:
            record_service.synchronize_patient_from_admin(
                filename=fname,
                admin_data={
                    "first_name": fn,
                    "last_name": ln,
                    "age": 65,
                    "date_birth": dob,
                    "date_rcp": datetime(2026, 10, 1),
                    "gender": "Male",
                },
            )
            mdt_form_repo.update_fields(
                fname,
                {
                    "ExpertAnswer": {
                        exp: {
                            "expert_relevant": True,
                            "patient_priority": prio,
                        }
                        for exp in exps
                    },
                    "MTDCompleted": {
                        "mtd_complete": {
                            "is_mtd_complete": is_comp,
                            "what_missing": missing,
                            "references": [],
                        }
                    },
                    "processing_status": "COMPLETED",
                },
            )

        return MDTAgendaService(
            agenda_repo=agenda_repo,
            patient_record_service=record_service,
            domain="oncology",
        )

    def test_api_mdt_agenda_full_lifecycle(self):
        spec = importlib.util.spec_from_file_location("app_api", APP_API_PATH)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        app = module.app

        service = self._build_seeded_service()
        app.dependency_overrides[get_mdt_agenda_service] = lambda: service
        try:
            client = TestClient(app)

            # 1. GET initial agenda -> all 3 patients are enrolled by default, defer_incomplete_files is False
            r_get = client.get("/api/v1/mdt-agenda?domain=oncology")
            assert r_get.status_code == 200
            data = r_get.json()
            assert data["agenda_id"] == "next_mdt_oncology"
            assert data["defer_incomplete_files"] is False
            assert data["total_enrolled"] == 3
            assert len(data["candidates"]) == 0

            # Clear patients to test filtered batch enrollment
            r_clear_init = client.delete("/api/v1/mdt-agenda/patients?domain=oncology")
            assert r_clear_init.status_code == 200
            assert r_clear_init.json()["total_enrolled"] == 0
            assert len(r_clear_init.json()["candidates"]) == 3

            # 2a. Test enroll_all_candidates with filter_mode="urgent" -> only Sophie Laurent
            r_add_urg = client.post(
                "/api/v1/mdt-agenda/patients?domain=oncology",
                json={"enroll_all_candidates": True, "filter_mode": "urgent"},
            )
            assert r_add_urg.status_code == 200
            assert r_add_urg.json()["total_enrolled"] == 1
            assert r_add_urg.json()["items"][0]["patient_name"] == "Sophie Laurent"

            # 2b. Test enroll_all_candidates with filter_mode="complete" -> Sophie + Martin (2 complete)
            r_add_comp = client.post(
                "/api/v1/mdt-agenda/patients?domain=oncology",
                json={"enroll_all_candidates": True, "filter_mode": "complete"},
            )
            assert r_add_comp.status_code == 200
            assert r_add_comp.json()["total_enrolled"] == 2

            # 2c. POST /patients with add_all_candidates=True (all 3)
            r_add = client.post(
                "/api/v1/mdt-agenda/patients?domain=oncology",
                json={"add_all_candidates": True},
            )
            assert r_add.status_code == 200
            added = r_add.json()
            assert added["total_enrolled"] == 3
            assert len(added["candidates"]) == 0
            # With hybrid strategy and defer_incomplete_files=False:
            # 1. Urgent (Sophie Laurent, pancreas) is #1
            # 2. Chained pancreas cluster (Martin Dupont, pancreas) is #2
            # 3. Semi-urgent (Paul Bernard, oesophagus) is #3
            assert added["items"][0]["patient_name"] == "Sophie Laurent"
            assert added["items"][1]["patient_name"] == "Martin Dupont"
            assert added["items"][2]["patient_name"] == "Paul Bernard"

            # 3. Move Martin Dupont up to #1 -> pins Martin Dupont at position 1
            martin_id = added["items"][1]["patient_id"]
            r_move = client.post(
                f"/api/v1/mdt-agenda/patients/{martin_id}/move?domain=oncology",
                json={"direction": "up"},
            )
            assert r_move.status_code == 200
            moved = r_move.json()
            assert moved["items"][0]["patient_id"] == martin_id
            assert moved["items"][0]["pinned"] is True
            assert (
                "Position épinglée manuellement (#1)"
                in moved["items"][0]["rank_reason"]
            )

            # 4. Unpin Martin Dupont -> Sophie Laurent returns to #1
            r_unpin = client.post(
                f"/api/v1/mdt-agenda/patients/{martin_id}/move?domain=oncology",
                json={"pinned": False},
            )
            assert r_unpin.status_code == 200
            unpinned = r_unpin.json()
            assert unpinned["items"][0]["patient_name"] == "Sophie Laurent"
            assert unpinned["items"][1]["patient_id"] == martin_id
            assert unpinned["items"][1]["pinned"] is False

            # 5. PATCH options: toggle pancreas expert off -> quorum warnings increase
            r_patch = client.patch(
                "/api/v1/mdt-agenda?domain=oncology",
                json={
                    "session_date": "2026-12-01",
                    "sort_strategy": "urgency_first",
                    "defer_incomplete_files": False,
                    "toggle_expert": "pancreas expert",
                },
            )
            assert r_patch.status_code == 200
            patched = r_patch.json()
            assert patched["session_date"] == "2026-12-01"
            assert patched["sort_strategy"] == "urgency_first"
            assert patched["defer_incomplete_files"] is False
            assert "pancreas expert" not in patched["attending_experts"]
            assert patched["quorum_warning_count"] == 2

            # 6. PUT /reorder -> manual order
            ids_reversed = [i["patient_id"] for i in reversed(patched["items"])]
            r_reord = client.put(
                "/api/v1/mdt-agenda/reorder?domain=oncology",
                json={"patient_ids": ids_reversed, "switch_to_manual": True},
            )
            assert r_reord.status_code == 200
            reord = r_reord.json()
            assert reord["sort_strategy"] == "manual"
            assert [i["patient_id"] for i in reord["items"]] == ids_reversed

            # 7. DELETE single patient
            r_del_one = client.delete(
                f"/api/v1/mdt-agenda/patients/{martin_id}?domain=oncology"
            )
            assert r_del_one.status_code == 200
            assert r_del_one.json()["total_enrolled"] == 2
            assert len(r_del_one.json()["candidates"]) == 1

            # 8. Re-add single patient using patient_id field
            r_add_single = client.post(
                "/api/v1/mdt-agenda/patients?domain=oncology",
                json={"patient_id": martin_id},
            )
            assert r_add_single.status_code == 200
            assert r_add_single.json()["total_enrolled"] == 3

            # 9. DELETE all patients
            r_clear = client.delete("/api/v1/mdt-agenda/patients?domain=oncology")
            assert r_clear.status_code == 200
            assert r_clear.json()["total_enrolled"] == 0
            assert len(r_clear.json()["candidates"]) == 3
        finally:
            app.dependency_overrides.pop(get_mdt_agenda_service, None)
