import streamlit as st
import bcrypt
from config import ADMIN_USERNAME, ADMIN_PASSWORD_HASH, ADMIN_PASSWORD_PLAIN


def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def login_page():
    """Render login form. Returns True if authenticated."""
    st.markdown("""
    <style>
    .login-wrap {
        max-width: 420px;
        margin: 80px auto 0 auto;
        background: #1a1f2e;
        border: 1px solid #2d3748;
        border-radius: 16px;
        padding: 40px;
    }
    .login-logo { text-align:center; font-size:3rem; margin-bottom:8px; }
    .login-title { text-align:center; font-size:1.4rem; font-weight:700; color:#e2e8f0; margin-bottom:4px; }
    .login-sub { text-align:center; font-size:0.85rem; color:#718096; margin-bottom:28px; }
    </style>
    <div class="login-wrap">
        <div class="login-logo">📊</div>
        <div class="login-title">DataWarehouse Chatbot</div>
        <div class="login-sub">Sign in to access your analytics assistant</div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        st.markdown("##### Username")
        username = st.text_input("", placeholder="Enter username", label_visibility="collapsed")
        st.markdown("##### Password")
        password = st.text_input("", placeholder="Enter password", type="password", label_visibility="collapsed")
        submitted = st.form_submit_button("Sign In", use_container_width=True)

    if submitted:
        correct_user = username == ADMIN_USERNAME
        # Support both bcrypt hash and plain fallback (set hash in .env for production)
        if ADMIN_PASSWORD_HASH:
            correct_pass = _check_password(password, ADMIN_PASSWORD_HASH)
        else:
            correct_pass = password == ADMIN_PASSWORD_PLAIN

        if correct_user and correct_pass:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.rerun()
        else:
            st.error("Invalid username or password.")

    return st.session_state.get("authenticated", False)


def require_auth():
    """Call at top of every page. Redirects to login if not authenticated."""
    if not st.session_state.get("authenticated", False):
        login_page()
        st.stop()
