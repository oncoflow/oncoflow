import streamlit as st


PAGES_DIR_SRC = "src/ui"
navigation = {}

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




pages = {}


pages["Patient mdt Oncologic"] = [
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt_oncologic/datas.py",
        title="Datas",
        icon=":material/dashboard:",
        default=True,
    ),
    st.Page(
        f"{PAGES_DIR_SRC}/patient_mdt_oncologic/metadatas.py",
        title="Metadatas",
        icon=":material/dashboard:",
    ),
]
pages["Reports"] = [
    st.Page(
        f"{PAGES_DIR_SRC}/reports/bugs.py",
        title="Bug reports",
        icon=":material/dashboard:",
    )
]


# if st.session_state.logged_in:
pg = st.navigation(pages)
# else:
#     pg = st.navigation([login_page])

pg.run()
