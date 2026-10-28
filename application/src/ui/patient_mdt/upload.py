import os
import streamlit as st

from src.application.config import AppConfig
from src.application.app_functions import (
    full_read_mtd_agents,
    ingest_and_associate_rcp,
    resolve_rcp_upload,
)
from src.domain.patient import Patient
from src.infrastructure.documents.mongodb import Mongodb


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


def upload_view():
    st.title("🚀 Importer des fiches RCP")
    st.caption(
        "Téléversez une ou plusieurs fiches RCP au format PDF. "
        "Par défaut, l'indexation RAG et l'extraction administrative IA identifient ou créent automatiquement le dossier patient (Prénom, Nom, Date de naissance)."
    )

    existing_patients = load_existing_patients()
    patient_options_map: dict[str, str | None] = {
        "✨ Automatique (IA Administrative : Prénom + Nom + Date de naissance)": None
    }
    for p in existing_patients:
        label = f"👤 {p.display_label} ({len(p.files)} RCP)"
        patient_options_map[label] = p.patient_id

    uploaded_files = st.file_uploader(
        "Choisir un ou plusieurs fichiers PDF",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        return

    st.divider()
    st.subheader(f"⚙️ Configuration de l'import ({len(uploaded_files)} fichier(s))")

    col_global, col_full = st.columns([2, 1], vertical_alignment="center")
    with col_global:
        global_choice_label = st.selectbox(
            "Association patient par défaut",
            options=list(patient_options_map.keys()),
            index=0,
            help="En mode Automatique, l'IA extrait le prénom, le nom et la date de naissance pour créer ou rattacher le dossier patient.",
        )
        global_patient_id = patient_options_map[global_choice_label]

    with col_full:
        run_full_ai = st.checkbox(
            "Lancer aussi l'analyse clinique complète",
            value=False,
            help="Si décoché (par défaut), seuls le RAG et l'extraction administrative du patient sont exécutés à l'import.",
        )

    per_file_patient_ids: dict[int, str | None] = {}

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
                per_file_patient_ids[idx] = global_patient_id
            else:
                per_file_patient_ids[idx] = patient_options_map[file_choice]
    else:
        per_file_patient_ids[0] = global_patient_id

    st.divider()
    btn_label = (
        "🚀 Importer et associer le lot"
        if len(uploaded_files) > 1
        else "🚀 Importer et associer la fiche RCP"
    )

    if st.button(btn_label, type="primary", width="stretch"):
        os.makedirs(app_conf.rcp.path, exist_ok=True)
        total = len(uploaded_files)
        progress_bar = st.progress(0, text="Initialisation de l'import...")
        batch_results: list[dict] = []

        for idx, uploaded_file in enumerate(uploaded_files):
            original_name = uploaded_file.name
            target_patient_id = per_file_patient_ids.get(idx, global_patient_id)
            mode_label = (
                "Auto (IA Administrative)"
                if target_patient_id is None
                else f"Patient existant ({target_patient_id})"
            )

            progress_bar.progress(
                idx / total,
                text=f"Traitement de {original_name} ({idx + 1}/{total}) — {mode_label}...",
            )

            with st.status(
                f"📄 [{idx + 1}/{total}] {original_name} — {mode_label}",
                expanded=(total == 1),
            ) as status:
                try:
                    bytes_data = uploaded_file.getvalue()
                    filename, is_duplicate = resolve_rcp_upload(
                        app_conf, bytes_data, original_name
                    )

                    if is_duplicate:
                        st.warning(
                            f"⚠️ Ce fichier existe déjà sous le nom `{filename}`."
                        )
                        st.link_button(
                            "👁️ Voir la fiche existante",
                            f"datas?file={filename}",
                        )
                        status.update(
                            label=f"⚠️ [{idx + 1}/{total}] {original_name} — Déjà existant ({filename})",
                            state="complete",
                            expanded=True,
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
                    st.write(f"💾 Enregistrement du PDF `{filename}`...")
                    with open(target_path, "wb") as pdf:
                        pdf.write(bytes_data)

                    st.write(
                        "🔍 Indexation RAG & extraction administrative du patient..."
                    )
                    _, patient_dict = ingest_and_associate_rcp(
                        app_conf=app_conf,
                        filename=filename,
                        patient_id=target_patient_id,
                    )

                    if run_full_ai:
                        st.write("🤖 Exécution de l'analyse clinique complète...")
                        full_read_mtd_agents(
                            app_conf=app_conf,
                            filename=filename,
                            logger=logger,
                        )

                    patient_obj = (
                        Patient.model_validate(patient_dict) if patient_dict else None
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

                    status.update(
                        label=f"✅ [{idx + 1}/{total}] {filename} → {patient_label}",
                        state="complete",
                        expanded=False,
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
                    status.update(
                        label=f"❌ [{idx + 1}/{total}] {original_name} — Erreur",
                        state="error",
                        expanded=True,
                    )
                    st.error(f"Erreur sur `{original_name}` : {e}")
                    batch_results.append(
                        {
                            "file": original_name,
                            "patient_id": target_patient_id or "",
                            "patient_label": "Erreur",
                            "status": f"❌ {e}",
                        }
                    )

        progress_bar.progress(1.0, text="Import terminé !")
        st.session_state["last_upload_results"] = batch_results

        # Si un seul fichier a été importé avec succès, rediriger directement vers son dossier patient
        if len(batch_results) == 1 and batch_results[0]["status"] == "✅ Succès":
            res = batch_results[0]
            query_params = {"file": res["file"]}
            if res["patient_id"]:
                query_params["patient_id"] = res["patient_id"]
            st.switch_page(
                f"{PAGES_DIR_SRC}/patient_mdt/datas.py",
                query_params=query_params,
            )

    # Affichage du récapitulatif du dernier lot importé
    if st.session_state.get("last_upload_results"):
        results = st.session_state["last_upload_results"]
        st.divider()
        st.subheader("📊 Récapitulatif de l'import")
        for res in results:
            c1, c2, c3, c4 = st.columns([3, 3, 2, 2], vertical_alignment="center")
            c1.markdown(f"📄 `{res['file']}`")
            c2.markdown(f"👤 **{res['patient_label']}**")
            c3.markdown(res["status"])
            if res.get("patient_id"):
                c4.link_button(
                    "👁️ Ouvrir le dossier",
                    f"datas?patient_id={res['patient_id']}&file={res['file']}",
                    width="stretch",
                )
            else:
                c4.link_button(
                    "👁️ Ouvrir la RCP",
                    f"datas?file={res['file']}",
                    width="stretch",
                )


if __name__ == "__main__":
    upload_view()
