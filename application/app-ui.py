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
