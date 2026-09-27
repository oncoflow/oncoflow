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

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["DOCLING_DEVICE"] = "cpu"

import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth


PAGES_DIR_SRC = "src/ui"
navigation = {}
st.set_page_config(layout="wide")

# Configuration de l'authentification
from src.application.config import AppConfig

app_config = AppConfig()

if app_config.dev_mode:
    logger = app_config.set_logger("oncoflow.ui")
    logger.warning(
        "\n"
        + "=" * 60
        + "\n"
        + "⚠️  ONCOFLOW EST EN MODE DÉVELOPPEMENT (DEV MODE)  ⚠️".center(60)
        + "\n"
        + "=" * 60
        + "\n"
    )

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
    st.error(f"Erreur lors du chargement de la configuration d'authentification : {e}")


st.logo(
    "static/logo.png",
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
    os.environ["APP_LANGUAGE"] = "english"
    app_config.language = "english"
else:
    os.environ["APP_LANGUAGE"] = "french"
    app_config.language = "french"


pages = {}

pages["Patient mdt Oncologic"] = [
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt/cards.py",
        title="Liste RCP",
        icon="📇",
        default=True,
    ),
    st.Page(f"{PAGES_DIR_SRC}/patient_mdt/datas.py", title="RCP", icon="📝"),
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
    )
]


if st.session_state.get("authentication_status"):
    with st.sidebar:
        if st.button("Se déconnecter", key="logout_btn", icon="🚪"):
            try:
                authenticator.logout(location="unrendered")
            except KeyError:
                pass
            st.rerun()

    pg = st.navigation(pages)

    # Redirection automatique vers la fiche patient si spécifiée dans l'URL
    if "file" in st.query_params and pg.title != "RCP":
        st.switch_page(
            f"{PAGES_DIR_SRC}/patient_mdt/datas.py",
            query_params={"file": st.query_params["file"]},
        )

    pg.run()
else:
    try:
        authenticator.login(location="main")
    except Exception as e:
        st.error(f"Erreur d'initialisation de l'authentification : {e}")

    if st.session_state.get("authentication_status") is False:
        st.error("Identifiant ou mot de passe incorrect")
    elif st.session_state.get("authentication_status") is None:
        st.warning("Veuillez saisir votre identifiant et votre mot de passe")
