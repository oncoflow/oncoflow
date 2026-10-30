import atexit
import hmac
import os
import signal


def clean_exit(signum=None, frame=None):
    try:
        from src.application.config import AppConfig
        from src.application.app_functions import unload_active_models

        config = AppConfig()
        unload_active_models(config)
    except Exception:
        pass
    try:
        # Send SIGKILL to the entire process group to stop all processes instantly
        os.killpg(os.getpgid(0), signal.SIGKILL)
    except Exception:
        os._exit(0)


try:
    signal.signal(signal.SIGINT, clean_exit)
    signal.signal(signal.SIGTERM, clean_exit)
except ValueError:
    atexit.register(clean_exit)

import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth


PAGES_DIR_SRC = "src/ui"
navigation = {}

# Configuration de l'authentification
from src.application.config import AppConfig
from src.ui.patient_mdt.translations import (
    apply_card_surface_style,
    get_icon_svg,
    get_logo_svg,
    translate_domain_fr,
)

app_config = AppConfig()
domain_fr = translate_domain_fr(app_config.domain)
app_title = f"DataSyntis — {domain_fr}" if domain_fr else "DataSyntis"

st.set_page_config(
    page_title=app_title,
    page_icon="static/icon.svg",
    layout="wide",
)
apply_card_surface_style()

if app_config.dev_mode:
    logger = app_config.set_logger("oncoflow.ui")
    logger.warning(
        "\n"
        + "=" * 60
        + "\n"
        + "⚠️  DATASYNTIS EST EN MODE DÉVELOPPEMENT (DEV MODE)  ⚠️".center(60)
        + "\n"
        + "=" * 60
        + "\n"
    )

auth_mode = app_config.auth_mode.lower()
authenticator = None

if auth_mode == "oauth_proxy":
    headers = (
        st.context.headers
        if hasattr(st, "context") and hasattr(st.context, "headers")
        else {}
    )
    # Identity headers are only trusted when the request carries the secret injected
    # by the reverse proxy (Caddy): a client reaching Streamlit directly cannot forge them.
    expected_secret = app_config.proxy_secret
    proxy_ok = expected_secret is not None and hmac.compare_digest(
        (headers.get("X-Oncoflow-Proxy-Secret") or "").encode(),
        expected_secret.get_secret_value().encode(),
    )
    if expected_secret is None:
        st.error(
            "Configuration invalide : APP_PROXY_SECRET est obligatoire avec APP_AUTH_MODE=oauth_proxy."
        )
    # Only the headers copied by Caddy `forward_auth` from oauth2-proxy are trusted.
    oauth_user = (
        headers.get("X-Auth-Request-Preferred-Username")
        or headers.get("X-Auth-Request-User")
        if proxy_ok
        else None
    )
    oauth_email = headers.get("X-Auth-Request-Email") if proxy_ok else None
    if oauth_user or oauth_email:
        st.session_state["authentication_status"] = True
        st.session_state["username"] = oauth_user or oauth_email
        st.session_state["name"] = oauth_email or oauth_user
    else:
        st.session_state["authentication_status"] = False
else:
    auth_config_path = app_config.auth_config_path
    try:
        with open(auth_config_path, "r", encoding="utf-8") as file:
            config = yaml.load(file, Loader=SafeLoader)
        authenticator = stauth.Authenticate(
            config["credentials"],
            config["cookie"]["name"],
            config["cookie"]["key"],
            config["cookie"]["expiry_days"],
        )
    except Exception:
        app_config.set_logger("oncoflow.ui").exception(
            "Failed to load authentication configuration (%s)", auth_config_path
        )
        st.error("Erreur lors du chargement de la configuration d'authentification.")


st.logo(
    get_logo_svg(app_config.domain),
    size="large",
    icon_image=get_icon_svg(),
)


if "language" not in st.session_state:
    st.session_state["language"] = "Français"

is_en = st.session_state.get("language") == "English"
if is_en:
    AppConfig.set_runtime_override(language="english")
    app_config.language = "english"
else:
    AppConfig.set_runtime_override(language="french")
    app_config.language = "french"


pages = {}

pages[app_title] = [
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/cards.py",
        title="MDT preparation & triage"
        if is_en
        else "Préparation & ordonnancement RCP",
        icon="📇",
        default=True,
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/datas.py",
        title="Patient clinical file" if is_en else "Dossier clinique patient",
        icon="👤",
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/upload.py",
        title="Document ingestion" if is_en else "Intégration documentaire",
        icon="📥",
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/agents.py",
        title="Specialty modules" if is_en else "Modules d'expertise",
        icon="🩺",
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/ressources.py",
        title="Clinical guidelines" if is_en else "Référentiels cliniques",
        icon="📚",
    ),
]
st.session_state["is_admin"] = bool(
    st.session_state.get("authentication_status")
) and app_config.is_admin(
    st.session_state.get("username"), st.session_state.get("name")
)

support_section_title = (
    "Quality & administration" if is_en else "Qualité & administration"
)
pages[support_section_title] = [
    st.Page(
        f"{PAGES_DIR_SRC}/reports/bugs.py",
        title="Quality feedback" if is_en else "Signalements & conformité",
        icon="📋",
    ),
]
if st.session_state["is_admin"]:
    pages[support_section_title].append(
        st.Page(
            f"{PAGES_DIR_SRC}/reports/queue_admin.py",
            title="Processing queue & locks" if is_en else "Supervision de la file",
            icon="⚙️",
        )
    )


if st.session_state.get("authentication_status"):
    pg = st.navigation(pages)

    with st.sidebar:
        st.caption(
            "Préparation documentaire et contrôle de complétude pour la décision collégiale en RCP."
            if not is_en
            else "Structured document synthesis and completeness verification for MDT preparation."
        )
        st.segmented_control(
            "Langue / Language",
            options=["Français", "English"],
            key="language",
            width="stretch",
        )
        if st.session_state.get("language") == "English":
            AppConfig.set_runtime_override(language="english")
            app_config.language = "english"
        else:
            AppConfig.set_runtime_override(language="french")
            app_config.language = "french"

        if auth_mode == "oauth_proxy":
            user_display = st.session_state.get("username") or st.session_state.get(
                "name"
            )
            if user_display:
                st.caption(
                    f":primary[:material/account_circle:] Praticien : **{user_display}**"
                )
            st.link_button(
                ":red[:material/logout:] Déconnexion",
                "/oauth2/sign_out",
                width="stretch",
            )
        elif authenticator is not None:
            user_display = st.session_state.get("name") or st.session_state.get(
                "username"
            )
            if user_display:
                st.caption(
                    f":primary[:material/account_circle:] Praticien : **{user_display}**"
                )
            if st.button(
                ":red[:material/logout:] Déconnexion",
                key="logout_btn",
                width="stretch",
            ):
                try:
                    authenticator.logout(location="unrendered")
                except KeyError:
                    pass
                st.rerun()

    # Redirection automatique vers le dossier patient si spécifié dans l'URL
    if (
        "patient_id" in st.query_params or "file" in st.query_params
    ) and pg.title not in (
        "Dossier clinique patient",
        "Patient clinical file",
    ):
        redirect_params = {}
        if "patient_id" in st.query_params:
            redirect_params["patient_id"] = st.query_params["patient_id"]
        if "file" in st.query_params:
            redirect_params["file"] = st.query_params["file"]
        st.switch_page(
            f"{PAGES_DIR_SRC}/patient_mdt/datas.py",
            query_params=redirect_params,
        )

    pg.run()
else:
    if auth_mode == "oauth_proxy":
        st.error(
            "Accès refusé : en-têtes d'authentification OAuth2 Proxy absents. "
            "Veuillez accéder à l'application via le portail sécurisé."
        )
    else:
        try:
            if authenticator is not None:
                authenticator.login(location="main")
        except Exception:
            app_config.set_logger("oncoflow.ui").exception(
                "Authentication widget initialisation failed"
            )
            st.error("Erreur d'initialisation de l'authentification.")

        if st.session_state.get("authentication_status") is False:
            st.error("Identifiant ou mot de passe incorrect")
        elif st.session_state.get("authentication_status") is None:
            st.warning("Veuillez saisir votre identifiant et votre mot de passe")
