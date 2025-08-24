import os
import time
import hmac
import hashlib
import streamlit as st

# -------- App meta --------
APP_TITLE = "KPIQ Starter Report"
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
st.title(APP_TITLE)

# -------- Config / ENV --------
ENABLED_PLANS = [
    p for p in os.getenv("ENABLED_PLANS", "starter").replace(" ", "").split(",") if p
]
SSO_SECRET = os.getenv("KPIQ_SSO_SECRET", "")
SHOPIFY_PLANS_URL = os.getenv("SHOPIFY_PLANS_URL", "https://kpiq.info/pages/plans")

# -------- Helpers --------
def sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def _get_query_params() -> dict:
    """
    Streamlit 1.31+ -> st.query_params (Mapping proxy)
    Eski sürümler -> experimental_get_query_params()
    """
    try:
        # Streamlit 1.31+: a dict-like object
        return dict(st.query_params)  # type: ignore[attr-defined]
    except Exception:
        return st.experimental_get_query_params()  # fallback

def _val(x, key):
    """Param değeri list veya str olabilir -> str olarak döndür."""
    if x is None:
        return ""
    v = x.get(key)
    if v is None:
        return ""
    return v[0] if isinstance(v, list) else v

def validate_sso(q: dict) -> (bool, str):
    """Validate query params coming from backend SSO; return (ok, message)."""
    required = ["email", "shop", "plan", "ts", "sig"]
    if any(k not in q for k in required):
        return False, "Missing SSO parameters."

    email = _val(q, "email")
    shop = _val(q, "shop")
    plan = _val(q, "plan")
    ts = _val(q, "ts")
    sig = _val(q, "sig")

    # time window (10 min)
    try:
        ts_int = int(ts)
    except Exception:
        return False, "Invalid timestamp."
    if abs(int(time.time()) - ts_int) > 600:
        return False, "SSO link expired."

    # plan allow-list
    if plan not in ENABLED_PLANS:
        return False, f"Plan '{plan}' not enabled."

    # signature
    if not SSO_SECRET:
        return False, "Server misconfigured (SSO secret missing)."

    expected = sign(f"{email}|{shop}|{plan}|{ts_int}", SSO_SECRET)
    if not hmac.compare_digest(expected, sig):
        return False, "Invalid SSO signature."

    return True, ""

# -------- Read & validate SSO --------
qp = _get_query_params()
ok, msg = validate_sso(qp)

if not ok:
    st.error(f"Access denied: {msg}")
    st.markdown(f"[Select a plan / Login]({SHOPIFY_PLANS_URL})")
    st.stop()

# Valid ise temel bilgiler
email = _val(qp, "email")
plan = _val(qp, "plan")

# İmza ve hassas paramları URL'den temizle (güvenlik + UX)
try:
    # Streamlit 1.31+: dict benzeri atama mümkün
    st.query_params.clear()  # type: ignore[attr-defined]
except Exception:
    # Daha eski sürüm için güvenli fallback
    st.experimental_set_query_params()  # boşalt

st.success(f"Welcome, **{email}** — plan: **{plan}** ✅")
st.write("This is your Starter KPI Report. (Charts/metrics will appear below.)")

# -------- Demo content (replace with your real report) --------
import pandas as pd
import numpy as np
import altair as alt

np.random.seed(7)
df = pd.DataFrame({
    "day": pd.date_range(end=pd.Timestamp.today().normalize(), periods=14),
    "sessions": np.random.randint(400, 1200, 14),
    "orders": np.random.randint(10, 60, 14),
})
df["conv_rate"] = (df["orders"] / df["sessions"]).round(4)

st.subheader("Last 14 days overview")
st.dataframe(df, use_container_width=True)

st.subheader("Conversion rate")
chart = alt.Chart(df).mark_line(point=True).encode(
    x="day:T",
    y="conv_rate:Q",
).properties(height=300)
st.altair_chart(chart, use_container_width=True)
