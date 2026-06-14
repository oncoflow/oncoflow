import os
import signal
import atexit


def clean_exit(signum=None, frame=None):
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


PAGES_DIR_SRC = "src/ui"
navigation = {}
st.set_page_config(layout="wide")


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


def login():
    if st.button("Log in"):
        st.session_state.logged_in = True
        st.rerun()


def logout():
    if st.button("Log out"):
        st.session_state.logged_in = False
        st.rerun()


# login_page = st.Page(login, title="Log in", icon=":material/login:")
# logout_page = st.Page(logout, title="Log out", icon=":material/logout:")

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


pages = {}


pages["Patient mdt Oncologic"] = [
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt_oncologic/cards.py",
        title="Liste RCP",
        icon="📇",
        default=True,
    ),
    st.Page(f"{PAGES_DIR_SRC}/patient_mdt_oncologic/datas.py", title="RCP", icon="📇"),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt_oncologic/upload.py",
        title="Charger le/les fichier(s)",
        icon="🚀",
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt_oncologic/agents.py",
        title="Agents and ressources",
        icon=":material/robot:",
    ),
]
pages["Reports"] = [
    st.Page(
        f"{PAGES_DIR_SRC}/reports/bugs.py",
        title="Bug reports",
        icon=":material/bug_report:",
    )
]


# if st.session_state.logged_in:
pg = st.navigation(pages)
# else:
#     pg = st.navigation([login_page])

pg.run()
