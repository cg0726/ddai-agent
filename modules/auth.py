import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

import streamlit as st
from modules.config import APP_PASSWORD

TOKEN_TTL = 2 * 3600  # 缩短为2小时

MAX_ATTEMPTS = 5
ATTEMPT_WINDOW = 900
LOCKOUT_STAGES = [
    (5, 60),
    (8, 300),
    (12, 900),
    (20, 3600),
]
CLEANUP_INTERVAL = 3600

RATE_LIMIT_FILE = Path(__file__).resolve().parent.parent / "data" / "login_attempts.json"


def _load_attempts() -> dict:
    try:
        with open(RATE_LIMIT_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"attempts": {}}


def _save_attempts(data: dict):
    RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RATE_LIMIT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_client_ip() -> str:
    try:
        headers = st.context.headers
        forwarded = headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        remote = headers.get("Remote-Addr")
        if remote:
            return remote
    except Exception:
        pass
    return "127.0.0.1"


def _get_lockout_duration(fail_count: int) -> int:
    for threshold, duration in LOCKOUT_STAGES:
        if fail_count >= threshold:
            return duration
    return 0


def _cleanup_old_attempts(data: dict):
    now = time.time()
    attempts = data.get("attempts", {})
    cutoff = now - ATTEMPT_WINDOW
    cleaned = {}
    for ip, record in attempts.items():
        recent = [ts for ts in record.get("failed_attempts", []) if ts > cutoff]
        locked_until = record.get("locked_until", 0)
        if recent or (locked_until and locked_until > now):
            cleaned[ip] = {
                "failed_attempts": recent,
                "locked_until": locked_until if locked_until > now else 0,
            }
    data["attempts"] = cleaned
    data["last_cleanup"] = now
    return data


def _check_rate_limit(ip: str) -> str | None:
    data = _load_attempts()
    now = time.time()

    if data.get("last_cleanup", 0) < now - CLEANUP_INTERVAL:
        data = _cleanup_old_attempts(data)
        _save_attempts(data)

    record = data.get("attempts", {}).get(ip, {})
    locked_until = record.get("locked_until", 0)

    if locked_until > now:
        remaining = int(locked_until - now)
        return f"登录尝试过于频繁，请在 {remaining} 秒后重试"

    recent_attempts = [ts for ts in record.get("failed_attempts", []) if ts > now - ATTEMPT_WINDOW]
    if len(recent_attempts) >= MAX_ATTEMPTS:
        duration = _get_lockout_duration(len(recent_attempts))
        if duration > 0:
            locked_until = now + duration
            data["attempts"][ip] = {
                "failed_attempts": recent_attempts,
                "locked_until": locked_until,
            }
            _save_attempts(data)
            return f"登录尝试过于频繁，请在 {duration} 秒后重试"
    return None


def _record_failed_attempt(ip: str):
    data = _load_attempts()
    now = time.time()
    record = data.get("attempts", {}).get(ip, {"failed_attempts": [], "locked_until": 0})
    recent = [ts for ts in record.get("failed_attempts", []) if ts > now - ATTEMPT_WINDOW]
    recent.append(now)

    duration = _get_lockout_duration(len(recent))
    locked_until = (now + duration) if duration > 0 else 0

    data["attempts"][ip] = {
        "failed_attempts": recent,
        "locked_until": locked_until,
    }
    _save_attempts(data)


def _timing_safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _make_token(password: str, ts: int) -> str:
    """生成安全的认证Token，使用密码哈希"""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return hashlib.sha256(f"ddai_auth_{password_hash}_{ts}".encode()).hexdigest()


def logout():
    """登出，清除认证状态和URL中的Token"""
    st.session_state.authenticated = False
    # 清除URL中的认证参数
    if "auth_token" in st.query_params:
        del st.query_params["auth_token"]
    if "auth_ts" in st.query_params:
        del st.query_params["auth_ts"]
    st.rerun()


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
                if _timing_safe_compare(stored_token, expected_token):
                    st.session_state.authenticated = True
                    return True
        except ValueError:
            pass

    client_ip = _get_client_ip()

    st.markdown("<h1 style='text-align: center;'>📋 尽责报告助手</h1>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("""
    <style>
    .login-input-wrapper {
        max-width: 250px;
        margin: 0 auto;
    }
    /* 隐藏 "Press Enter to submit form" 提示 */
    .st-emotion-cache-gm93q9 {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form", border=True):
            st.markdown("### 登录")
            st.markdown('<div class="login-input-wrapper">', unsafe_allow_html=True)
            password = st.text_input("请输入密码", type="password", label_visibility="collapsed",
                                     placeholder="请输入密码")
            st.markdown('</div>', unsafe_allow_html=True)
            if st.form_submit_button("登录", use_container_width=True, type="primary"):
                    rate_limit_msg = _check_rate_limit(client_ip)
                    if rate_limit_msg:
                        st.error(rate_limit_msg)
                        return False

                    if _timing_safe_compare(password, APP_PASSWORD):
                        st.session_state.authenticated = True
                        ts = int(time.time())
                        st.query_params["auth_token"] = _make_token(APP_PASSWORD, ts)
                        st.query_params["auth_ts"] = str(ts)
                        st.rerun()
                    else:
                        _record_failed_attempt(client_ip)
                        remaining = MAX_ATTEMPTS - len(
                            [ts for ts in _load_attempts()
                             .get("attempts", {})
                             .get(client_ip, {})
                             .get("failed_attempts", [])
                             if ts > time.time() - ATTEMPT_WINDOW]
                        )
                        st.error(f"密码错误，请重试（还可尝试 {max(0, remaining)} 次）")
    return False
