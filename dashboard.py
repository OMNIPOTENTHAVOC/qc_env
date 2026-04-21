"""
Layer 7 — Observability Dashboard (Streamlit)
Polls Node A's Flask API for live session data.
Reads SQLite history via Node A's /history endpoint.

Run with:
    streamlit run ui/dashboard.py
"""
import time
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

NODE_A = "http://localhost:5001"
NODE_B = "http://localhost:5002"
QBER_THRESHOLD = 0.11


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="QKD System — Live Dashboard",
    page_icon="🔐",
    layout="wide",
)
st.title("🔐 QKD System — Live Dashboard")
st.caption("BB84 Protocol · AES-256-GCM · Intercept-Resend Eve Model")


# ---------------------------------------------------------------------------
# Sidebar — session control
# ---------------------------------------------------------------------------
st.sidebar.header("Session Control")

num_bits = st.sidebar.select_slider(
    "Qubit count",
    options=[64, 128, 256, 512],
    value=256,
    help="More qubits → more sifted key material, slower simulation",
)
eve_enabled = st.sidebar.toggle("🕵️ Enable Eve (intercept-resend attack)", value=False)
plaintext = st.sidebar.text_area(
    "Plaintext to encrypt",
    value="Hello from Node A — this message will be encrypted with the BB84-derived key.",
    height=80,
)

run_session = st.sidebar.button("▶ Initiate Key Exchange", type="primary", use_container_width=True)
st.sidebar.divider()
auto_refresh = st.sidebar.toggle("Auto-refresh every 5s", value=False)


# ---------------------------------------------------------------------------
# Trigger session
# ---------------------------------------------------------------------------
if run_session:
    with st.spinner("Running BB84 protocol between Node A and Node B…"):
        try:
            resp = requests.post(
                f"{NODE_A}/initiate",
                json={"num_bits": num_bits, "eve": eve_enabled, "plaintext": plaintext},
                timeout=30,
            )
            result = resp.json()
            st.session_state["last_result"] = result
            if result.get("valid"):
                st.success("✅ Key exchange successful — data encrypted and stored.")
            else:
                reason = "QBER too high (Eve detected)" if result.get("eve_detected") else "Too few sifted bits"
                st.error(f"❌ Key rejected — {reason}")
        except requests.RequestException as exc:
            st.error(f"Could not reach Node A: {exc}")


# ---------------------------------------------------------------------------
# Last session metrics
# ---------------------------------------------------------------------------
if "last_result" in st.session_state:
    r = st.session_state["last_result"]
    st.subheader("Last Session")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("QBER", f"{r['qber']:.4f}", delta=f"{r['qber'] - QBER_THRESHOLD:.4f} vs threshold")
    c2.metric("Key Valid", "✅ Yes" if r["valid"] else "❌ No")
    c3.metric("Eve Detected", "🚨 Yes" if r.get("eve_detected") else "✅ No")
    c4.metric("Sifted Bits", r["num_sifted_bits"])
    c5.metric("Encrypted", "✅" if r.get("encrypted") else "—")
    with st.expander("Full session JSON"):
        st.json(r)

st.divider()


# ---------------------------------------------------------------------------
# Historical QBER chart (SQLite via Node A /history)
# ---------------------------------------------------------------------------
st.subheader("📈 QBER History")

try:
    history_resp = requests.get(f"{NODE_A}/history", timeout=5)
    history = history_resp.json()
except requests.RequestException:
    history = []

if history:
    df = pd.DataFrame(history)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    df["eve_label"] = df["eve_present"].map({True: "Eve ON", False: "Clean"})

    fig = go.Figure()

    # Separate traces for clean vs Eve sessions
    for eve_val, color, name in [(False, "#00d4aa", "Clean channel"), (True, "#ff4444", "Eve present")]:
        mask = df["eve_present"] == eve_val
        if mask.any():
            fig.add_trace(go.Scatter(
                x=df.loc[mask, "timestamp"],
                y=df.loc[mask, "qber"],
                mode="lines+markers",
                name=name,
                line=dict(color=color, width=2),
                marker=dict(size=7),
            ))

    fig.add_hline(
        y=QBER_THRESHOLD,
        line_dash="dash",
        line_color="#ff9900",
        annotation_text=f"Rejection threshold ({QBER_THRESHOLD})",
        annotation_position="bottom right",
    )
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="QBER",
        yaxis=dict(range=[0, max(0.35, df["qber"].max() + 0.05)]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=30, b=0),
        height=350,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Summary table
    st.dataframe(
        df[["session_id", "qber", "eve_label", "timestamp"]]
        .rename(columns={"eve_label": "channel", "session_id": "Session ID", "qber": "QBER", "timestamp": "Time"}),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No sessions recorded yet. Run a session using the sidebar controls.")

st.divider()


# ---------------------------------------------------------------------------
# Node status (live)
# ---------------------------------------------------------------------------
st.subheader("🖧 Node Status")
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Node A** — port 5001")
    try:
        sa = requests.get(f"{NODE_A}/status", timeout=3).json()
        st.metric("Total sessions", sa.get("total_sessions", 0))
        st.metric("QBER threshold", sa.get("qber_threshold", QBER_THRESHOLD))
        st.caption("🟢 Online")
    except requests.RequestException:
        st.warning("🔴 Node A offline — is `api/node_a.py` running?")

with col_b:
    st.markdown("**Node B** — port 5002")
    try:
        sb = requests.get(f"{NODE_B}/status", timeout=3).json()
        st.metric("Total sessions", sb.get("total_sessions", 0))
        st.caption("🟢 Online")
    except requests.RequestException:
        st.warning("🔴 Node B offline — is `api/node_b.py` running?")


# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------
if auto_refresh:
    time.sleep(5)
    st.rerun()
