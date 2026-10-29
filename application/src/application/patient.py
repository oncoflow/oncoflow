from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from slugify import slugify

from src.application.paths import is_safe_filename
from src.domain.common.common_ressources import Gender, PatientPriority
from src.domain.patient import Patient
from src.infrastructure.documents.mongodb import Mongodb

_PARIS_TZ = ZoneInfo("Europe/Paris")


def to_naive(dt: datetime | None) -> datetime | None:
    """Convertit un datetime (aware ou naive) en datetime naive (Europe/Paris)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(_PARIS_TZ).replace(tzinfo=None)
    return dt


def normalize_date_str(date_val: datetime | str | None) -> str | None:
    """Normalise un datetime ou une chaîne ISO en YYYY_MM_DD."""
    if date_val is None or date_val == "":
        return None
    if isinstance(date_val, str):
        try:
            date_val = datetime.fromisoformat(date_val)
        except ValueError:
            return slugify(date_val, separator="_") or None
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y_%m_%d")
    return None


def build_name_key(first_name: str | None, last_name: str | None) -> str:
    """Construit une clé normalisée basée sur le nom et le prénom."""
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    if fn.lower() in ("inconnu", "unknown", "none", "null"):
        fn = ""
    if ln.lower() in ("inconnu", "unknown", "none", "null"):
        ln = ""
    if not fn and not ln:
        return ""
    return slugify(f"{ln}_{fn}", separator="_")


def build_patient_id(
    first_name: str | None,
    last_name: str | None,
    date_birth: datetime | str | None = None,
    fallback_file: str | None = None,
) -> str:
    """
    Construit un patient_id déterministe et normalisé à partir de (last_name, first_name, date_birth).
    Repli sur (last_name, first_name) si date_birth est absent, ou sur fallback_file si le nom est inconnu.
    """
    name_key = build_name_key(first_name, last_name)
    if not name_key:
        file_slug = slugify(fallback_file or "unknown", separator="_")
        return f"patient_{file_slug}"

    dob_str = normalize_date_str(date_birth)
    if dob_str:
        return f"{name_key}_{dob_str}"
    return name_key


def build_patient_from_administrative(
    admin_data: BaseModel | dict | None,
    filename: str | None = None,
    existing_patient: Patient | dict | None = None,
) -> Patient:
    """
    Instancie ou met à jour un modèle domaine Patient à partir des données PatientAdministrative.
    """
    if isinstance(admin_data, BaseModel):
        admin_dict = admin_data.model_dump()
    elif isinstance(admin_data, dict):
        admin_dict = dict(admin_data)
    else:
        admin_dict = {}

    existing_dict: dict = {}
    if isinstance(existing_patient, Patient):
        existing_dict = existing_patient.model_dump()
    elif isinstance(existing_patient, dict):
        existing_dict = dict(existing_patient)

    first_name = (
        admin_dict.get("first_name") or existing_dict.get("first_name") or ""
    ).strip()
    last_name = (
        admin_dict.get("last_name") or existing_dict.get("last_name") or ""
    ).strip()
    born_name = admin_dict.get("born_name") or existing_dict.get("born_name")
    date_birth = admin_dict.get("date_birth") or existing_dict.get("date_birth")
    gender = admin_dict.get("gender") or existing_dict.get("gender") or Gender.not_given

    patient_id = existing_dict.get("patient_id") or build_patient_id(
        first_name=first_name,
        last_name=last_name,
        date_birth=date_birth,
        fallback_file=filename,
    )

    files = list(existing_dict.get("files", []))
    if filename and filename not in files:
        files.append(filename)

    return Patient(
        patient_id=patient_id,
        first_name=first_name,
        last_name=last_name,
        born_name=born_name,
        date_birth=date_birth,
        gender=gender,
        files=files,
        updated_at=datetime.now(),
    )


def sync_patient_from_admin(
    mtd_datas: dict,
    db_client: Mongodb | None = None,
    target_patient_id: str | None = None,
) -> Patient:
    """
    Synchronise le modèle Patient et l'entrée MongoDB `patients` à partir de `mtd_datas["PatientAdministrative"]`.
    Si `target_patient_id` est fourni (association manuelle), force l'identité du patient sélectionné
    tout en conservant `date_rcp` et `age` extraits de la fiche RCP courante.
    """
    admin_raw = mtd_datas.get("PatientAdministrative")
    if isinstance(admin_raw, BaseModel):
        admin_dict = json_safe_dict(admin_raw)
    elif isinstance(admin_raw, dict):
        admin_dict = dict(admin_raw)
    else:
        admin_dict = {}

    filename = mtd_datas.get("file")
    existing_patient = None

    if db_client is not None:
        if target_patient_id:
            existing_patient = db_client.get_patient(target_patient_id)
            if existing_patient:
                admin_dict["first_name"] = existing_patient.get(
                    "first_name", admin_dict.get("first_name", "")
                )
                admin_dict["last_name"] = existing_patient.get(
                    "last_name", admin_dict.get("last_name", "")
                )
                if existing_patient.get("born_name") is not None:
                    admin_dict["born_name"] = existing_patient.get("born_name")
                if existing_patient.get("date_birth") is not None:
                    dob = existing_patient.get("date_birth")
                    admin_dict["date_birth"] = (
                        dob.strftime("%Y-%m-%d") if isinstance(dob, datetime) else dob
                    )
                if existing_patient.get("gender") is not None:
                    admin_dict["gender"] = existing_patient.get("gender")
        else:
            existing_patient = db_client.find_patient_by_identity(
                first_name=admin_dict.get("first_name"),
                last_name=admin_dict.get("last_name"),
                date_birth=admin_dict.get("date_birth"),
                fallback_file=filename,
            )

    patient_obj = build_patient_from_administrative(
        admin_data=admin_dict,
        filename=filename,
        existing_patient=existing_patient,
    )
    if target_patient_id:
        patient_obj.patient_id = target_patient_id

    if admin_dict:
        mtd_datas["PatientAdministrative"] = admin_dict
    mtd_datas["patient_id"] = patient_obj.patient_id

    if db_client is not None:
        db_client.upsert_patient(patient_obj.model_dump(), filename=filename)

    return patient_obj


def json_safe_dict(model: BaseModel) -> dict[str, Any]:
    """Convertit un BaseModel en dict compatible JSON."""
    import json

    return json.loads(model.model_dump_json())


def process_patient_association(
    form: Any,
    target_patient_id: str | None = None,
    run_admin_ai: bool = True,
    callbacks: list | None = None,
) -> Patient:
    """
    Exécute l'extraction IA administrative sur la fiche RCP (si run_admin_ai=True),
    crée ou associe le Patient correspondant (automatique ou forcé sur target_patient_id),
    et persiste le tout dans MongoDB.
    """
    if run_admin_ai:
        form.read_model(form.PatientAdministrative, upsert=False, callbacks=callbacks)

    form.mtd_datas["ui_date"] = datetime.now()

    db_client = None
    should_close = False
    if form.config.rcp.display_type == "mongodb":
        if getattr(form, "db_client", None) is not None:
            db_client = form.db_client
        else:
            db_client = Mongodb(form.config)
            should_close = True

    try:
        patient_obj = sync_patient_from_admin(
            mtd_datas=form.mtd_datas,
            db_client=db_client,
            target_patient_id=target_patient_id,
        )
        form.patient = patient_obj
        if db_client is not None:
            upsert_payload = {
                "patient_id": patient_obj.patient_id,
                "ui_date": form.mtd_datas["ui_date"],
                "execution_times": form.mtd_datas.get("execution_times", {}),
            }
            if "PatientAdministrative" in form.mtd_datas:
                upsert_payload["PatientAdministrative"] = form.mtd_datas[
                    "PatientAdministrative"
                ]
            db_client.update_doc(
                collection="rcp_info",
                filter={"file": form.mtd_datas["file"]},
                upsertable_data=upsert_payload,
            )
        return patient_obj
    finally:
        if should_close and db_client is not None:
            db_client.close()
        elif getattr(form, "db_client", None) is not None:
            form.db_client.close()
            form.db_client = None


def is_rcp_visible_in_cards(d: dict) -> bool:
    """
    Détermine si une fiche RCP est prête à être affichée dans le tableau de bord de consultation.
    Une fiche apparaît dès que l'identité du patient (Étape 1) est extraite (ou pour toute fiche historique).
    Les fiches venant d'être déposées et encore en attente d'identification (PENDING_ADMIN / PROCESSING_ADMIN
    sans PatientAdministrative) restent uniquement dans la file de traitement.
    """
    status = d.get("processing_status")
    if status in ("PENDING_ADMIN", "PROCESSING_ADMIN") and not d.get(
        "PatientAdministrative"
    ):
        return False
    return True


def extract_card_metrics(d: dict) -> dict:
    """Extrait les métriques d'affichage d'une carte à partir d'un document rcp_info."""
    processing_status = d.get("processing_status")
    if not processing_status:
        processing_status = "COMPLETED"

    is_clinical_pending = processing_status in (
        "PENDING_CLINICAL",
        "PROCESSING_CLINICAL",
    )

    patient_name = "Inconnu"
    if "PatientAdministrative" in d and isinstance(d["PatientAdministrative"], dict):
        p = d["PatientAdministrative"]
        first = p.get("first_name", "") or ""
        last = p.get("last_name", "") or ""
        full = f"{first} {last}".strip()
        if full:
            patient_name = full

    date_refresh = d.get(
        "ui_date",
        datetime.now(_PARIS_TZ).replace(hour=0, minute=0, second=0, microsecond=0),
    )
    if isinstance(date_refresh, str):
        try:
            date_refresh = datetime.fromisoformat(date_refresh)
        except ValueError:
            date_refresh = datetime.now()
    date_refresh = to_naive(date_refresh)

    date_mcp = (
        d["PatientAdministrative"].get("date_rcp")
        if "PatientAdministrative" in d and isinstance(d["PatientAdministrative"], dict)
        else None
    )
    if isinstance(date_mcp, str):
        try:
            date_mcp = datetime.fromisoformat(date_mcp)
        except ValueError:
            date_mcp = None
    date_mcp = to_naive(date_mcp)

    # Experts Pertinents & Urgence
    relevant_experts = []
    urgency_level = "Indéfini"
    urgency_score = 0  # 0: Low/None, 1: Medium, 2: Urgent

    if "ExpertAnswer" in d and isinstance(d["ExpertAnswer"], dict):
        for agent_name, agent_data in d["ExpertAnswer"].items():
            if isinstance(agent_data, dict):
                if agent_data.get("expert_relevant"):
                    relevant_experts.append(agent_name)

                p_prio = str(agent_data.get("patient_priority", "")).lower()
                for urgency in list(PatientPriority):
                    if p_prio == urgency.value.lower():
                        if urgency.name == "urgent":
                            if urgency_score < 2:
                                urgency_score = 2
                                urgency_level = "Urgent"
                        elif urgency.name == "medium":
                            if urgency_score < 1:
                                urgency_score = 1
                                urgency_level = "Semi-urgent"
                        elif urgency.name == "low":
                            if urgency_score == 0:
                                urgency_level = "Standard"

    # Données Manquantes
    missing_data = []
    if "MTDCompleted" in d and isinstance(d["MTDCompleted"], dict):
        if "mtd_complete" in d["MTDCompleted"]:
            mtd_comp = d["MTDCompleted"].get("mtd_complete")
            if isinstance(mtd_comp, dict):
                m = mtd_comp.get("what_missing", [])
                if isinstance(m, list):
                    missing_data.extend(m)
        else:
            for agent_name, agent_data in d["MTDCompleted"].items():
                if isinstance(agent_data, dict):
                    mtd_comp = agent_data.get("mtd_complete")
                    if isinstance(mtd_comp, dict):
                        m = mtd_comp.get("what_missing", [])
                        if isinstance(m, list):
                            missing_data.extend(m)
    elif not is_clinical_pending:
        missing_data.extend(["no data"])

    # Intervention requise
    intervention_required = None
    intervention_type = None
    if "isInterventionRequiered" in d and isinstance(
        d["isInterventionRequiered"], dict
    ):
        int_data = d["isInterventionRequiered"]
        if "intervention_required" in int_data:
            intervention_required = int_data.get("intervention_required")
            intervention_type = int_data.get("intervention_type")
        else:
            for agent_data in int_data.values():
                if (
                    isinstance(agent_data, dict)
                    and "intervention_required" in agent_data
                ):
                    intervention_required = agent_data.get("intervention_required")
                    intervention_type = agent_data.get("intervention_type")
                    break

    patient_id = d.get("patient_id")
    link = (
        f"datas?patient_id={patient_id}&file={d['file']}"
        if patient_id
        else f"datas?file={d['file']}"
    )

    return {
        "file": d["file"],
        "patient_id": patient_id,
        "patient": patient_name,
        "date_refresh": date_refresh,
        "date": date_mcp,
        "experts": relevant_experts,
        "missing": list(set(missing_data)),
        "urgency": urgency_level,
        "urgency_score": urgency_score,
        "link": link,
        "intervention_required": intervention_required,
        "intervention_type": intervention_type,
        "processing_status": processing_status,
        "processing_step": d.get("processing_step"),
        "processing_progress_pct": d.get("processing_progress_pct", 0.0),
    }


def select_latest_analyzed_rcp(rcp_docs: list[dict]) -> dict | None:
    """
    Sélectionne la dernière fiche RCP analysée d'un patient.
    Priorise les fiches ayant une analyse IA, puis trie par date_rcp (ou ui_date à défaut) décroissante.
    """
    if not rcp_docs:
        return None

    def sort_key(doc: dict):
        has_clinical_ai = int(
            bool(
                doc.get("ExpertAnswer")
                or doc.get("MTDCompleted")
                or doc.get("isInterventionRequiered")
            )
        )
        has_admin_ai = int(bool(doc.get("PatientAdministrative")))
        metrics = extract_card_metrics(doc)
        effective_date = (
            metrics.get("date") or metrics.get("date_refresh") or datetime.min
        )
        refresh_date = metrics.get("date_refresh") or datetime.min
        return (has_clinical_ai, has_admin_ai, effective_date, refresh_date)

    return max(rcp_docs, key=sort_key)


def extract_rcp_date(doc: dict) -> datetime | None:
    """Extrait la date clinique de la RCP (ou ui_date en secours) à partir d'un document rcp_info."""
    admin = doc.get("PatientAdministrative")
    if isinstance(admin, dict) and admin.get("date_rcp"):
        d_rcp = admin.get("date_rcp")
        if isinstance(d_rcp, str):
            try:
                d_rcp = datetime.fromisoformat(d_rcp)
            except ValueError:
                d_rcp = None
        if isinstance(d_rcp, datetime):
            return to_naive(d_rcp)
    ui_d = doc.get("ui_date")
    if isinstance(ui_d, str):
        try:
            ui_d = datetime.fromisoformat(ui_d)
        except ValueError:
            ui_d = None
    if isinstance(ui_d, datetime):
        return to_naive(ui_d)
    return None


def ensure_patients_synced(db_client: Mongodb | None) -> None:
    """
    Synchronise automatiquement dans la collection `patients` toutes les fiches `rcp_info`
    possédant des informations `PatientAdministrative` mais pas encore de `patient_id` enregistré.
    """
    if db_client is None or not hasattr(db_client, "database"):
        return

    try:
        rcp_docs = list(
            db_client.database["rcp_info"].find(
                {},
                {"file": 1, "patient_id": 1, "PatientAdministrative": 1},
            )
        )
        existing_patients = {
            p.get("patient_id"): p
            for p in (
                db_client.get_all_patients()
                if hasattr(db_client, "get_all_patients")
                else []
            )
            if isinstance(p, dict) and p.get("patient_id")
        }

        for doc in rcp_docs:
            fname = doc.get("file")
            if not fname:
                continue
            admin = doc.get("PatientAdministrative")
            if not isinstance(admin, dict) or not (
                admin.get("first_name") or admin.get("last_name")
            ):
                continue

            pid = doc.get("patient_id")
            p_entry = existing_patients.get(pid) if pid else None
            if (
                pid
                and p_entry
                and isinstance(p_entry.get("files"), list)
                and fname in p_entry["files"]
            ):
                continue

            mtd_copy = {
                "file": fname,
                "PatientAdministrative": dict(admin),
            }
            if pid:
                mtd_copy["patient_id"] = pid

            patient_obj = sync_patient_from_admin(
                mtd_datas=mtd_copy,
                db_client=db_client,
                target_patient_id=pid,
            )
            existing_patients[patient_obj.patient_id] = patient_obj.model_dump()
            if doc.get("patient_id") != patient_obj.patient_id:
                db_client.update_doc(
                    collection="rcp_info",
                    filter={"file": fname},
                    upsertable_data={"patient_id": patient_obj.patient_id},
                )
    except Exception:
        pass


def build_patients_cards_data(db_client: Mongodb | None) -> list[dict]:
    """
    Récupère les dossiers patients et construit pour chacun la carte basée sur sa dernière RCP analysée.
    Inclut également un regroupement de secours pour les fiches RCP non encore rattachées à la collection `patients`.
    """
    if db_client is None or not hasattr(db_client, "database"):
        return []

    ensure_patients_synced(db_client)

    projection = {
        "file": 1,
        "patient_id": 1,
        "ui_date": 1,
        "PatientAdministrative": 1,
        "ExpertAnswer": 1,
        "MTDCompleted": 1,
        "isInterventionRequiered": 1,
        "processing_status": 1,
        "processing_step": 1,
        "processing_progress_pct": 1,
    }
    all_rcps = [
        d
        for d in db_client.database["rcp_info"].find({}, projection)
        if is_rcp_visible_in_cards(d)
    ]
    if not all_rcps:
        return []

    rcps_by_file = {d["file"]: d for d in all_rcps if "file" in d}
    covered_files: set[str] = set()
    patient_cards: list[dict] = []

    raw_patients = (
        db_client.get_all_patients() if hasattr(db_client, "get_all_patients") else []
    )
    for raw_p in raw_patients:
        try:
            patient = Patient.model_validate(raw_p)
        except Exception:
            continue

        patient_rcps_map: dict[str, dict] = {}
        for f in patient.files:
            if f in rcps_by_file:
                patient_rcps_map[f] = rcps_by_file[f]
        for d in all_rcps:
            if d.get("patient_id") == patient.patient_id and "file" in d:
                patient_rcps_map[d["file"]] = d

        patient_rcps = list(patient_rcps_map.values())
        if not patient_rcps:
            continue

        for d in patient_rcps:
            covered_files.add(d["file"])

        latest_doc = select_latest_analyzed_rcp(patient_rcps)
        if latest_doc is None:
            continue

        card = extract_card_metrics(latest_doc)
        card["patient_id"] = patient.patient_id
        card["patient"] = patient.full_name
        card["rcp_count"] = len(patient_rcps)
        card["link"] = (
            f"datas?patient_id={patient.patient_id}&file={latest_doc['file']}"
        )
        card["is_patient_card"] = True
        patient_cards.append(card)

    # Regroupement de secours pour les fiches RCP existantes sans entrée dans `patients`
    orphan_groups: dict[str, list[dict]] = {}
    for d in all_rcps:
        fname = d.get("file")
        if not fname or fname in covered_files:
            continue
        admin = d.get("PatientAdministrative")
        if isinstance(admin, dict) and (
            admin.get("first_name") or admin.get("last_name")
        ):
            pid = d.get("patient_id") or build_patient_id(
                admin.get("first_name"),
                admin.get("last_name"),
                admin.get("date_birth"),
            )
        else:
            pid = f"orphan_{fname}"
        orphan_groups.setdefault(pid, []).append(d)

    for pid, docs in orphan_groups.items():
        latest_doc = select_latest_analyzed_rcp(docs)
        if latest_doc is None:
            continue
        card = extract_card_metrics(latest_doc)
        card["patient_id"] = None if pid.startswith("orphan_") else pid
        card["rcp_count"] = len(docs)
        card["link"] = (
            f"datas?patient_id={pid}&file={latest_doc['file']}"
            if not pid.startswith("orphan_")
            else f"datas?file={latest_doc['file']}"
        )
        card["is_patient_card"] = not pid.startswith("orphan_")
        patient_cards.append(card)

    patient_cards.sort(
        key=lambda x: (
            x.get("urgency_score", 0),
            x.get("date") or x.get("date_refresh") or datetime.min,
        ),
        reverse=True,
    )
    return patient_cards


def resolve_patient_dossier(
    db_client: Mongodb | None,
    patient_id_param: str | None = None,
    file_param: str | None = None,
    logger: Any = None,
) -> tuple[Patient | None, list[dict], str | None]:
    """
    Résout le dossier patient, la liste chronologique de ses fiches RCP (de la plus récente à la plus ancienne),
    ainsi que le fichier RCP actuellement sélectionné.
    """
    if file_param and not is_safe_filename(file_param):
        file_param = None
    if db_client is None or not hasattr(db_client, "database"):
        return None, [], file_param

    ensure_patients_synced(db_client)

    patient_obj: Patient | None = None
    patient_rcps_map: dict[str, dict] = {}

    # 1. Si `file` est fourni, charger d'abord cette fiche et tenter de retrouver son `patient_id`
    if file_param:
        rcp_doc = db_client.database["rcp_info"].find_one({"file": file_param})
        if rcp_doc:
            patient_rcps_map[file_param] = rcp_doc
            if not patient_id_param:
                patient_id_param = rcp_doc.get("patient_id")
            if not patient_id_param and isinstance(
                rcp_doc.get("PatientAdministrative"), dict
            ):
                admin = rcp_doc["PatientAdministrative"]
                found_p = db_client.find_patient_by_identity(
                    admin.get("first_name"),
                    admin.get("last_name"),
                    admin.get("date_birth"),
                )
                if found_p:
                    patient_id_param = found_p.get("patient_id")
                elif admin.get("first_name") or admin.get("last_name"):
                    patient_obj = build_patient_from_administrative(
                        admin, filename=file_param
                    )
                    patient_id_param = patient_obj.patient_id

    # 2. Charger l'objet Patient depuis MongoDB si disponible
    if patient_id_param and patient_obj is None:
        raw_p = db_client.get_patient(patient_id_param)
        if raw_p:
            try:
                patient_obj = Patient.model_validate(raw_p)
            except Exception as e:
                if logger:
                    logger.warning(f"Validation Patient impossible: {e}")

    # 3. Récupérer toutes les fiches RCP associées à ce patient
    if patient_obj is not None:
        for f in patient_obj.files:
            doc = db_client.database["rcp_info"].find_one({"file": f})
            if doc:
                patient_rcps_map[f] = doc

    if patient_id_param:
        for doc in db_client.database["rcp_info"].find(
            {"patient_id": patient_id_param}
        ):
            if "file" in doc:
                patient_rcps_map[doc["file"]] = doc

        # Fallback systématique : rechercher aussi les fiches partageant la même identité administrative
        target_pid = (
            patient_obj.patient_id if patient_obj is not None else patient_id_param
        )
        for doc in db_client.database["rcp_info"].find():
            admin = doc.get("PatientAdministrative")
            if isinstance(admin, dict) and (
                admin.get("first_name") or admin.get("last_name")
            ):
                cand_id = doc.get("patient_id") or build_patient_id(
                    admin.get("first_name"),
                    admin.get("last_name"),
                    admin.get("date_birth"),
                )
                cand_name_only = build_patient_id(
                    admin.get("first_name"),
                    admin.get("last_name"),
                    None,
                )
                if (
                    cand_id == target_pid or cand_name_only == target_pid
                ) and "file" in doc:
                    patient_rcps_map[doc["file"]] = doc

    # 4. Trier les fiches RCP de la plus récente à la plus ancienne
    patient_rcps = list(patient_rcps_map.values())
    patient_rcps.sort(
        key=lambda d: extract_rcp_date(d) or datetime.min,
        reverse=True,
    )

    # 5. Déterminer la fiche RCP active (par défaut : la dernière RCP analysée)
    selected_file = file_param
    valid_files = [d["file"] for d in patient_rcps if "file" in d]
    if not selected_file or (valid_files and selected_file not in valid_files):
        latest_doc = select_latest_analyzed_rcp(patient_rcps)
        if latest_doc and "file" in latest_doc:
            selected_file = latest_doc["file"]
        elif valid_files:
            selected_file = valid_files[0]

    # Si patient_obj n'existe toujours pas mais qu'on a une fiche avec PatientAdministrative
    if patient_obj is None and selected_file and selected_file in patient_rcps_map:
        admin = patient_rcps_map[selected_file].get("PatientAdministrative")
        if isinstance(admin, dict) and (
            admin.get("first_name") or admin.get("last_name")
        ):
            patient_obj = build_patient_from_administrative(
                admin,
                filename=selected_file,
                existing_patient={"patient_id": patient_id_param, "files": valid_files}
                if patient_id_param
                else {"files": valid_files},
            )

    return patient_obj, patient_rcps, selected_file


def _serialize_ai_value(val: Any) -> Any:
    """Convertit récursivement les modèles Pydantic et dictionnaires d'extraction IA en structures sérialisables JSON."""
    if isinstance(val, BaseModel):
        data = json_safe_dict(val)
        data.pop("reasoning_thinking", None)
        return data
    if isinstance(val, dict):
        return {
            k: _serialize_ai_value(v)
            for k, v in val.items()
            if k not in ("_id", "id", "execution_times", "reasoning_thinking")
        }
    if isinstance(val, list):
        return [_serialize_ai_value(item) for item in val]
    return val


def format_patient_ai_history(patient_readers: list[Any]) -> str:
    """
    Formate l'historique chronologique de toutes les informations extraites par l'IA
    (administratives, cliniques, avis d'experts, consensus d'intervention, complétude)
    sur l'ensemble des fiches RCP du dossier patient.
    """
    import json

    sections: list[str] = []
    excluded_top_keys = {
        "_id",
        "id",
        "file",
        "patient_id",
        "ui_date",
        "execution_times",
        "processing_status",
        "processing_step",
        "processing_progress_pct",
    }

    for reader in patient_readers:
        doc_name = getattr(reader, "document", None) or "unknown"
        raw_datas: dict[str, Any] = {}

        if isinstance(getattr(reader, "mtd_datas", None), dict):
            raw_datas = dict(reader.mtd_datas)

        # Fallback vers MongoDB si le reader est un simple DocumentReader sans mtd_datas chargées
        has_ai_keys = any(k not in excluded_top_keys for k in raw_datas)
        if not has_ai_keys:
            cfg = getattr(reader, "config", None)
            if (
                cfg is not None
                and getattr(getattr(cfg, "rcp", None), "display_type", None)
                == "mongodb"
            ):
                try:
                    client = Mongodb(cfg)
                    db_doc = client.get_document(
                        collection="rcp_info", filter={"file": doc_name}
                    )
                    client.close()
                    if isinstance(db_doc, dict):
                        raw_datas = db_doc
                except Exception:
                    pass

        ai_payload = {
            k: _serialize_ai_value(v)
            for k, v in raw_datas.items()
            if k not in excluded_top_keys and v is not None
        }

        rcp_dt = extract_rcp_date(ai_payload) or extract_rcp_date(raw_datas)
        date_str = rcp_dt.strftime("%Y-%m-%d") if rcp_dt else "Inconnue"

        if ai_payload:
            body_str = json.dumps(ai_payload, ensure_ascii=False, indent=2, default=str)
        else:
            body_str = "Aucune analyse IA enregistrée pour cette fiche RCP."

        sections.append(
            f"=== HISTORIQUE IA — FICHE RCP : {doc_name} (Date RCP : {date_str}) ===\n{body_str}"
        )

    return "\n\n".join(sections)
