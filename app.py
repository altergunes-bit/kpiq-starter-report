import os, time, hmac, hashlib
import streamlit as st

APP_TITLE = "KPIQ Starter Report"

# ----- config -----
ENABLED_PLANS = [p for p in os.getenv("ENABLED_PLANS", "starter").replace(" ", "").split(",") if p]
SSO_SECRET = os.getenv("KPIQ_SSO_SECRET", "")
SHOPIFY_PLANS_URL = os.getenv("SHOPIFY_PLANS_URL", "https://kpiq.info/pages/plans")

def sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def validate_sso(q: dict) -> (bool, str):
    """Validate query params coming from backend SSO; return (ok, message)."""
    required = ["email", "shop", "plan", "ts", "sig"]
    if any(k not in q for k in required):
        return False, "Missing SSO parameters."

    email = q["email"][0] if isinstance(q["email"], list) else q["email"]
    shop = q["shop"][0] if isinstance(q["shop"], list) else q["shop"]
    plan = q["plan"][0] if isinstance(q["plan"], list) else q["plan"]
    ts = q["ts"][0] if isinstance(q["ts"], list) else q["ts"]
    sig = q["sig"][0] if isinstance(q["sig"], list) else q["sig"]

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

# ----- UI -----
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
st.title(APP_TITLE)

# Streamlit 1.31+: st.query_params ; eski sürümler: experimental_get_query_params
try:
    qp = st.query_params  # type: ignore[attr-defined]
except Exception:
    qp = st.experimental_get_query_params()  # fallback

ok, msg = validate_sso(qp)

if not ok:
    st.error(f"Access denied: {msg}")
    st.markdown(f"[Select a plan / Login]({SHOPIFY_PLANS_URL})")
    st.stop()

email = qp.get("email", [""])[0] if isinstance(qp.get("email"), list) else qp.get("email", "")
plan = qp.get("plan", [""])[0] if isinstance(qp.get("plan"), list) else qp.get("plan", "")

st.success(f"Welcome, **{email}** — plan: **{plan}** ✅")
st.write("This is your Starter KPI Report. (You can now render charts/metrics here.)")

# ---- Example content (replace with your real report) ----
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
    x="day:T", y="conv_rate:Q"
).properties(height=300)
st.altair_chart(chart, use_container_width=True)
