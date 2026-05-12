import streamlit as st
from modules.config import APP_PASSWORD


def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.set_page_config(page_title="尽责报告助手", page_icon="📋", layout="wide")
    st.markdown("<h1 style='text-align: center;'>📋 尽责报告助手</h1>", unsafe_allow_html=True)
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("### 登录")
            password = st.text_input("请输入密码", type="password", label_visibility="collapsed",
                                     placeholder="请输入密码")
            if st.button("登录", use_container_width=True, type="primary"):
                if password == APP_PASSWORD:
                    st.session_state.authenticated = True
                    st.session_state.password = password
                    st.rerun()
                else:
                    st.error("密码错误，请重试")
    return False
