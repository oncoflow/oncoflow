"""Pure domain models and deterministic scheduling policies for the Next MDT Agenda."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MDTAgendaSortStrategy(str, Enum):
    """Selectable organization and scheduling strategies for an MDT meeting agenda."""

    HYBRID = "hybrid"
    URGENCY_FIRST = "urgency_first"
    EXPERT_GROUPING = "expert_grouping"
    MANUAL = "manual"


PriorityLevelLiteral = Literal["high", "medium", "low"]


def map_urgency_score_to_priority_level(urgency_score: int) -> PriorityLevelLiteral:
    """Map numeric `urgency_score` (0..2) to canonical priority level (`high`, `medium`, `low`)."""
    if urgency_score >= 2:
        return "high"
    if urgency_score == 1:
        return "medium"
    return "low"


def _coerce_optional_date(val: Any) -> Optional[date]:
    """Coerce an optional date, datetime, or ISO date string into a `datetime.date`."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            try:
                return date.fromisoformat(s[:10])
            except ValueError:
                return None
    return None


class MDTAgendaEntry(BaseModel):
    """Enrolled patient entry inside an `MDTAgenda` aggregate."""

    patient_id: str = Field(description="Normalized identifier of the enrolled patient")
    filename: str = Field(
        default="",
        description="Target PatientMDTForm PDF filename selected for the MDT session",
    )
    pinned: bool = Field(
        default=False,
        description="Whether this patient is manually pinned to a fixed agenda position",
    )
    pinned_position: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-indexed pinned position when `pinned` is True",
    )
    manual_order: int = Field(
        default=0,
        ge=0,
        description="0-indexed manual ordering rank used by manual sort and tie-breaking",
    )


class MDTAgendaCandidateSnapshot(BaseModel):
    """Immutable snapshot of a patient's latest analyzed `PatientMDTForm` metrics for agenda scheduling."""

    model_config = ConfigDict(frozen=True)

    patient_id: str
    filename: str
    patient_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    urgency: str = "Indéfini"
    urgency_score: int = 0
    priority_level: PriorityLevelLiteral = "low"
    is_complete: bool = True
    missing_count: int = 0
    missing_items: list[str] = Field(default_factory=list)
    care_adaptation_suggested: Optional[bool] = None
    proposed_care_type: Optional[str] = None
    required_experts: list[str] = Field(default_factory=list)
    mdt_date: Optional[datetime] = None


class MDTAgendaScheduledItem(BaseModel):
    """Immutable scheduled patient item with computed position, quorum metrics, and ranking rationale."""

    model_config = ConfigDict(frozen=True)

    position: int = Field(ge=1, description="1-indexed scheduled passage position")
    patient_id: str
    filename: str
    patient_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_birth: Optional[datetime] = None
    urgency: str
    urgency_score: int
    priority_level: PriorityLevelLiteral
    is_complete: bool
    missing_count: int
    missing_items: list[str] = Field(default_factory=list)
    care_adaptation_suggested: Optional[bool] = None
    proposed_care_type: Optional[str] = None
    required_experts: list[str] = Field(default_factory=list)
    present_required_experts: list[str] = Field(default_factory=list)
    absent_required_experts: list[str] = Field(default_factory=list)
    quorum_met: bool = True
    expert_coverage_ratio: float = 1.0
    cluster_key: str = ""
    pinned: bool = False
    rank_reason: str = ""
    mdt_date: Optional[datetime] = None


class MDTExpertWindow(BaseModel):
    """Presence window summary for a domain specialist across the scheduled MDT agenda."""

    model_config = ConfigDict(frozen=True)

    expert_name: str
    is_attending: bool
    case_count: int = 0
    urgent_case_count: int = 0
    first_position: Optional[int] = None
    last_position: Optional[int] = None
    is_contiguous: bool = True
    patient_ids: list[str] = Field(default_factory=list)


class MDTAgendaScheduleResult(BaseModel):
    """Complete result of scheduling an `MDTAgenda`."""

    model_config = ConfigDict(frozen=True)

    items: list[MDTAgendaScheduledItem] = Field(default_factory=list)
    expert_windows: list[MDTExpertWindow] = Field(default_factory=list)
    total_enrolled: int = 0
    urgent_count: int = 0
    incomplete_count: int = 0
    quorum_warning_count: int = 0


class MDTAgenda(BaseModel):
    """
    Pure Domain Aggregate Root representing the active Next MDT Agenda for a medical domain.
    Contains zero I/O or infrastructure dependencies.
    """

    agenda_id: str = Field(
        description="Deterministic agenda identifier (e.g. next_mdt_oncology)"
    )
    domain: str = Field(description="Medical domain identifier (e.g. oncology, sma)")
    session_date: Optional[date] = Field(
        default=None, description="Selected date for the next MDT meeting"
    )
    sort_strategy: MDTAgendaSortStrategy = Field(
        default=MDTAgendaSortStrategy.HYBRID,
        description="Active scheduling and sorting strategy",
    )
    defer_incomplete_files: bool = Field(
        default=False,
        description="When True, unpinned incomplete files are deferred to the end of the session",
    )
    attending_experts: list[str] = Field(
        default_factory=list,
        description="List of domain expert names attending the MDT session",
    )
    entries: list[MDTAgendaEntry] = Field(
        default_factory=list,
        description="Enrolled patient entries for the session",
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last modification timestamp"
    )

    @field_validator("session_date", mode="before")
    @classmethod
    def _parse_session_date(cls, v: Any) -> Optional[date]:
        return _coerce_optional_date(v)

    @staticmethod
    def build_agenda_id(domain: str) -> str:
        """Build the canonical single-draft agenda ID for a medical domain."""
        clean = (domain or "oncology").strip().lower()
        return f"next_mdt_{clean}"

    @classmethod
    def create_default(
        cls, domain: str, available_experts: list[str] | None = None
    ) -> Self:
        """Create a fresh default `MDTAgenda` for `domain` with all domain experts attending."""
        clean_domain = (domain or "oncology").strip().lower()
        return cls(
            agenda_id=cls.build_agenda_id(clean_domain),
            domain=clean_domain,
            session_date=date.today(),
            sort_strategy=MDTAgendaSortStrategy.HYBRID,
            defer_incomplete_files=False,
            attending_experts=list(dict.fromkeys(available_experts or [])),
            entries=[],
            updated_at=datetime.now(),
        )

    def normalize_manual_order(self) -> None:
        """Normalize `manual_order` indices sequentially (0..N-1)."""
        for idx, entry in enumerate(self.entries):
            entry.manual_order = idx

    def add_or_update_patient(
        self, patient_id: str, filename: str = ""
    ) -> MDTAgendaEntry:
        """Enroll a patient in the agenda or update their selected `filename` if already enrolled."""
        pid = patient_id.strip()
        for existing in self.entries:
            if existing.patient_id == pid:
                if filename:
                    existing.filename = filename
                self.updated_at = datetime.now()
                return existing

        entry = MDTAgendaEntry(
            patient_id=pid,
            filename=filename,
            pinned=False,
            pinned_position=None,
            manual_order=len(self.entries),
        )
        self.entries.append(entry)
        self.updated_at = datetime.now()
        return entry

    def remove_patient(self, patient_id: str) -> bool:
        """Remove a patient from the agenda and normalize remaining positions."""
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.patient_id != patient_id]
        if len(self.entries) == before:
            return False
        self.normalize_manual_order()
        max_pos = len(self.entries)
        for e in self.entries:
            if (
                e.pinned
                and e.pinned_position is not None
                and e.pinned_position > max_pos
            ):
                e.pinned_position = max(1, max_pos)
        self.updated_at = datetime.now()
        return True

    def clear_patients(self) -> None:
        """Remove all enrolled patients from the agenda."""
        self.entries = []
        self.updated_at = datetime.now()

    def set_attending_experts(
        self, experts: list[str], available_experts: list[str]
    ) -> None:
        """Update the list of attending experts, preserving canonical domain expert ordering."""
        requested_set = {e.strip() for e in experts if e and e.strip()}
        valid_ordered = [e for e in available_experts if e in requested_set]
        for extra in experts:
            clean = extra.strip()
            if clean and clean not in valid_ordered and clean in requested_set:
                valid_ordered.append(clean)
        self.attending_experts = valid_ordered
        self.updated_at = datetime.now()

    def toggle_attending_expert(
        self, expert_name: str, available_experts: list[str]
    ) -> None:
        """Toggle a single specialist's attendance status in `attending_experts`."""
        target = expert_name.strip()
        if not target:
            return
        current = set(self.attending_experts)
        if target in current:
            current.remove(target)
        else:
            current.add(target)
        self.set_attending_experts(list(current), available_experts)

    def reorder_patients(
        self,
        patient_ids: list[str],
        switch_to_manual: bool = True,
    ) -> None:
        """Explicitly reorder enrolled entries according to `patient_ids`."""
        by_id = {e.patient_id: e for e in self.entries}
        reordered: list[MDTAgendaEntry] = []
        seen: set[str] = set()
        for pid in patient_ids:
            if pid in by_id and pid not in seen:
                reordered.append(by_id[pid])
                seen.add(pid)
        for e in self.entries:
            if e.patient_id not in seen:
                reordered.append(e)
                seen.add(e.patient_id)
        for idx, entry in enumerate(reordered):
            entry.manual_order = idx
            if switch_to_manual:
                entry.pinned = False
                entry.pinned_position = None
        self.entries = reordered
        if switch_to_manual:
            self.sort_strategy = MDTAgendaSortStrategy.MANUAL
        self.updated_at = datetime.now()

    @classmethod
    def from_persistence(cls, raw: dict[str, Any]) -> Self:
        """Hydrate an `MDTAgenda` aggregate from a persistence dictionary."""
        clean = {k: v for k, v in raw.items() if k != "_id"}
        return cls.model_validate(clean)

    def to_persistence(self) -> dict[str, Any]:
        """Serialize this `MDTAgenda` aggregate into a BSON-safe persistence dictionary."""
        return {
            "agenda_id": self.agenda_id,
            "domain": self.domain,
            "session_date": (
                self.session_date.isoformat() if self.session_date else None
            ),
            "sort_strategy": self.sort_strategy.value,
            "defer_incomplete_files": self.defer_incomplete_files,
            "attending_experts": list(self.attending_experts),
            "entries": [e.model_dump(mode="python") for e in self.entries],
            "updated_at": self.updated_at or datetime.now(),
        }


class _EnrichedCandidate:
    """Internal helper holding an entry, its clinical snapshot, and computed expert quorum metrics."""

    def __init__(
        self,
        entry: MDTAgendaEntry,
        snapshot: MDTAgendaCandidateSnapshot,
        attending_set: set[str],
        available_order: dict[str, int],
    ) -> None:
        self.entry = entry
        self.snapshot = snapshot
        req = list(dict.fromkeys(snapshot.required_experts))
        req.sort(key=lambda x: (available_order.get(x, 999), x))
        self.required_experts = req
        self.present_required_experts = [e for e in req if e in attending_set]
        self.absent_required_experts = [e for e in req if e not in attending_set]
        self.quorum_met = len(self.absent_required_experts) == 0
        self.expert_coverage_ratio = (
            round(len(self.present_required_experts) / len(req), 4) if req else 1.0
        )
        if self.present_required_experts:
            self.cluster_key = " + ".join(self.present_required_experts)
        elif req:
            self.cluster_key = " + ".join(req) + " (absent)"
        else:
            self.cluster_key = "Tronc commun / Sans spécialiste spécifique"
        self.present_set = frozenset(self.present_required_experts)
        self.required_set = frozenset(self.required_experts)


class MDTAgendaScheduler:
    """
    Pure deterministic scheduling service computing optimal MDT passage order,
    contiguous specialist blocks, quorum alerts, and human-readable ranking explanations.
    """

    @classmethod
    def schedule(
        cls,
        agenda: MDTAgenda,
        snapshots_by_patient: dict[str, MDTAgendaCandidateSnapshot],
        available_experts: list[str],
    ) -> MDTAgendaScheduleResult:
        """Compute the ordered `MDTAgendaScheduleResult` for `agenda`."""
        attending_set = set(agenda.attending_experts)
        available_order = {name: idx for idx, name in enumerate(available_experts)}

        enriched_all: list[_EnrichedCandidate] = []
        for idx, entry in enumerate(agenda.entries):
            snap = snapshots_by_patient.get(entry.patient_id)
            if snap is None:
                continue
            if entry.manual_order != idx:
                entry.manual_order = idx
            enriched_all.append(
                _EnrichedCandidate(
                    entry=entry,
                    snapshot=snap,
                    attending_set=attending_set,
                    available_order=available_order,
                )
            )

        total_n = len(enriched_all)
        if total_n == 0:
            empty_windows = [
                MDTExpertWindow(
                    expert_name=exp,
                    is_attending=exp in attending_set,
                    case_count=0,
                    urgent_case_count=0,
                    first_position=None,
                    last_position=None,
                    is_contiguous=True,
                    patient_ids=[],
                )
                for exp in available_experts
            ]
            return MDTAgendaScheduleResult(
                items=[],
                expert_windows=empty_windows,
                total_enrolled=0,
                urgent_count=0,
                incomplete_count=0,
                quorum_warning_count=0,
            )

        pinned_items = [
            c
            for c in enriched_all
            if c.entry.pinned and c.entry.pinned_position is not None
        ]
        unpinned_items = [
            c
            for c in enriched_all
            if not (c.entry.pinned and c.entry.pinned_position is not None)
        ]

        sorted_unpinned = cls._sort_unpinned(
            unpinned_items,
            strategy=agenda.sort_strategy,
            defer_incomplete=agenda.defer_incomplete_files,
        )

        # Merge pinned items at their exact 1-indexed target positions
        slots: list[_EnrichedCandidate | None] = [None] * total_n
        pinned_sorted = sorted(
            pinned_items,
            key=lambda c: (c.entry.pinned_position or 1, c.entry.manual_order),
        )
        for p_item in pinned_sorted:
            target_idx = min(
                max(0, (p_item.entry.pinned_position or 1) - 1), total_n - 1
            )
            while target_idx < total_n and slots[target_idx] is not None:
                target_idx += 1
            if target_idx >= total_n:
                target_idx = next(i for i, v in enumerate(slots) if v is None)
            slots[target_idx] = p_item

        unpinned_iter = iter(sorted_unpinned)
        for i in range(total_n):
            if slots[i] is None:
                slots[i] = next(unpinned_iter)

        final_candidates = [c for c in slots if c is not None]

        scheduled_items: list[MDTAgendaScheduledItem] = []
        for pos, cand in enumerate(final_candidates, start=1):
            reason = cls._build_rank_reason(
                cand=cand,
                position=pos,
                strategy=agenda.sort_strategy,
                defer_incomplete=agenda.defer_incomplete_files,
            )
            snap = cand.snapshot
            scheduled_items.append(
                MDTAgendaScheduledItem(
                    position=pos,
                    patient_id=snap.patient_id,
                    filename=cand.entry.filename or snap.filename,
                    patient_name=snap.patient_name,
                    first_name=snap.first_name,
                    last_name=snap.last_name,
                    date_birth=snap.date_birth,
                    urgency=snap.urgency,
                    urgency_score=snap.urgency_score,
                    priority_level=snap.priority_level,
                    is_complete=snap.is_complete,
                    missing_count=snap.missing_count,
                    missing_items=list(snap.missing_items),
                    care_adaptation_suggested=snap.care_adaptation_suggested,
                    proposed_care_type=snap.proposed_care_type,
                    required_experts=cand.required_experts,
                    present_required_experts=cand.present_required_experts,
                    absent_required_experts=cand.absent_required_experts,
                    quorum_met=cand.quorum_met,
                    expert_coverage_ratio=cand.expert_coverage_ratio,
                    cluster_key=cand.cluster_key,
                    pinned=(
                        cand.entry.pinned and cand.entry.pinned_position is not None
                    ),
                    rank_reason=reason,
                    mdt_date=snap.mdt_date,
                )
            )

        expert_windows = cls._compute_expert_windows(
            scheduled_items=scheduled_items,
            available_experts=available_experts,
            attending_set=attending_set,
        )

        urgent_count = sum(1 for item in scheduled_items if item.urgency_score >= 2)
        incomplete_count = sum(1 for item in scheduled_items if not item.is_complete)
        quorum_warning_count = sum(1 for item in scheduled_items if not item.quorum_met)

        return MDTAgendaScheduleResult(
            items=scheduled_items,
            expert_windows=expert_windows,
            total_enrolled=len(scheduled_items),
            urgent_count=urgent_count,
            incomplete_count=incomplete_count,
            quorum_warning_count=quorum_warning_count,
        )

    @classmethod
    def _sort_unpinned(
        cls,
        items: list[_EnrichedCandidate],
        strategy: MDTAgendaSortStrategy,
        defer_incomplete: bool,
    ) -> list[_EnrichedCandidate]:
        """Sort unpinned candidates according to `strategy` and `defer_incomplete`."""
        if not items:
            return []

        if strategy == MDTAgendaSortStrategy.MANUAL:
            if not defer_incomplete:
                return sorted(items, key=lambda c: c.entry.manual_order)
            complete = [c for c in items if c.snapshot.is_complete]
            incomplete = [c for c in items if not c.snapshot.is_complete]
            return sorted(complete, key=lambda c: c.entry.manual_order) + sorted(
                incomplete, key=lambda c: c.entry.manual_order
            )

        if defer_incomplete:
            complete_tier = [c for c in items if c.snapshot.is_complete]
            incomplete_tier = [c for c in items if not c.snapshot.is_complete]
            return cls._sort_tier(complete_tier, strategy) + cls._sort_tier(
                incomplete_tier, strategy
            )

        return cls._sort_tier(items, strategy)

    @classmethod
    def _base_priority_tuple(cls, c: _EnrichedCandidate) -> tuple:
        """Return descending-priority tuple (higher values are more critical)."""
        return (
            1 if c.quorum_met else 0,
            c.snapshot.urgency_score,
            1 if c.snapshot.care_adaptation_suggested else 0,
            1 if c.snapshot.is_complete else 0,
            c.expert_coverage_ratio,
            len(c.present_required_experts),
            len(c.required_experts),
            -c.entry.manual_order,
            c.snapshot.patient_name.lower(),
        )

    @classmethod
    def _sort_tier(
        cls,
        tier_items: list[_EnrichedCandidate],
        strategy: MDTAgendaSortStrategy,
    ) -> list[_EnrichedCandidate]:
        if len(tier_items) <= 1:
            return list(tier_items)

        if strategy == MDTAgendaSortStrategy.URGENCY_FIRST:
            return cls._sort_urgency_first(tier_items)
        if strategy == MDTAgendaSortStrategy.EXPERT_GROUPING:
            return cls._sort_by_expert_clusters(tier_items)
        # Default: HYBRID
        urgent_cases = [
            c for c in tier_items if c.snapshot.urgency_score >= 2 and c.quorum_met
        ]
        remaining_cases = [
            c
            for c in tier_items
            if not (c.snapshot.urgency_score >= 2 and c.quorum_met)
        ]
        ordered_urgent = cls._chain_by_shared_experts(urgent_cases)
        ordered_remaining = cls._sort_by_expert_clusters(
            remaining_cases,
            seed_experts=(
                ordered_urgent[-1].present_set if ordered_urgent else frozenset()
            ),
        )
        return ordered_urgent + ordered_remaining

    @classmethod
    def _sort_urgency_first(
        cls, items: list[_EnrichedCandidate]
    ) -> list[_EnrichedCandidate]:
        """Sort strictly by clinical urgency and quorum, chaining shared experts on equal urgency."""
        buckets: dict[tuple[int, int], list[_EnrichedCandidate]] = {}
        for c in items:
            key = (1 if c.quorum_met else 0, c.snapshot.urgency_score)
            buckets.setdefault(key, []).append(c)

        ordered_keys = sorted(buckets.keys(), reverse=True)
        result: list[_EnrichedCandidate] = []
        seed_experts: frozenset[str] = frozenset()
        for key in ordered_keys:
            chained = cls._chain_by_shared_experts(
                buckets[key], seed_experts=seed_experts
            )
            result.extend(chained)
            if chained:
                seed_experts = chained[-1].present_set
        return result

    @classmethod
    def _chain_by_shared_experts(
        cls,
        candidates: list[_EnrichedCandidate],
        seed_experts: frozenset[str] = frozenset(),
    ) -> list[_EnrichedCandidate]:
        """Greedy chaining within an urgency tier to maximize specialist overlap between adjacent cases."""
        if len(candidates) <= 1:
            return list(candidates)

        pool = sorted(
            candidates,
            key=cls._base_priority_tuple,
            reverse=True,
        )
        result: list[_EnrichedCandidate] = []
        current_experts = seed_experts

        while pool:
            if not current_experts:
                chosen = pool.pop(0)
            else:
                best_idx = 0
                best_key: tuple = (-1, ())
                for idx, cand in enumerate(pool):
                    overlap = len(cand.present_set & current_experts)
                    sym_diff = len(cand.present_set ^ current_experts)
                    cand_key = (
                        overlap,
                        -sym_diff,
                        cls._base_priority_tuple(cand),
                    )
                    if idx == 0 or cand_key > best_key:
                        best_key = cand_key
                        best_idx = idx
                chosen = pool.pop(best_idx)
            result.append(chosen)
            current_experts = chosen.present_set

        return result

    @classmethod
    def _sort_by_expert_clusters(
        cls,
        candidates: list[_EnrichedCandidate],
        seed_experts: frozenset[str] = frozenset(),
    ) -> list[_EnrichedCandidate]:
        """
        Group cases by their attending specialist signature (`present_set`), order clusters
        to maximize contiguous specialist presence and criticality, and sort cases by urgency within each cluster.
        """
        if len(candidates) <= 1:
            return list(candidates)

        clusters: dict[frozenset[str], list[_EnrichedCandidate]] = {}
        for c in candidates:
            clusters.setdefault(c.present_set, []).append(c)

        for sig in clusters:
            clusters[sig].sort(key=cls._base_priority_tuple, reverse=True)

        def cluster_criticality(sig: frozenset[str]) -> tuple:
            members = clusters[sig]
            quorum_all = 1 if all(m.quorum_met for m in members) else 0
            avg_cov = sum(m.expert_coverage_ratio for m in members) / len(members)
            max_urg = max(m.snapshot.urgency_score for m in members)
            sum_urg = sum(m.snapshot.urgency_score for m in members)
            has_experts = 1 if len(sig) > 0 else 0
            return (
                quorum_all,
                round(avg_cov, 4),
                max_urg,
                sum_urg,
                has_experts,
                len(sig),
                len(members),
            )

        remaining_sigs = list(clusters.keys())
        remaining_sigs.sort(key=cluster_criticality, reverse=True)

        ordered_result: list[_EnrichedCandidate] = []
        current_sig = seed_experts

        while remaining_sigs:
            if not current_sig:
                chosen_sig = remaining_sigs.pop(0)
            else:
                best_idx = 0
                best_score: tuple = ()
                for idx, sig in enumerate(remaining_sigs):
                    overlap = len(sig & current_sig)
                    jaccard = (
                        overlap / len(sig | current_sig) if (sig | current_sig) else 0.0
                    )
                    crit = cluster_criticality(sig)
                    score = (
                        1 if overlap > 0 else 0,
                        round(jaccard, 4),
                        overlap,
                        crit,
                    )
                    if idx == 0 or score > best_score:
                        best_score = score
                        best_idx = idx
                chosen_sig = remaining_sigs.pop(best_idx)

            ordered_result.extend(clusters[chosen_sig])
            current_sig = chosen_sig

        return ordered_result

    @classmethod
    def _build_rank_reason(
        cls,
        cand: _EnrichedCandidate,
        position: int,
        strategy: MDTAgendaSortStrategy,
        defer_incomplete: bool,
    ) -> str:
        """Build a concise French clinical explanation for the patient's scheduled position."""
        if cand.entry.pinned and cand.entry.pinned_position is not None:
            return f"Position épinglée manuellement (#{position})"

        parts: list[str] = []
        snap = cand.snapshot

        if not snap.is_complete and defer_incomplete:
            missing_n = snap.missing_count or len(snap.missing_items)
            suffix = f" ({missing_n} élém. manquant(s))" if missing_n else ""
            parts.append(f"Relégué en fin de séance : dossier incomplet{suffix}")

        if not cand.quorum_met:
            absent_str = ", ".join(cand.absent_required_experts)
            parts.append(
                f"Quorum incomplet : {len(cand.absent_required_experts)} spécialiste(s) absent(s) ({absent_str})"
            )

        if strategy == MDTAgendaSortStrategy.MANUAL:
            parts.append(f"Ordre manuel (#{position})")
        elif snap.urgency_score >= 2:
            parts.append("Priorité haute (Urgent)")
        elif (
            strategy == MDTAgendaSortStrategy.EXPERT_GROUPING
            and cand.present_required_experts
        ):
            parts.append(
                f"Bloc spécialistes : {', '.join(cand.present_required_experts)}"
            )
            if snap.urgency_score == 1:
                parts.append("Priorité semi-urgente")
        elif snap.urgency_score == 1:
            parts.append("Priorité semi-urgente")
            if cand.present_required_experts:
                parts.append(
                    f"Bloc spécialistes : {', '.join(cand.present_required_experts)}"
                )
        else:
            if cand.present_required_experts:
                parts.append(
                    f"Bloc spécialistes : {', '.join(cand.present_required_experts)}"
                )
            else:
                parts.append("Priorité standard")

        if cand.quorum_met and cand.required_experts:
            n_req = len(cand.required_experts)
            parts.append(f"Quorum complet ({n_req}/{n_req})")

        if snap.care_adaptation_suggested:
            parts.append("Adaptation thérapeutique suggérée")
        elif snap.is_complete and not (not snap.is_complete and defer_incomplete):
            parts.append("Dossier complet")

        return " · ".join(parts)

    @classmethod
    def _compute_expert_windows(
        cls,
        scheduled_items: list[MDTAgendaScheduledItem],
        available_experts: list[str],
        attending_set: set[str],
    ) -> list[MDTExpertWindow]:
        """Compute the passage window (`first_position`..`last_position`) for each domain specialist."""
        windows: list[MDTExpertWindow] = []
        for exp in available_experts:
            positions: list[int] = []
            patient_ids: list[str] = []
            urgent_count = 0
            for item in scheduled_items:
                if exp in item.required_experts:
                    positions.append(item.position)
                    patient_ids.append(item.patient_id)
                    if item.urgency_score >= 2:
                        urgent_count += 1

            if positions:
                first_pos = positions[0]
                last_pos = positions[-1]
                span = last_pos - first_pos + 1
                # Contiguous if all cases are adjacent or separated by at most 1 slot
                is_contiguous = (span - len(positions)) <= 1
            else:
                first_pos = None
                last_pos = None
                is_contiguous = True

            windows.append(
                MDTExpertWindow(
                    expert_name=exp,
                    is_attending=exp in attending_set,
                    case_count=len(positions),
                    urgent_case_count=urgent_count,
                    first_position=first_pos,
                    last_position=last_pos,
                    is_contiguous=is_contiguous,
                    patient_ids=patient_ids,
                )
            )
        return windows
