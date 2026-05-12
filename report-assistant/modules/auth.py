import hashlib
import time
import streamlit as st
from modules.config import APP_PASSWORD

TOKEN_TTL = 48 * 3600


def _make_token(password: str, ts: int) -> str:
    return hashlib.sha256(f"ddai_auth_{password}_{ts}".encode()).hexdigest()


def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    now = int(time.time())
    params = st.query_params
    stored_ts_str = params.get("auth_ts", "")
    stored_token = params.get("auth_token", "")

    if stored_ts_str and stored_token:
        try:
            stored_ts = int(stored_ts_str)
            if now - stored_ts <= TOKEN_TTL:
                expected_token = _make_token(APP_PASSWORD, stored_ts)
                if stored_token == expected_token:
                    st.session_state.authenticated = True
                    return True
        except ValueError:
            pass

    st.markdown("<h1 style='text-align: center;'>📋 尽责报告助手</h1>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("""
    <style>
    .login-input-wrapper {
        max-width: 250px;
        margin: 0 auto;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("### 登录")
            st.markdown('<div class="login-input-wrapper">', unsafe_allow_html=True)
            password = st.text_input("请输入密码", type="password", label_visibility="collapsed",
                                     placeholder="请输入密码")
            st.markdown('</div>', unsafe_allow_html=True)
            if st.button("登录", use_container_width=True, type="primary"):
                if password == APP_PASSWORD:
                    st.session_state.authenticated = True
                    st.session_state.password = password
                    ts = int(time.time())
                    st.query_params["auth_token"] = _make_token(APP_PASSWORD, ts)
                    st.query_params["auth_ts"] = str(ts)
                    st.rerun()
                else:
                    st.error("密码错误，请重试")
    return False
