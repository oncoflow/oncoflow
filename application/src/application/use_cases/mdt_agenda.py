"""Application use-case service orchestrating the Next MDT Agenda lifecycle and scheduling."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from src.application.config import AppConfig
from src.application.use_cases.patient_record import PatientRecordService
from src.domain.agents import get_domain_agents
from src.domain.mdt_agenda import (
    MDTAgenda,
    MDTAgendaCandidateSnapshot,
    MDTAgendaScheduler,
    MDTAgendaSortStrategy,
    map_urgency_score_to_priority_level,
)
from src.domain.repositories import MDTAgendaRepository
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.documents.repositories import MongoMDTAgendaRepository


class MDTAgendaService:
    """
    Application use-case service managing the single active Next MDT Agenda per domain,
    hydrating patient clinical metrics from `PatientRecordService`, and invoking `MDTAgendaScheduler`.
    """

    def __init__(
        self,
        agenda_repo: MDTAgendaRepository,
        patient_record_service: PatientRecordService,
        domain: str = "oncology",
        available_experts: list[str] | None = None,
    ) -> None:
        self.agenda_repo = agenda_repo
        self.patient_record_service = patient_record_service
        self.domain = (domain or "oncology").strip().lower()
        if available_experts is not None:
            self.available_experts = list(dict.fromkeys(available_experts))
        else:
            agents_obj = get_domain_agents(self.domain)
            self.available_experts = [
                str(getattr(ag, "agent_name", ""))
                for ag in getattr(agents_obj, "expert_agents", [])
                if getattr(ag, "agent_name", None)
            ]

    @classmethod
    def from_config(
        cls,
        config: AppConfig,
        db_client: Mongodb | None = None,
    ) -> "MDTAgendaService":
        """Build a domain-scoped `MDTAgendaService` backed by MongoDB adapters."""
        client = db_client or Mongodb(config)
        record_service = PatientRecordService.from_config(config, db_client=client)
        agenda_repo = MongoMDTAgendaRepository(
            config, db_client=client, domain=config.domain
        )
        return cls(
            agenda_repo=agenda_repo,
            patient_record_service=record_service,
            domain=config.domain,
        )

    def _get_or_init_agenda(
        self,
        ordered_snapshots: list[MDTAgendaCandidateSnapshot] | None = None,
    ) -> MDTAgenda:
        """
        Retrieve the persisted `MDTAgenda` or initialize and persist a default one
        with all domain patients enrolled by default.
        """
        agenda = self.agenda_repo.get_active()
        if agenda is None:
            agenda = MDTAgenda.create_default(
                domain=self.domain,
                available_experts=self.available_experts,
            )
            if ordered_snapshots is None:
                _, ordered_snapshots = self._collect_snapshots()
            for snap in ordered_snapshots:
                agenda.add_or_update_patient(
                    patient_id=snap.patient_id,
                    filename=snap.filename,
                )
            return self.agenda_repo.save(agenda)
        valid_set = set(self.available_experts)
        if valid_set:
            filtered = [e for e in agenda.attending_experts if e in valid_set]
            agenda.attending_experts = filtered
        return agenda

    def _collect_snapshots(
        self,
    ) -> tuple[dict[str, MDTAgendaCandidateSnapshot], list[MDTAgendaCandidateSnapshot]]:
        """Convert `PatientRecordService.list_patient_cards()` into `MDTAgendaCandidateSnapshot` objects."""
        cards = self.patient_record_service.list_patient_cards()
        by_id: dict[str, MDTAgendaCandidateSnapshot] = {}
        ordered_list: list[MDTAgendaCandidateSnapshot] = []

        for card in cards:
            pid = str(card.get("patient_id") or "").strip()
            if not pid:
                continue
            urgency_score = int(card.get("urgency_score") or 0)
            missing_list = [str(m) for m in (card.get("missing") or []) if m]
            is_comp_raw = card.get("is_complete")
            is_complete = (
                bool(is_comp_raw)
                if is_comp_raw is not None
                else (len(missing_list) == 0)
            )
            fname = str(card.get("latest_file") or card.get("file") or "")
            snap = MDTAgendaCandidateSnapshot(
                patient_id=pid,
                filename=fname,
                patient_name=str(card.get("patient") or "Inconnu"),
                first_name=card.get("first_name"),
                last_name=card.get("last_name"),
                date_birth=card.get("date_birth"),
                urgency=str(card.get("urgency") or "Indéfini"),
                urgency_score=urgency_score,
                priority_level=map_urgency_score_to_priority_level(urgency_score),
                is_complete=is_complete,
                missing_count=len(missing_list),
                missing_items=missing_list,
                care_adaptation_suggested=card.get("care_adaptation_suggested"),
                proposed_care_type=card.get("proposed_care_type"),
                required_experts=[str(e) for e in (card.get("experts") or []) if e],
                mdt_date=card.get("date"),
            )
            by_id[pid] = snap
            ordered_list.append(snap)

        ordered_list.sort(
            key=lambda s: (
                -s.urgency_score,
                0 if s.is_complete else 1,
                -(1 if s.care_adaptation_suggested else 0),
                s.patient_name.lower(),
            )
        )
        return by_id, ordered_list

    def _build_detail_payload(
        self,
        agenda: MDTAgenda,
        snapshots_by_id: dict[str, MDTAgendaCandidateSnapshot] | None = None,
        ordered_snapshots: list[MDTAgendaCandidateSnapshot] | None = None,
    ) -> dict[str, Any]:
        """Build the complete `MDTAgendaDetailResponse`-compatible dictionary."""
        if snapshots_by_id is None or ordered_snapshots is None:
            snapshots_by_id, ordered_snapshots = self._collect_snapshots()

        valid_entries = [e for e in agenda.entries if e.patient_id in snapshots_by_id]
        if len(valid_entries) != len(agenda.entries):
            agenda.entries = valid_entries
            agenda.normalize_manual_order()

        schedule_res = MDTAgendaScheduler.schedule(
            agenda=agenda,
            snapshots_by_patient=snapshots_by_id,
            available_experts=self.available_experts,
        )
        enrolled_ids = {item.patient_id for item in schedule_res.items}
        candidates = [
            snap.model_dump(mode="python")
            for snap in ordered_snapshots
            if snap.patient_id not in enrolled_ids
        ]

        return {
            "agenda_id": agenda.agenda_id,
            "domain": agenda.domain,
            "session_date": agenda.session_date,
            "sort_strategy": agenda.sort_strategy,
            "defer_incomplete_files": agenda.defer_incomplete_files,
            "available_experts": list(self.available_experts),
            "attending_experts": list(agenda.attending_experts),
            "total_enrolled": schedule_res.total_enrolled,
            "urgent_count": schedule_res.urgent_count,
            "incomplete_count": schedule_res.incomplete_count,
            "quorum_warning_count": schedule_res.quorum_warning_count,
            "items": [item.model_dump(mode="python") for item in schedule_res.items],
            "expert_windows": [
                w.model_dump(mode="python") for w in schedule_res.expert_windows
            ],
            "candidates": candidates,
            "updated_at": agenda.updated_at,
        }

    def get_agenda_detail(self) -> dict[str, Any]:
        """Return the current Next MDT Agenda detail, scheduled items, expert windows, and candidate pool."""
        snapshots_by_id, ordered_snapshots = self._collect_snapshots()
        agenda = self._get_or_init_agenda(ordered_snapshots=ordered_snapshots)
        return self._build_detail_payload(agenda, snapshots_by_id, ordered_snapshots)

    def update_options(
        self,
        *,
        session_date: date | str | None = None,
        clear_session_date: bool = False,
        sort_strategy: MDTAgendaSortStrategy | str | None = None,
        defer_incomplete_files: bool | None = None,
        attending_experts: list[str] | None = None,
        toggle_expert: str | None = None,
        patient_ids: list[str] | None = None,
        reset_enrolled_patients: bool = False,
    ) -> dict[str, Any]:
        """Update session date, sort strategy, attending experts, or re-initialize enrolled patients for a new meeting."""
        snapshots_by_id, ordered_snapshots = self._collect_snapshots()
        agenda = self._get_or_init_agenda(ordered_snapshots=ordered_snapshots)

        if clear_session_date:
            agenda.session_date = None
        elif session_date is not None:
            parsed_date = MDTAgenda._parse_session_date(session_date)
            if parsed_date is None and str(session_date).strip():
                raise ValueError(f"Invalid session_date format: '{session_date}'.")
            agenda.session_date = parsed_date

        if sort_strategy is not None:
            resolved_strategy = (
                sort_strategy
                if isinstance(sort_strategy, MDTAgendaSortStrategy)
                else MDTAgendaSortStrategy(str(sort_strategy).strip().lower())
            )
            agenda.sort_strategy = resolved_strategy

        if defer_incomplete_files is not None:
            agenda.defer_incomplete_files = bool(defer_incomplete_files)

        if attending_experts is not None:
            agenda.set_attending_experts(attending_experts, self.available_experts)

        if toggle_expert:
            agenda.toggle_attending_expert(toggle_expert, self.available_experts)

        if reset_enrolled_patients or patient_ids is not None:
            agenda.clear_patients()
            target_ids = (
                [pid.strip() for pid in patient_ids if pid and pid.strip()]
                if patient_ids is not None
                else [s.patient_id for s in ordered_snapshots]
            )
            for pid in target_ids:
                snap = snapshots_by_id.get(pid)
                if snap is not None:
                    agenda.add_or_update_patient(patient_id=pid, filename=snap.filename)

        saved = self.agenda_repo.save(agenda)
        return self._build_detail_payload(saved, snapshots_by_id, ordered_snapshots)

    def add_patients(
        self,
        patient_ids: list[str] | None = None,
        patient_id: str | None = None,
        add_all_candidates: bool = False,
        enroll_all_candidates: bool = False,
        filter_mode: Literal["all", "complete", "urgent"] | None = "all",
    ) -> dict[str, Any]:
        """Enroll one, several, or filtered candidate patients into the Next MDT Agenda."""
        agenda = self._get_or_init_agenda()
        snapshots_by_id, ordered_snapshots = self._collect_snapshots()

        should_enroll_all = bool(add_all_candidates or enroll_all_candidates)
        resolved_mode = (filter_mode or "all").strip().lower()

        if should_enroll_all:
            if resolved_mode == "complete":
                target_ids = [s.patient_id for s in ordered_snapshots if s.is_complete]
            elif resolved_mode == "urgent":
                target_ids = [
                    s.patient_id for s in ordered_snapshots if s.urgency_score >= 2
                ]
            else:
                target_ids = [s.patient_id for s in ordered_snapshots]
        else:
            raw_ids = list(patient_ids or [])
            if patient_id and patient_id.strip():
                raw_ids.append(patient_id.strip())
            target_ids = [pid.strip() for pid in raw_ids if pid and pid.strip()]

        for pid in target_ids:
            snap = snapshots_by_id.get(pid)
            if snap is None:
                continue
            agenda.add_or_update_patient(patient_id=pid, filename=snap.filename)

        saved = self.agenda_repo.save(agenda)
        return self._build_detail_payload(saved, snapshots_by_id, ordered_snapshots)

    def remove_patient(self, patient_id: str) -> dict[str, Any]:
        """Remove an enrolled patient from the Next MDT Agenda."""
        agenda = self._get_or_init_agenda()
        agenda.remove_patient(patient_id)
        saved = self.agenda_repo.save(agenda)
        return self._build_detail_payload(saved)

    def clear_patients(self) -> dict[str, Any]:
        """Clear all enrolled patients from the Next MDT Agenda."""
        agenda = self._get_or_init_agenda()
        agenda.clear_patients()
        saved = self.agenda_repo.save(agenda)
        return self._build_detail_payload(saved)

    def move_patient(
        self,
        patient_id: str,
        *,
        direction: Literal["up", "down"] | None = None,
        target_position: int | None = None,
        pinned: bool | None = None,
    ) -> dict[str, Any]:
        """Move an enrolled patient up/down or pin/unpin their scheduled position."""
        agenda = self._get_or_init_agenda()
        snapshots_by_id, ordered_snapshots = self._collect_snapshots()

        entry_map = {e.patient_id: e for e in agenda.entries}
        if patient_id not in entry_map:
            raise KeyError(f"Patient '{patient_id}' is not enrolled in the agenda.")

        current_schedule = MDTAgendaScheduler.schedule(
            agenda=agenda,
            snapshots_by_patient=snapshots_by_id,
            available_experts=self.available_experts,
        )
        current_order_ids = [item.patient_id for item in current_schedule.items]
        if patient_id not in current_order_ids:
            raise KeyError(f"Patient '{patient_id}' is not enrolled in the agenda.")

        total_n = len(current_order_ids)
        curr_idx = current_order_ids.index(patient_id)
        curr_pos = curr_idx + 1
        target_entry = entry_map[patient_id]

        if pinned is False and direction is None and target_position is None:
            target_entry.pinned = False
            target_entry.pinned_position = None
            saved = self.agenda_repo.save(agenda)
            return self._build_detail_payload(saved, snapshots_by_id, ordered_snapshots)

        new_pos = curr_pos
        if direction == "up":
            new_pos = max(1, curr_pos - 1)
        elif direction == "down":
            new_pos = min(total_n, curr_pos + 1)
        elif target_position is not None:
            new_pos = min(max(1, int(target_position)), total_n)

        if direction in ("up", "down") or target_position is not None:
            reordered_ids = list(current_order_ids)
            reordered_ids.pop(curr_idx)
            reordered_ids.insert(new_pos - 1, patient_id)

            new_entries: list = []
            for idx, pid in enumerate(reordered_ids):
                e = entry_map[pid]
                e.manual_order = idx
                if pid == patient_id:
                    e.pinned = True if pinned is None else bool(pinned)
                    e.pinned_position = new_pos if e.pinned else None
                elif e.pinned and e.pinned_position == new_pos:
                    e.pinned_position = curr_pos
                new_entries.append(e)
            agenda.entries = new_entries
        elif pinned is True:
            target_entry.pinned = True
            target_entry.pinned_position = new_pos

        saved = self.agenda_repo.save(agenda)
        return self._build_detail_payload(saved, snapshots_by_id, ordered_snapshots)

    def reorder_patients(
        self,
        patient_ids: list[str],
        switch_to_manual: bool = True,
    ) -> dict[str, Any]:
        """Explicitly reorder enrolled patients and optionally switch strategy to `manual`."""
        agenda = self._get_or_init_agenda()
        agenda.reorder_patients(patient_ids, switch_to_manual=switch_to_manual)
        saved = self.agenda_repo.save(agenda)
        return self._build_detail_payload(saved)
