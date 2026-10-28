import os
import signal
import atexit


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
from src.ui.patient_mdt.translations import get_logo_svg, translate_domain_fr

app_config = AppConfig()
domain_fr = translate_domain_fr(app_config.domain)
app_title = f"MedDataSyntis - {domain_fr}" if domain_fr else "MedDataSyntis"

st.set_page_config(
    page_title=app_title,
    page_icon="static/icon.png",
    layout="wide",
)

if app_config.dev_mode:
    logger = app_config.set_logger("oncoflow.ui")
    logger.warning(
        "\n"
        + "=" * 60
        + "\n"
        + "⚠️  MEDDATASYNTIS EST EN MODE DÉVELOPPEMENT (DEV MODE)  ⚠️".center(60)
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
    oauth_user = (
        headers.get("X-Forwarded-Preferred-Username")
        or headers.get("X-Auth-Request-Preferred-Username")
        or headers.get("X-Forwarded-User")
        or headers.get("X-Auth-Request-User")
    )
    oauth_email = headers.get("X-Forwarded-Email") or headers.get(
        "X-Auth-Request-Email"
    )
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
    except Exception as e:
        st.error(
            f"Erreur lors du chargement de la configuration d'authentification : {e}"
        )


st.logo(
    get_logo_svg(app_config.domain),
    size="large",
    icon_image="static/icon.png",
)


if "language" not in st.session_state:
    st.session_state["language"] = "Français"

st.sidebar.selectbox(
    "🌐 Langue / Language",
    options=["Français", "English"],
    key="language",
)

if st.session_state.get("language") == "English":
    AppConfig.set_runtime_override(language="english")
    app_config.language = "english"
else:
    AppConfig.set_runtime_override(language="french")
    app_config.language = "french"


pages = {}

pages[app_title] = [
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/cards.py",
        title="Dossiers Patients",
        icon="📇",
        default=True,
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/datas.py", title="Dossier Patient", icon="📝"
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/upload.py",
        title="Charger le/les fichier(s)",
        icon="🚀",
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/agents.py",
        title="Agents and ressources",
        icon="🤖",
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/ressources.py",
        title="Ressources",
        icon="📚",
    ),
]
pages["Reports"] = [
    st.Page(
        f"{PAGES_DIR_SRC}/reports/bugs.py",
        title="Bug reports",
        icon="🐛",
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/reports/queue_admin.py",
        title="File de traitement & Verrous",
        icon="⚙️",
    ),
]


if st.session_state.get("authentication_status"):
    with st.sidebar:
        if auth_mode == "oauth_proxy":
            user_display = st.session_state.get("username") or st.session_state.get(
                "name"
            )
            if user_display:
                st.caption(f"👤 Connecté : **{user_display}**")
            st.link_button(
                "Se déconnecter",
                "/oauth2/sign_out",
                icon="🚪",
                width="stretch",
            )
        elif authenticator is not None:
            if st.button("Se déconnecter", key="logout_btn", icon="🚪"):
                try:
                    authenticator.logout(location="unrendered")
                except KeyError:
                    pass
                st.rerun()

    pg = st.navigation(pages)

    # Redirection automatique vers le dossier patient si spécifié dans l'URL
    if (
        "patient_id" in st.query_params or "file" in st.query_params
    ) and pg.title != "Dossier Patient":
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
        except Exception as e:
            st.error(f"Erreur d'initialisation de l'authentification : {e}")

        if st.session_state.get("authentication_status") is False:
            st.error("Identifiant ou mot de passe incorrect")
        elif st.session_state.get("authentication_status") is None:
            st.warning("Veuillez saisir votre identifiant et votre mot de passe")
