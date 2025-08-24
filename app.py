import os
import time
import hmac
import hashlib
import streamlit as st

# =========================
# App meta
# =========================
APP_TITLE = "KPIQ Starter Report"
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
st.title(APP_TITLE)

# =========================
# Config / ENV
# =========================
ENABLED_PLANS = [p for p in os.getenv("ENABLED_PLANS", "starter").replace(" ", "").split(",") if p]
SSO_SECRET = os.getenv("KPIQ_SSO_SECRET", "")
SHOPIFY_PLANS_URL = os.getenv("SHOPIFY_PLANS_URL", "https://kpiq.info/pages/plans")

# Gerçek veri API’si (AWS vb.)
DATA_API_BASE   = os.getenv("KPIQ_DATA_API_BASE", "").rstrip("/")     # ör: https://api.kpiq.yourdomain.com
DATA_API_SECRET = os.getenv("KPIQ_DATA_API_SECRET", SSO_SECRET)       # yoksa SSO secret’ı kullanır

# =========================
# Helpers
# =========================
def sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

def _get_query_params() -> dict:
    """Streamlit 1.31+: st.query_params ; eski sürümler: experimental_get_query_params()"""
    try:
        return dict(st.query_params)  # type: ignore[attr-defined]
    except Exception:
        return st.experimental_get_query_params()

def _val(q: dict, key: str) -> str:
    v = q.get(key)
    if v is None: return ""
    return v[0] if isinstance(v, list) else v

def validate_sso(q: dict) -> (bool, str):
    """Backend’ten gelen SSO paramlarını doğrula."""
    required = ["email", "shop", "plan", "ts", "sig"]
    if any(k not in q for k in required):
        return False, "Missing SSO parameters."

    email = _val(q, "email")
    shop  = _val(q, "shop")
    plan  = _val(q, "plan")
    ts    = _val(q, "ts")
    sig   = _val(q, "sig")

    try:
        ts_int = int(ts)
    except Exception:
        return False, "Invalid timestamp."
    if abs(int(time.time()) - ts_int) > 600:
        return False, "SSO link expired."

    if plan not in ENABLED_PLANS:
        return False, f"Plan '{plan}' not enabled."

    if not SSO_SECRET:
        return False, "Server misconfigured (SSO secret missing)."

    expected = sign(f"{email}|{shop}|{plan}|{ts_int}", SSO_SECRET)
    if not hmac.compare_digest(expected, sig):
        return False, "Invalid SSO signature."

    return True, ""

# =========================
# SSO doğrulama
# =========================
qp = _get_query_params()
ok, msg = validate_sso(qp)
if not ok:
    st.error(f"Access denied: {msg}")
    st.markdown(f"[Select a plan / Login]({SHOPIFY_PLANS_URL})")
    st.stop()

email = _val(qp, "email")
shop  = _val(qp, "shop")
plan  = _val(qp, "plan")
ts    = _val(qp, "ts")

# URL'den hassas query param'ları temizle (UX + güvenlik)
try:
    st.query_params.clear()  # type: ignore[attr-defined]
except Exception:
    st.experimental_set_query_params()

st.success(f"Welcome, **{email}** — plan: **{plan}** ✅")
st.caption("This is your Starter KPI Report.")

# =========================
# REAL DATA FETCH
# =========================
import requests
import pandas as pd
import altair as alt

def _sig_header(email: str, shop: str, plan: str, ts: str) -> str:
    """Veri API’sine gönderilecek HMAC imzası (email|shop|plan|ts)."""
    return sign(f"{email}|{shop}|{plan}|{ts}", DATA_API_SECRET or "")

def fetch_report(email: str, shop: str, plan: str, ts: str):
    """
    GET {DATA_API_BASE}/starter/report?shop=...&email=...&plan=starter&ts=...
    Headers: X-KPIQ-Signature: hmac_sha256(email|shop|plan|ts, DATA_API_SECRET)
    """
    if not DATA_API_BASE:
        return None, "DATA API base URL not configured (KPIQ_DATA_API_BASE)."

    url = f"{DATA_API_BASE}/starter/report"
    params = {"shop": shop, "email": email, "plan": plan, "ts": ts}
    headers = {"X-KPIQ-Signature": _sig_header(email, shop, plan, ts)}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None, f"API error: {resp.status_code} {resp.text[:200]}"
        return resp.json(), None
    except Exception as e:
        return None, f"Request failed: {e}"

data, err = fetch_report(email, shop, plan, ts)

if err:
    st.info("Your dashboard is connected. Waiting for real data…")
    st.caption(err)  # debug amaçlı; prod'da kaldırabilirsiniz
    st.stop()

# Beklenen JSON örneği:
# {
#   "kpis": {"total_orders": 1234, "cr": 0.031, "aov": 52.3},
#   "table": [
#     {"day": "2025-08-11", "sessions": 575, "orders": 52, "conv_rate": 0.0904},
#     ...
#   ]
# }

kpis = (data or {}).get("kpis", {})
table = (data or {}).get("table", [])

# KPIs (varsa)
if kpis:
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Orders", f"{kpis.get('total_orders', 0):,}")
    if "cr" in kpis:
        c2.metric("Conversion Rate", f"{kpis['cr']:.2%}")
    if "aov" in kpis:
        c3.metric("AOV", f"{kpis['aov']:.2f}")

# Tablo
if not table:
    st.warning("No rows returned from the data API.")
    st.stop()

df = pd.DataFrame(table)
if "day" in df.columns:
    # tarih alanını düzgün göster
    df["day"] = pd.to_datetime(df["day"], errors="coerce")

st.subheader("Last 14 days overview")
st.dataframe(df, use_container_width=True)

# Grafik (varsa)
if {"day", "conv_rate"}.issubset(df.columns):
    st.subheader("Conversion rate")
    chart = alt.Chart(df).mark_line(point=True).encode(
        x="day:T",
        y="conv_rate:Q"
    ).properties(height=300)
    st.altair_chart(chart, use_container_width=True)

# (Opsiyonel) geri linki
st.markdown('<div style="margin-top:24px"><a href="https://kpiq.info/pages/dashboard">← Back to Dashboard</a></div>', unsafe_allow_html=True)
