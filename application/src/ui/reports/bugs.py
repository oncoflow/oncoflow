from datetime import datetime

import streamlit as st

from src.application.config import AppConfig
from src.domain.bug_report import BugCategory, BugReport, BugSeverity, BugStatus
from src.domain.patient import Patient
from src.infrastructure.documents.mongodb import Mongodb

app_conf = AppConfig()
logger = app_conf.set_logger("ui", default_context={"page": "bugs"})

PAGE_OPTIONS = [
    "Général",
    "Dossiers Patients",
    "Dossier Patient",
    "Charger le/les fichier(s)",
    "Agents and ressources",
    "Ressources",
    "Autre",
]

SEVERITY_BADGES = {
    BugSeverity.critical.value: ":red-badge[🚨 Critique]",
    BugSeverity.high.value: ":orange-badge[🟠 Élevé]",
    BugSeverity.medium.value: ":blue-badge[🟡 Moyen]",
    BugSeverity.low.value: ":green-badge[🟢 Faible]",
}

STATUS_BADGES = {
    BugStatus.open.value: ":red-badge[🔴 Ouvert]",
    BugStatus.in_progress.value: ":orange-badge[⏳ En cours]",
    BugStatus.resolved.value: ":green-badge[✅ Résolu]",
    BugStatus.closed.value: ":gray-badge[🔒 Fermé]",
}


def _get_db_client() -> Mongodb | None:
    if app_conf.rcp.display_type != "mongodb":
        return None
    return Mongodb(app_conf)


def _load_context_options(
    db_client: Mongodb | None,
) -> tuple[dict[str, str | None], list[str]]:
    """Charge la liste des patients et des fichiers RCP disponibles pour enrichir le rapport de bug."""
    patient_map: dict[str, str | None] = {"Aucun": None}
    rcp_files: list[str] = ["Aucune"]

    if db_client is None or not hasattr(db_client, "database"):
        return patient_map, rcp_files

    try:
        for raw_p in db_client.get_all_patients():
            try:
                p = Patient.model_validate(raw_p)
                patient_map[f"{p.display_label} ({p.patient_id})"] = p.patient_id
            except Exception:
                continue

        rcp_docs = list(db_client.database["rcp_info"].find({}, {"file": 1}))
        files = sorted({d["file"] for d in rcp_docs if d.get("file")})
        rcp_files.extend(files)
    except Exception as e:
        logger.warning(f"Impossible de charger le contexte patients/RCP : {e}")

    return patient_map, rcp_files


@st.dialog("Confirmation de suppression du signalement")
def confirm_delete_bug(bug_id: str, title: str):
    st.warning(
        f"Voulez-vous vraiment supprimer le signalement **{title}** (`{bug_id}`) ?"
    )
    st.markdown("Cette action est irréversible.")
    if st.button("Confirmer la suppression", type="primary"):
        client = _get_db_client()
        if client is not None:
            try:
                client.delete_bug_report(bug_id)
                st.toast(f"Signalement {bug_id} supprimé.", icon="🗑️")
            finally:
                client.close()
        st.rerun()


def render_bug_form(db_client: Mongodb | None):
    """Affiche le formulaire de création d'un nouveau rapport de bug."""
    st.subheader("📝 Nouveau signalement")
    st.caption(
        "Signalez une anomalie technique, une erreur d'extraction IA ou proposez une amélioration clinique."
    )

    patient_map, rcp_files = _load_context_options(db_client)
    category_labels = BugCategory.labels()
    severity_labels = BugSeverity.labels()

    default_reporter = (
        st.session_state.get("name") or st.session_state.get("username") or "Anonyme"
    )

    with st.form("bug_report_form", clear_on_submit=True):
        title = st.text_input(
            "Titre du signalement *",
            placeholder="Ex : Mauvaise extraction de la date de naissance sur la fiche RCP...",
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            selected_category = st.selectbox(
                "Catégorie",
                options=list(BugCategory),
                format_func=lambda x: category_labels.get(x, x.value),
                index=0,
            )
        with c2:
            selected_severity = st.selectbox(
                "Sévérité",
                options=list(BugSeverity),
                format_func=lambda x: severity_labels.get(x, x.value),
                index=1,  # Moyen par défaut
            )
        with c3:
            selected_page = st.selectbox(
                "Page / Composant concerné",
                options=PAGE_OPTIONS,
                index=0,
            )

        ctx1, ctx2, ctx3 = st.columns(3)
        with ctx1:
            selected_patient_label = st.selectbox(
                "Dossier Patient associé (optionnel)",
                options=list(patient_map.keys()),
                index=0,
            )
        with ctx2:
            selected_rcp_file = st.selectbox(
                "Fiche RCP associée (optionnel)",
                options=rcp_files,
                index=0,
            )
        with ctx3:
            reporter = st.text_input(
                "Signalé par",
                value=str(default_reporter),
            )

        description = st.text_area(
            "Description détaillée *",
            height=130,
            placeholder="Décrivez précisément le problème rencontré, le résultat observé et le contexte clinique ou technique...",
        )

        steps_to_reproduce = st.text_area(
            "Étapes pour reproduire / Comportement attendu (optionnel)",
            height=90,
            placeholder="1. Ouvrir le dossier...\n2. Cliquer sur...\nComportement attendu : ...",
        )

        submitted = st.form_submit_button(
            "📨 Envoyer le signalement",
            type="primary",
            width="stretch",
        )

        if submitted:
            if not title.strip() or not description.strip():
                st.error(
                    "Veuillez renseigner au minimum le **titre** et la **description** du signalement."
                )
            elif db_client is None:
                st.error("La connexion MongoDB n'est pas disponible.")
            else:
                try:
                    report = BugReport(
                        title=title.strip(),
                        description=description.strip(),
                        category=selected_category,
                        severity=selected_severity,
                        status=BugStatus.open,
                        page=selected_page,
                        patient_id=patient_map.get(selected_patient_label),
                        rcp_file=(
                            None if selected_rcp_file == "Aucune" else selected_rcp_file
                        ),
                        steps_to_reproduce=steps_to_reproduce.strip() or None,
                        reporter=reporter.strip() or "Anonyme",
                    )
                    saved = db_client.create_bug_report(report.model_dump())
                    st.toast(
                        f"Signalement {saved['bug_id']} enregistré avec succès !",
                        icon="✅",
                    )
                    st.success(
                        f"✅ Votre signalement **`{saved['bug_id']}`** (*{saved['title']}*) a bien été enregistré dans MongoDB."
                    )
                except Exception as e:
                    logger.error(f"Erreur lors de l'enregistrement du bug report : {e}")
                    st.error(f"Erreur lors de l'enregistrement du signalement : {e}")


def render_bug_list(db_client: Mongodb | None):
    """Affiche la liste filtrable des rapports de bugs stockés dans MongoDB."""
    if db_client is None:
        st.warning("La base de données MongoDB n'est pas configurée.")
        return

    try:
        all_bugs = db_client.get_all_bug_reports()
    except Exception as e:
        logger.error(f"Erreur lors de la lecture des bugs depuis MongoDB : {e}")
        st.error(f"Impossible de récupérer les signalements depuis MongoDB : {e}")
        return

    category_labels = {k.value: v for k, v in BugCategory.labels().items()}
    severity_labels = {k.value: v for k, v in BugSeverity.labels().items()}
    status_labels = {k.value: v for k, v in BugStatus.labels().items()}

    # --- Métriques synthétiques ---
    total_count = len(all_bugs)
    open_count = sum(1 for b in all_bugs if b.get("status") == BugStatus.open.value)
    progress_count = sum(
        1 for b in all_bugs if b.get("status") == BugStatus.in_progress.value
    )
    resolved_count = sum(
        1
        for b in all_bugs
        if b.get("status") in (BugStatus.resolved.value, BugStatus.closed.value)
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total signalements", total_count)
    m2.metric("🔴 Ouverts", open_count)
    m3.metric("⏳ En cours", progress_count)
    m4.metric("✅ Résolus / Fermés", resolved_count)

    st.divider()

    if not all_bugs:
        st.info("Aucun signalement de bug enregistré pour le moment.")
        return

    # --- Filtres ---
    f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
    with f1:
        search_term = st.text_input(
            "Rechercher",
            placeholder="Titre, description, ID, auteur, fichier...",
        )
    with f2:
        status_filter = st.selectbox(
            "Statut",
            options=["Tous"] + [s.value for s in BugStatus],
            format_func=lambda v: "Tous" if v == "Tous" else status_labels.get(v, v),
        )
    with f3:
        severity_filter = st.selectbox(
            "Sévérité",
            options=["Toutes"] + [s.value for s in BugSeverity],
            format_func=lambda v: (
                "Toutes" if v == "Toutes" else severity_labels.get(v, v)
            ),
        )
    with f4:
        category_filter = st.selectbox(
            "Catégorie",
            options=["Toutes"] + [c.value for c in BugCategory],
            format_func=lambda v: (
                "Toutes" if v == "Toutes" else category_labels.get(v, v)
            ),
        )

    filtered_bugs = []
    for bug in all_bugs:
        if status_filter != "Tous" and bug.get("status") != status_filter:
            continue
        if severity_filter != "Toutes" and bug.get("severity") != severity_filter:
            continue
        if category_filter != "Toutes" and bug.get("category") != category_filter:
            continue
        if search_term:
            term = search_term.lower()
            searchable = " ".join(
                str(bug.get(k) or "")
                for k in (
                    "bug_id",
                    "title",
                    "description",
                    "reporter",
                    "patient_id",
                    "rcp_file",
                    "page",
                )
            ).lower()
            if term not in searchable:
                continue
        filtered_bugs.append(bug)

    st.caption(f"{len(filtered_bugs)} signalement(s) affiché(s)")

    for bug in filtered_bugs:
        bug_id = bug.get("bug_id", "unknown")
        title = bug.get("title", "Sans titre")
        sev = bug.get("severity", BugSeverity.medium.value)
        stat = bug.get("status", BugStatus.open.value)
        cat = bug.get("category", BugCategory.other.value)
        created_at = bug.get("created_at")
        date_str = (
            created_at.strftime("%d/%m/%Y %H:%M")
            if isinstance(created_at, datetime)
            else str(created_at or "Inconnue")
        )

        with st.container(border=True):
            top_left, top_right = st.columns([4, 2], vertical_alignment="center")
            with top_left:
                st.subheader(f"{title}")
                badges = [
                    SEVERITY_BADGES.get(sev, f":blue-badge[{sev}]"),
                    STATUS_BADGES.get(stat, f":gray-badge[{stat}]"),
                    f":violet-badge[🏷️ {category_labels.get(cat, cat)}]",
                ]
                if bug.get("page"):
                    badges.append(f":gray-badge[📍 {bug['page']}]")
                st.markdown(" ".join(badges))

                meta_parts = [
                    f"🆔 `{bug_id}`",
                    f"📅 {date_str}",
                    f"👤 **{bug.get('reporter') or 'Anonyme'}**",
                ]
                if bug.get("patient_id"):
                    meta_parts.append(f"🗂️ Patient : `{bug['patient_id']}`")
                if bug.get("rcp_file"):
                    meta_parts.append(f"📄 RCP : `{bug['rcp_file']}`")
                st.caption(" · ".join(meta_parts))

            with top_right:
                act1, act2 = st.columns([3, 1], vertical_alignment="center")
                status_options = [s.value for s in BugStatus]
                current_idx = (
                    status_options.index(stat) if stat in status_options else 0
                )
                new_status = act1.selectbox(
                    "Changer le statut",
                    options=status_options,
                    index=current_idx,
                    format_func=lambda v: status_labels.get(v, v),
                    key=f"status_select_{bug_id}",
                    label_visibility="collapsed",
                )
                if new_status != stat:
                    db_client.update_bug_report(bug_id, {"status": new_status})
                    st.toast(
                        f"Statut de {bug_id} mis à jour : {status_labels.get(new_status, new_status)}",
                        icon="🔄",
                    )
                    st.rerun()

                if act2.button(
                    "🗑️",
                    key=f"del_bug_{bug_id}",
                    type="primary",
                    width="stretch",
                    help="Supprimer ce signalement",
                ):
                    confirm_delete_bug(bug_id, title)

            st.markdown(bug.get("description", ""))

            if bug.get("steps_to_reproduce"):
                with st.expander("🔍 Étapes pour reproduire / Comportement attendu"):
                    st.markdown(bug["steps_to_reproduce"])


def bugs_view():
    st.title("🐛 Bug Reports & Retours Utilisateurs")

    db_client = _get_db_client()
    try:
        tab_new, tab_list = st.tabs(
            ["➕ Signaler un bug", "📋 Historique des signalements"]
        )
        with tab_new:
            render_bug_form(db_client)
        with tab_list:
            render_bug_list(db_client)
    finally:
        if db_client is not None:
            db_client.close()


bugs_view()
