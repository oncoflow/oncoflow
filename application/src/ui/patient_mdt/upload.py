import os
import streamlit as st

from src.application.config import AppConfig
from src.application.app_functions import (
    enqueue_rcp_batch,
    full_read_mtd_agents,
    ingest_and_associate_rcp,
    resolve_rcp_upload,
)
from src.domain.patient import Patient
from src.domain.worker import RCPProcessingStatus
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.queue import SqliteQueueBroker


app_conf = AppConfig()
PAGES_DIR_SRC = "src/ui"
logger = app_conf.set_logger("ui", default_context={"page": "upload"})


def load_existing_patients() -> list[Patient]:
    """Charge la liste des patients existants depuis MongoDB."""
    if app_conf.rcp.display_type != "mongodb":
        return []
    db_client = Mongodb(app_conf)
    try:
        raw_patients = db_client.get_all_patients()
        patients = []
        for raw in raw_patients:
            try:
                patients.append(Patient.model_validate(raw))
            except Exception as e:
                logger.warning(f"Impossible de valider le patient {raw}: {e}")
        return patients
    finally:
        db_client.close()


def _format_business_status(rcp_doc: dict | None) -> tuple[str, int, bool]:
    """
    Traduit l'état du document RCP en libellé purement métier, pourcentage d'avancement
    et indicateur d'ouverture du dossier patient.
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
    Affiche en temps réel l'avancement de la file de traitement en langage métier
    sans aucun élément technique.
    """
    if app_conf.rcp.display_type != "mongodb":
        return

    broker = SqliteQueueBroker(app_conf)
    db_client = Mongodb(app_conf)
    try:
        stats = broker.get_queue_stats()
        active_jobs = broker.get_queue_jobs(
            status="PENDING", limit=100
        ) + broker.get_queue_jobs(status="PROCESSING", limit=100)
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
            docs = list(
                db_client.database["rcp_info"].find(
                    {"file": {"$in": tracked_files}},
                    {
                        "file": 1,
                        "patient_id": 1,
                        "PatientAdministrative": 1,
                        "processing_status": 1,
                        "processing_step": 1,
                        "processing_progress_pct": 1,
                    },
                )
            )
            rcp_docs_by_file = {d["file"]: d for d in docs if "file" in d}

        raw_patients = db_client.get_all_patients()
        patients_by_id: dict[str, Patient] = {}
        for raw in raw_patients:
            try:
                p = Patient.model_validate(raw)
                patients_by_id[p.patient_id] = p
            except Exception:
                continue
    finally:
        broker.close()
        db_client.close()

    st.divider()
    st.subheader("⏳ Suivi de la file de traitement")

    active_total = stats["pending"] + stats["processing"]
    if active_total > 0:
        st.info(
            f"📋 **{stats['processing']}** fiche(s) en cours de traitement • "
            f"**{stats['pending']}** tâche(s) en attente dans la file de traitement"
        )
    else:
        st.success("✅ Toutes les fiches de la file de traitement sont prêtes.")

    if tracked_files:
        progress_values = []
        rows_data = []
        for fn in tracked_files:
            rcp_doc = rcp_docs_by_file.get(fn)
            status_label, pct, can_open = _format_business_status(rcp_doc)
            patient_label = _resolve_patient_display_name(rcp_doc, patients_by_id)
            pid = rcp_doc.get("patient_id") if rcp_doc else None
            progress_values.append(pct)
            rows_data.append(
                {
                    "file": fn,
                    "patient_label": patient_label,
                    "patient_id": pid,
                    "status_label": status_label,
                    "pct": pct,
                    "can_open": can_open,
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
                    "👁️ Ouvrir le dossier",
                    target_url,
                    width="stretch",
                )
            else:
                c4.caption("⏳ Identification...")


def upload_view():
    st.title("🚀 Importer des fiches RCP")
    st.caption(
        "Téléversez une ou plusieurs fiches RCP au format PDF. "
        "Les fiches importées sont ajoutées à la file de traitement : les patients sont d'abord identifiés sur l'ensemble du lot, puis l'analyse clinique complète chaque dossier."
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
            if app_conf.queue.enabled and app_conf.rcp.display_type == "mongodb":
                files_payload: list[dict] = []
                for uploaded_file in uploaded_files:
                    original_name = uploaded_file.name
                    target_patient_id = per_file_patient_ids.get(
                        original_name, global_patient_id
                    )
                    bytes_data = uploaded_file.getvalue()
                    filename, is_duplicate = resolve_rcp_upload(
                        app_conf, bytes_data, original_name
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
                    enqueue_res = enqueue_rcp_batch(
                        app_conf=app_conf,
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
                        filename, is_duplicate = resolve_rcp_upload(
                            app_conf, bytes_data, original_name
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

                        _, patient_dict = ingest_and_associate_rcp(
                            app_conf=app_conf,
                            filename=filename,
                            patient_id=target_patient_id,
                        )
                        if run_full_ai:
                            full_read_mtd_agents(
                                app_conf=app_conf,
                                filename=filename,
                                logger=logger,
                            )
                        patient_obj = (
                            Patient.model_validate(patient_dict)
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
                    except Exception as e:
                        logger.error(f"Erreur lors de l'import de {original_name}: {e}")
                        st.error(f"Erreur sur `{original_name}` : {e}")

                progress_bar.progress(1.0, text="Import terminé !")
                st.session_state["last_upload_results"] = batch_results

    render_upload_queue_tracker()


if __name__ == "__main__":
    upload_view()
