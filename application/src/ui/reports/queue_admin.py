from datetime import datetime

import streamlit as st

from src.application.config import AppConfig
from src.domain.worker import JobStatus, JobType
from src.infrastructure.queue import QueueBroker

app_conf = AppConfig()
logger = app_conf.set_logger("ui", default_context={"page": "queue_admin"})

STATUS_BADGES = {
    JobStatus.PENDING.value: ":blue-badge[⏳ En attente]",
    JobStatus.PROCESSING.value: ":orange-badge[🔄 En cours]",
    JobStatus.COMPLETED.value: ":green-badge[✅ Terminée]",
    JobStatus.FAILED.value: ":red-badge[❌ Échec]",
    JobStatus.CANCELLED.value: ":gray-badge[🚫 Annulée]",
}

JOB_TYPE_LABELS = {
    JobType.WAVE1_ADMIN.value: "Identification patient (Vague 1)",
    JobType.WAVE2_CLINICAL.value: "Extraction clinique (Vague 2)",
    JobType.WAVE3_EXPERTS.value: "Concertation d'experts (Vague 3)",
    JobType.SINGLE_MODEL.value: "Relance rubrique unitaire",
}


def _get_broker() -> QueueBroker:
    return QueueBroker(app_conf)


@st.dialog("Confirmation de purge intégrale de la file")
def confirm_full_queue_purge(cross_domain: bool = True):
    st.error(
        "Voulez-vous vraiment **vider intégralement la file de traitement** et **lever tous les verrous actifs** ?",
        icon=":material/warning:",
    )
    st.caption(
        "Toutes les tâches (en attente, en cours, terminées ou en échec) seront supprimées et les verrous seront immédiatement libérés. Cette action est irréversible."
    )
    if st.button(
        "Confirmer la purge intégrale",
        type="primary",
        icon=":material/delete_forever:",
        key="btn_danger_confirm_purge_all",
        width="stretch",
    ):
        broker = _get_broker()
        try:
            res = broker.clean_queue(mode="all", cross_domain=cross_domain)
            unlocked = broker.release_gpu_lease(force_all=True)
            st.toast(
                f"File purgée ({res['affected_jobs']} tâche(s), {unlocked} verrou(s) levé(s)).",
                icon="🧹",
            )
        finally:
            broker.close()
        st.rerun()


@st.fragment(run_every="2s")
def render_live_thinking_section(cross_domain: bool = True):
    """Render a live auto-refreshing panel streaming the AI reasoning of the active queue task."""
    broker = _get_broker()
    try:
        thinking_snap = broker.get_job_thinking(cross_domain=cross_domain)
    finally:
        broker.close()

    st.subheader("💭 Réflexion IA en direct (Tâche en cours)")
    if not thinking_snap.get("active"):
        st.info("Aucune tâche en cours de raisonnement IA actuellement.")
        return

    filename = thinking_snap.get("filename") or "-"
    domain = thinking_snap.get("domain") or app_conf.domain
    job_id = thinking_snap.get("job_id") or "-"
    step = thinking_snap.get("current_step") or "-"
    active_agent = thinking_snap.get("active_agent") or "Initialisation de l'agent..."
    progress_pct = int(thinking_snap.get("progress_pct") or 0)
    thinking_text = thinking_snap.get("current_thinking") or ""

    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 3, 2], vertical_alignment="center")
        c1.markdown(f"📄 **`{filename}`** (`{domain}`) · 🆔 `{job_id}`")
        c2.markdown(f"🤖 **Agent actif :** `{active_agent}`")
        c3.markdown(f":orange-badge[🔄 {step} ({progress_pct}%)]")
        st.progress(min(max(progress_pct, 5), 100) / 100.0)
        with st.container(height=220, border=True):
            if thinking_text:
                st.caption(thinking_text)
            else:
                st.caption("_En attente des premiers jetons de réflexion IA..._")


def render_locks_section(db_client: QueueBroker):
    st.subheader("🔒 Gestion des Verrous d'Exécution")
    st.caption(
        "La file `PriorityQueue` centrale régule automatiquement les traitements selon la capacité configurée "
        f"sur les domaines autorisés (`{', '.join(app_conf.enabled_domains_list)}`)."
    )

    leases = db_client.get_all_gpu_leases()
    top_c1, top_c2 = st.columns([4, 2], vertical_alignment="center")
    top_c1.markdown(
        f"**Emplacements actifs :** `{len(leases)} / {app_conf.queue.batch_size}` "
        f"(Domaines actifs : `{', '.join(app_conf.enabled_domains_list)}`)"
    )
    if top_c2.button(
        "🔓 Lever tous les verrous",
        type="primary",
        width="stretch",
        disabled=(len(leases) == 0),
        key="btn_force_unlock_all",
    ):
        removed = db_client.release_gpu_lease(force_all=True)
        st.toast(f"{removed} verrou(s) levé(s).", icon="🔓")
        st.rerun()

    if not leases:
        st.success("✅ Aucun verrou actif actuellement.")
        return

    for lease in leases:
        lease_id = lease.get("lease_id", "")
        worker_id = lease.get("worker_id", "inconnu")
        domain = lease.get("domain", "inconnu")
        job_id = lease.get("job_id", "inconnu")
        acq = lease.get("acquired_at")
        exp = lease.get("expires_at")
        acq_str = (
            acq.strftime("%d/%m/%Y %H:%M:%S")
            if isinstance(acq, datetime)
            else str(acq or "-")
        )
        exp_str = (
            exp.strftime("%d/%m/%Y %H:%M:%S")
            if isinstance(exp, datetime)
            else str(exp or "-")
        )

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 3, 3, 2], vertical_alignment="center")
            c1.markdown(f"🔑 **Verrou :** `{lease_id}`  \n🌐 **Domaine :** `{domain}`")
            c2.markdown(f"⚙️ **Agent :** `{worker_id}`  \n📋 **Tâche :** `{job_id}`")
            c3.caption(f"Acquis : {acq_str}  \nExpire : {exp_str}")
            if c4.button(
                "🔓 Lever ce verrou",
                key=f"btn_unlock_{lease_id}",
                width="stretch",
            ):
                db_client.release_gpu_lease(lease_id=lease_id)
                st.toast(f"Verrou {lease_id} levé.", icon="🔓")
                st.rerun()


def render_maintenance_actions(db_client: QueueBroker, cross_domain: bool = True):
    st.subheader("🧹 Actions de Nettoyage de la File")
    c1, c2, c3, c4, c5 = st.columns(5)

    if c1.button(
        ":material/delete_sweep: Purger terminées",
        help="Supprime définitivement les tâches terminées ou annulées de l'historique",
        width="stretch",
        key="btn_del_purge_completed",
    ):
        res = db_client.clean_queue(mode="completed", cross_domain=cross_domain)
        st.toast(
            f"{res['affected_jobs']} tâche(s) terminée(s) supprimée(s).",
            icon="🧹",
        )
        st.rerun()

    if c2.button(
        "🔄 Débloquer en cours",
        help="Remet en attente les tâches bloquées à l'état EN COURS et lève les verrous",
        width="stretch",
    ):
        res = db_client.clean_queue(mode="reset_stuck", cross_domain=cross_domain)
        st.toast(
            f"{res['affected_jobs']} tâche(s) remise(s) en attente et verrous libérés.",
            icon="🔄",
        )
        st.rerun()

    if c3.button(
        "🔁 Relancer échecs",
        help="Remet en file d'attente toutes les tâches en échec",
        width="stretch",
    ):
        res = db_client.clean_queue(mode="retry_failed", cross_domain=cross_domain)
        st.toast(f"{res['affected_jobs']} tâche(s) en échec relancée(s).", icon="🔁")
        st.rerun()

    if c4.button(
        ":material/delete: Vider en attente",
        help="Supprime définitivement toutes les tâches en attente non démarrées",
        width="stretch",
        key="btn_del_purge_pending",
    ):
        res = db_client.clean_queue(mode="pending", cross_domain=cross_domain)
        st.toast(f"{res['affected_jobs']} tâche(s) en attente supprimée(s).", icon="🗑️")
        st.rerun()

    if c5.button(
        ":material/delete_forever: Tout vider",
        type="primary",
        help="Purge intégralement la file de traitement et lève tous les verrous (action irréversible)",
        width="stretch",
        key="btn_danger_purge_all",
    ):
        confirm_full_queue_purge(cross_domain=cross_domain)


def render_jobs_table(db_client: QueueBroker, cross_domain: bool = True):
    st.subheader("📋 Tâches de la File de Traitement")

    f1, f2, f3 = st.columns([2, 3, 1], vertical_alignment="bottom")
    with f1:
        status_filter = st.selectbox(
            "Filtrer par statut",
            options=["Tous"] + [s.value for s in JobStatus],
            index=0,
        )
    with f2:
        search_file = st.text_input(
            "Rechercher un fichier ou un identifiant de tâche",
            placeholder="Ex: rcp_patient1.pdf, job-...",
        )
    with f3:
        if st.button("🔄 Actualiser", width="stretch", key="btn_refresh_admin_jobs"):
            st.rerun()

    status_val = None if status_filter == "Tous" else status_filter
    jobs = db_client.get_queue_jobs(
        status=status_val, limit=200, cross_domain=cross_domain
    )

    if search_file:
        q = search_file.lower().strip()
        jobs = [
            j
            for j in jobs
            if q in str(j.get("filename", "")).lower()
            or q in str(j.get("job_id", "")).lower()
            or q in str(j.get("batch_id", "")).lower()
            or q in str(j.get("domain", "")).lower()
        ]

    if not jobs:
        st.info("Aucune tâche ne correspond aux critères sélectionnés.")
        return

    st.caption(f"{len(jobs)} tâche(s) affichée(s)")

    for job in jobs:
        job_id = job.get("job_id", "")
        filename = job.get("filename", "Inconnu")
        job_domain = job.get("domain", app_conf.domain)
        status = job.get("status", JobStatus.PENDING.value)
        job_type = job.get("job_type", "")
        type_label = JOB_TYPE_LABELS.get(job_type, job_type)
        target_model = job.get("model_name")
        if target_model:
            type_label = f"{type_label} (`{target_model}`)"
        current_step = job.get("current_step") or "-"
        progress_pct = int(job.get("progress_pct") or 0)
        attempts = job.get("attempts", 0)
        max_attempts = job.get("max_retries", 2)
        created_at = job.get("created_at")
        created_str = (
            created_at.strftime("%d/%m/%Y %H:%M:%S")
            if isinstance(created_at, datetime)
            else str(created_at or "-")
        )
        error_msg = job.get("error_message")

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 3, 2, 2], vertical_alignment="center")
            with c1:
                st.markdown(f"📄 **`{filename}`** (`{job_domain}`)")
                st.caption(f"🆔 `{job_id}` · 📅 {created_str}")
            with c2:
                st.markdown(f"**{type_label}**")
                st.caption(
                    f"Étape : {current_step} ({progress_pct}%) · Tentatives : {attempts}/{max_attempts}"
                )
            with c3:
                badge = STATUS_BADGES.get(status, f":gray-badge[{status}]")
                st.markdown(badge)
            with c4:
                b1, b2 = st.columns(2)
                if b1.button(
                    ":blue[:material/refresh:]",
                    key=f"retry_{job_id}",
                    help="Relancer cette tâche",
                    width="stretch",
                    disabled=(status == JobStatus.PROCESSING.value),
                ):
                    db_client.retry_job(job_id)
                    st.toast(f"Tâche {job_id} remise en file d'attente.", icon="🔁")
                    st.rerun()
                if b2.button(
                    ":material/delete:",
                    key=f"btn_del_job_{job_id}",
                    type="secondary",
                    help="Supprimer cette tâche et lever son verrou éventuel (action irréversible)",
                    width="stretch",
                ):
                    db_client.cancel_or_delete_job(job_id)
                    st.toast(f"Tâche {job_id} supprimée.", icon="🗑️")
                    st.rerun()

            if error_msg:
                st.error(f"Erreur : {error_msg}")

            job_thinking = job.get("current_thinking")
            if job_thinking:
                agent_lbl = job.get("active_agent") or "Agent IA"
                with st.expander(
                    f"💭 Réflexion IA ({agent_lbl})",
                    expanded=(status == JobStatus.PROCESSING.value),
                ):
                    with st.container(height=180, border=True):
                        st.caption(job_thinking)


def queue_admin_view():
    st.title("⚙️ Administration — File de traitement & Verrous")
    st.caption(
        "Supervisez l'état de la file de traitement `PriorityQueue`, nettoyez les tâches et libérez les verrous en cas d'interruption."
    )

    cross_domain = st.toggle(
        f"Vue globale multi-domaines ({', '.join(app_conf.enabled_domains_list)})",
        value=True,
    )

    broker = _get_broker()
    try:
        stats = broker.get_queue_stats(cross_domain=cross_domain)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric(
            "⏳ En attente", stats.get("pending", 0), border=True, height="stretch"
        )
        m2.metric(
            "🔄 En cours", stats.get("processing", 0), border=True, height="stretch"
        )
        m3.metric(
            "✅ Terminées", stats.get("completed", 0), border=True, height="stretch"
        )
        m4.metric("❌ En échec", stats.get("failed", 0), border=True, height="stretch")
        m5.metric(
            "🔒 Emplacements actifs",
            f"{stats.get('active_locks', 0)} / {stats.get('batch_size', 1)}",
            border=True,
            height="stretch",
        )

        st.divider()
        render_live_thinking_section(cross_domain=cross_domain)
        st.divider()
        render_locks_section(broker)
        st.divider()
        render_maintenance_actions(broker, cross_domain=cross_domain)
        st.divider()
        render_jobs_table(broker, cross_domain=cross_domain)
    finally:
        broker.close()


queue_admin_view()
