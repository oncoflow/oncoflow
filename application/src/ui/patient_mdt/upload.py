import os
import streamlit as st

from src.application.config import AppConfig
from src.application.use_cases import (
    PatientMDTFormExtractionService,
    PatientRecordService,
)
from src.domain.patient import Patient
from src.domain.patient_mdt_form import NonPatientMDTFormError
from src.domain.worker import RCPProcessingStatus
from src.infrastructure.documents.repositories import (
    MongoDocumentCacheRepository,
    MongoPatientMDTFormRepository,
    MongoPatientRepository,
)
from src.infrastructure.queue import QueueBroker


app_conf = AppConfig()
PAGES_DIR_SRC = "src/ui"
logger = app_conf.set_logger("ui", default_context={"page": "upload"})


def _get_extraction_service() -> PatientMDTFormExtractionService:
    """Instantiate a `PatientMDTFormExtractionService` for the active UI configuration."""
    record_service = PatientRecordService.from_config(app_conf)
    return PatientMDTFormExtractionService(
        config=app_conf,
        patient_repo=MongoPatientRepository(app_conf),
        mdt_form_repo=MongoPatientMDTFormRepository(app_conf),
        cache_repo=MongoDocumentCacheRepository(app_conf),
        patient_record_service=record_service,
    )


def load_existing_patients() -> list[Patient]:
    """Load the list of existing patients from MongoDB."""
    if app_conf.rcp.display_type != "mongodb":
        return []
    patient_repo = MongoPatientRepository(app_conf)
    return patient_repo.list_all()


def _format_business_status(rcp_doc: dict | None) -> tuple[str, int, bool]:
    """
    Translate the PatientMDTForm processing state into a business label, progress percentage,
    and an indicator of whether the patient dossier can be opened.
    """
    if not rcp_doc:
        return "⏳ En attente de traitement", 0, False

    proc_status = rcp_doc.get("processing_status")
    proc_step = rcp_doc.get("processing_step") or ""
    pct = int(rcp_doc.get("processing_progress_pct") or 0)

    if proc_status == RCPProcessingStatus.PENDING_ADMIN.value:
        return "⏳ En attente de traitement", max(pct, 5), False
    if proc_status == RCPProcessingStatus.PROCESSING_ADMIN.value:
        return "🔍 Identification du patient en cours...", max(pct, 20), False
    if proc_status == RCPProcessingStatus.PENDING_CLINICAL.value:
        return "⏳ Patient identifié — Analyse clinique en attente", max(pct, 30), True
    if proc_status == RCPProcessingStatus.PROCESSING_CLINICAL.value:
        step_label = proc_step if proc_step else "Analyse clinique en cours..."
        return f"📋 {step_label}", max(pct, 40), True
    if proc_status == RCPProcessingStatus.FAILED.value:
        return "❌ Échec du traitement", pct, bool(rcp_doc.get("patient_id"))
    if proc_status == RCPProcessingStatus.COMPLETED.value or proc_status is None:
        return "✅ Dossier prêt", 100, True

    return "⏳ En cours de traitement...", pct, bool(rcp_doc.get("patient_id"))


def _resolve_patient_display_name(
    rcp_doc: dict | None, patients_by_id: dict[str, Patient]
) -> str:
    if not rcp_doc:
        return "Identification en cours..."
    pid = rcp_doc.get("patient_id")
    if pid and pid in patients_by_id:
        return patients_by_id[pid].display_label
    admin = rcp_doc.get("PatientAdministrative")
    if isinstance(admin, dict):
        first = (admin.get("first_name") or "").strip()
        last = (admin.get("last_name") or "").strip()
        full = f"{first} {last}".strip()
        if full:
            return full
    if rcp_doc.get("processing_status") in (
        RCPProcessingStatus.PENDING_ADMIN.value,
        RCPProcessingStatus.PROCESSING_ADMIN.value,
    ):
        return "Identification en cours..."
    return pid or "Patient non renseigné"


@st.fragment(run_every="3s")
def render_upload_queue_tracker():
    """
    Display the processing queue progress in real time using business-oriented labels
    without exposing technical internals.
    """
    if app_conf.rcp.display_type != "mongodb":
        return

    broker = QueueBroker(app_conf)
    mdt_repo = MongoPatientMDTFormRepository(app_conf)
    patient_repo = MongoPatientRepository(app_conf)
    try:
        stats = broker.get_queue_stats()
        active_jobs = broker.get_queue_jobs(
            status="PENDING", limit=100
        ) + broker.get_queue_jobs(status="PROCESSING", limit=100)
        failed_jobs = broker.get_queue_jobs(status="FAILED", limit=100)
        failed_jobs_by_file = {
            j["filename"]: j for j in failed_jobs if j.get("filename")
        }
        batch_info = st.session_state.get("last_upload_batch") or {}
        batch_files: list[str] = batch_info.get("files", [])

        tracked_files: list[str] = []
        for fn in batch_files:
            if fn not in tracked_files:
                tracked_files.append(fn)
        for job in active_jobs:
            fn = job.get("filename")
            if fn and fn not in tracked_files:
                tracked_files.append(fn)

        if not tracked_files and stats["pending"] == 0 and stats["processing"] == 0:
            return

        rcp_docs_by_file: dict[str, dict] = {}
        if tracked_files:
            docs = mdt_repo.list_by_filenames(
                tracked_files,
                projection={
                    "file": 1,
                    "patient_id": 1,
                    "PatientAdministrative": 1,
                    "processing_status": 1,
                    "processing_step": 1,
                    "processing_progress_pct": 1,
                },
            )
            rcp_docs_by_file = {d["file"]: d for d in docs if "file" in d}

        patients_by_id: dict[str, Patient] = {
            p.patient_id: p for p in patient_repo.list_all()
        }
        thinking_snap = broker.get_job_thinking()
    finally:
        broker.close()

    with st.container(key="clinical_scroll_upload_tracker"):
        st.divider()
        st.subheader("⏳ Suivi de la file de traitement")

    active_total = stats["pending"] + stats["processing"]
    if active_total > 0:
        st.info(
            f"📋 **{stats['processing']}** fiche(s) en cours de traitement • "
            f"**{stats['pending']}** tâche(s) en attente dans la file de traitement"
        )
        if thinking_snap.get("active"):
            active_fn = thinking_snap.get("filename") or "-"
            active_agent = (
                thinking_snap.get("active_agent") or "Initialisation de l'agent..."
            )
            active_step = thinking_snap.get("current_step") or "-"
            thinking_text = thinking_snap.get("current_thinking") or ""
            with st.expander(
                f"💭 Réflexion IA en direct — {active_fn} ({active_agent})",
                expanded=True,
            ):
                st.caption(f"Étape : **{active_step}** · Agent : `{active_agent}`")
                with st.container(height=160, border=True):
                    if thinking_text:
                        st.caption(thinking_text)
                    else:
                        st.caption(
                            "_En attente des premiers jetons de réflexion IA..._"
                        )
    else:
        st.success("✅ Toutes les fiches de la file de traitement sont prêtes.")

    if tracked_files:
        active_files_set = {j.get("filename") for j in active_jobs if j.get("filename")}
        progress_values = []
        rows_data = []
        for fn in tracked_files:
            rcp_doc = rcp_docs_by_file.get(fn)
            failed_job = failed_jobs_by_file.get(fn)
            if rcp_doc is None and failed_job is not None:
                err_msg = failed_job.get("error_message") or "Échec du traitement"
                status_label = f"❌ {err_msg}"
                pct = 100
                can_open = False
                patient_label = (
                    "Document non-RCP"
                    if "n'est pas une fiche RCP" in err_msg
                    else "Échec"
                )
                pid = None
                is_rejected = True
            elif rcp_doc is None and fn not in active_files_set:
                status_label = "❌ Document refusé (non-RCP)"
                pct = 100
                can_open = False
                patient_label = "Document non-RCP"
                pid = None
                is_rejected = True
            else:
                status_label, pct, can_open = _format_business_status(rcp_doc)
                patient_label = _resolve_patient_display_name(rcp_doc, patients_by_id)
                pid = rcp_doc.get("patient_id") if rcp_doc else None
                is_rejected = False
            progress_values.append(pct)
            rows_data.append(
                {
                    "file": fn,
                    "patient_label": patient_label,
                    "patient_id": pid,
                    "status_label": status_label,
                    "pct": pct,
                    "can_open": can_open,
                    "is_rejected": is_rejected,
                }
            )

        overall_pct = (
            int(sum(progress_values) / len(progress_values)) if progress_values else 100
        )
        st.progress(
            min(max(overall_pct, 0), 100) / 100.0,
            text=f"Avancement global du lot : {overall_pct}%",
        )

        for row in rows_data:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 3, 3, 2], vertical_alignment="center")
                c1.markdown(f"📄 `{row['file']}`")
                c2.markdown(f"👤 **{row['patient_label']}**")
                c3.markdown(row["status_label"])
                if row["can_open"]:
                    target_url = (
                        f"datas?patient_id={row['patient_id']}&file={row['file']}"
                        if row.get("patient_id")
                        else f"datas?file={row['file']}"
                    )
                    c4.link_button(
                        ":blue[:material/visibility:] Ouvrir le dossier",
                        target_url,
                        width="stretch",
                    )
                elif row.get("is_rejected"):
                    c4.caption("🚫 Document refusé")
                else:
                    c4.caption("⏳ Identification...")


def upload_view():
    title_c1, title_c2 = st.columns([4, 1], vertical_alignment="center")
    with title_c1:
        st.title("📥 Intégration documentaire (Multi-PDF)")
    with title_c2:
        if st.button(
            "◀️ Retour aux dossiers",
            width="stretch",
        ):
            st.switch_page(f"{PAGES_DIR_SRC}/patient_mdt/cards.py")

    st.caption(
        "Exhaustivité documentaire : intégrez une ou plusieurs pièces médicales au format PDF. "
        "Les documents sont traités séquentiellement (identification administrative du patient puis structuration clinique et contrôle de complétude)."
    )

    existing_patients = load_existing_patients()
    patient_options_map: dict[str, str | None] = {
        "✨ Automatique (Identification Prénom + Nom + Date de naissance)": None
    }
    for p in existing_patients:
        label = f"👤 {p.display_label} ({len(p.files)} RCP)"
        patient_options_map[label] = p.patient_id

    uploaded_files = st.file_uploader(
        "Choisir un ou plusieurs fichiers PDF",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.divider()
        st.subheader(f"⚙️ Configuration de l'import ({len(uploaded_files)} fichier(s))")

        col_global, col_full = st.columns([2, 1], vertical_alignment="center")
        with col_global:
            global_choice_label = st.selectbox(
                "Association patient par défaut",
                options=list(patient_options_map.keys()),
                index=0,
                help="En mode Automatique, le système extrait le prénom, le nom et la date de naissance pour créer ou rattacher le dossier patient.",
            )
            global_patient_id = patient_options_map[global_choice_label]

        with col_full:
            run_full_ai = st.checkbox(
                "Lancer aussi l'analyse clinique complète",
                value=True,
                help="Si coché (par défaut), l'identification du patient puis l'analyse clinique complète sont programmées dans la file de traitement.",
            )

        per_file_patient_ids: dict[str, str | None] = {}

        if len(uploaded_files) > 1:
            st.markdown("##### 📋 Attribution par fichier")
            follow_global_label = "🔄 Suivre le mode par défaut du lot"
            per_file_options = [follow_global_label] + list(patient_options_map.keys())

            header_cols = st.columns([3, 1, 4])
            header_cols[0].markdown("**Fichier PDF**")
            header_cols[1].markdown("**Taille**")
            header_cols[2].markdown("**Associer au patient**")

            for idx, uf in enumerate(uploaded_files):
                row_cols = st.columns([3, 1, 4], vertical_alignment="center")
                row_cols[0].markdown(f"📄 `{uf.name}`")
                size_kb = len(uf.getvalue()) / 1024
                row_cols[1].caption(f"{size_kb:.1f} Ko")
                file_choice = row_cols[2].selectbox(
                    f"Patient pour {uf.name}",
                    options=per_file_options,
                    index=0,
                    key=f"batch_patient_select_{idx}_{uf.name}",
                    label_visibility="collapsed",
                )
                if file_choice == follow_global_label:
                    per_file_patient_ids[uf.name] = global_patient_id
                else:
                    per_file_patient_ids[uf.name] = patient_options_map[file_choice]
        else:
            single_file = uploaded_files[0]
            per_file_patient_ids[single_file.name] = global_patient_id

        st.divider()
        btn_label = "🚀 Importer et ajouter à la file de traitement"

        if st.button(btn_label, type="primary", width="stretch"):
            os.makedirs(app_conf.rcp.path, exist_ok=True)
            extraction_service = _get_extraction_service()
            if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
                files_payload: list[dict] = []
                for uploaded_file in uploaded_files:
                    original_name = uploaded_file.name
                    target_patient_id = per_file_patient_ids.get(
                        original_name, global_patient_id
                    )
                    bytes_data = uploaded_file.getvalue()
                    filename, is_duplicate = extraction_service.resolve_upload(
                        bytes_data, original_name
                    )

                    if is_duplicate:
                        st.warning(
                            f"⚠️ Ce fichier (`{original_name}`) existe déjà sous le nom `{filename}`."
                        )
                        st.link_button(
                            "👁️ Voir la fiche existante",
                            f"datas?file={filename}",
                        )
                        continue

                    target_path = os.path.join(app_conf.rcp.path, filename)
                    with open(target_path, "wb") as pdf:
                        pdf.write(bytes_data)
                    files_payload.append(
                        {"filename": filename, "patient_id": target_patient_id}
                    )

                if files_payload:
                    enqueue_res = extraction_service.enqueue_batch(
                        files_payload=files_payload,
                        run_full_ai=run_full_ai,
                    )
                    st.session_state["last_upload_batch"] = {
                        "batch_id": enqueue_res["batch_id"],
                        "files": [f["filename"] for f in files_payload],
                    }
                    if enqueue_res.get("enqueued_count", 0) > 0:
                        st.toast(
                            f"✅ {enqueue_res['enqueued_count']} fiche(s) ajoutée(s) à la file de traitement",
                            icon="✅",
                        )
                    if enqueue_res.get("already_queued_count", 0) > 0:
                        st.toast(
                            f"ℹ️ {enqueue_res['already_queued_count']} fiche(s) déjà présente(s) dans la file de traitement",
                            icon="ℹ️",
                        )
            else:
                total = len(uploaded_files)
                progress_bar = st.progress(0, text="Initialisation de l'import...")
                batch_results: list[dict] = []

                for idx, uploaded_file in enumerate(uploaded_files):
                    original_name = uploaded_file.name
                    target_patient_id = per_file_patient_ids.get(
                        original_name, global_patient_id
                    )
                    progress_bar.progress(
                        idx / total,
                        text=f"Traitement de {original_name} ({idx + 1}/{total})...",
                    )
                    try:
                        bytes_data = uploaded_file.getvalue()
                        filename, is_duplicate = extraction_service.resolve_upload(
                            bytes_data, original_name
                        )
                        if is_duplicate:
                            st.warning(
                                f"⚠️ Ce fichier (`{original_name}`) existe déjà sous le nom `{filename}`."
                            )
                            st.link_button(
                                "👁️ Voir la fiche existante",
                                f"datas?file={filename}",
                            )
                            batch_results.append(
                                {
                                    "file": filename,
                                    "patient_id": "",
                                    "patient_label": "Déjà existant",
                                    "status": "⚠️ Doublon",
                                }
                            )
                            continue

                        target_path = os.path.join(app_conf.rcp.path, filename)
                        with open(target_path, "wb") as pdf:
                            pdf.write(bytes_data)

                        _, patient_dict = extraction_service.ingest_and_associate(
                            filename=filename,
                            patient_id=target_patient_id,
                        )
                        if run_full_ai:
                            extraction_service.extract_all_sections(filename=filename)
                        patient_obj = (
                            Patient.from_persistence(patient_dict)
                            if patient_dict
                            else None
                        )
                        patient_label = (
                            patient_obj.display_label
                            if patient_obj
                            else (target_patient_id or "Inconnu")
                        )
                        resolved_pid = (
                            patient_obj.patient_id
                            if patient_obj
                            else (target_patient_id or "")
                        )
                        batch_results.append(
                            {
                                "file": filename,
                                "patient_id": resolved_pid,
                                "patient_label": patient_label,
                                "status": "✅ Succès",
                            }
                        )
                    except NonPatientMDTFormError as e:
                        logger.warning(f"Document refusé ({original_name}): {e}")
                        st.error(f"🚫 `{original_name}` : {e}")
                        batch_results.append(
                            {
                                "file": original_name,
                                "patient_id": "",
                                "patient_label": "Document non-RCP",
                                "status": "❌ Refusé (non-RCP)",
                            }
                        )
                    except Exception as e:
                        logger.error(f"Erreur lors de l'import de {original_name}: {e}")
                        st.error(f"Erreur sur `{original_name}` : {e}")

                progress_bar.progress(1.0, text="Import terminé !")
                st.session_state["last_upload_results"] = batch_results

    render_upload_queue_tracker()


if __name__ == "__main__":
    upload_view()
