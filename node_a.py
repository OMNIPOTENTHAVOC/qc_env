"""
Layer 1 — Node A (port 5001)
Orchestrates the full end-to-end flow by delegating to the correct layer
for each responsibility:

  BB84Core.prepare()     → Layer 2 (quantum state generation)
  Node B /measure        → Layer 2 (Bob's measurement, remote)
  BB84Core.process()     → Layer 3 (sifting, QBER, key validity)
  Node B /confirm-key    → Layer 1 (classical channel notification)
  security/crypto.py     → Layer 5 (key derivation, encryption, wrapping)
  storage/db.py          → Layer 6 (persist C and EK)

Endpoints:
  POST /initiate   — start a key exchange session
  GET  /status     — live node state (last 5 sessions)
  GET  /history    — full session list from SQLite (for Streamlit)
"""
import sys
import os
import time
import uuid

import requests
from flask import Flask, jsonify, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quantum.bb84_core import BB84Core
from shared.models import (
    InitiateRequest,
    MeasureRequest,
    MeasureResponse,
    ConfirmKeyRequest,
    SessionResult,
)
from security.crypto import derive_key_from_bits, encrypt_data, generate_data_key, wrap_key
from storage.db import get_all_sessions, store_session

app = Flask(__name__)

NODE_B_URL = "http://localhost:5002"

# In-memory session summaries (no key material stored here)
_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# POST /initiate
# ---------------------------------------------------------------------------
@app.route("/initiate", methods=["POST"])
def initiate():
    # --- Parse and validate inbound request via shared model ---
    try:
        req = InitiateRequest.from_dict(request.get_json(force=True))
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    session_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Phase 1 (Layer 2): Alice prepares qubits
    # BB84Core owns bit generation, encoding, and channel simulation
    # ------------------------------------------------------------------
    bb84 = BB84Core(
        num_bits=req.num_bits,
        eve=req.eve,
    )
    prep = bb84.prepare()

    # ------------------------------------------------------------------
    # Layer 1 → Node B: Send circuit for Bob's measurement
    # QASM serialises the Qiskit circuit into a portable string format
    # ------------------------------------------------------------------
    measure_req = MeasureRequest(
        qasm=prep.circuit.qasm(),
        num_qubits=prep.num_bits,
    )
    try:
        resp = requests.post(
            f"{NODE_B_URL}/measure",
            json=measure_req.to_dict(),
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"Node B unreachable: {exc}"}), 503

    # --- Parse Node B's response via shared model ---
    measure_resp = MeasureResponse.from_dict(resp.json())

    # ------------------------------------------------------------------
    # Phase 2 (Layer 3): Sifting, QBER, key validity
    # BB84Core.process() owns all protocol logic — node_a has no
    # sifting or QBER arithmetic of its own
    # ------------------------------------------------------------------
    protocol = bb84.process(
        alice_bits=prep.alice_bits,
        alice_bases=prep.alice_bases,
        bob_bases=measure_resp.bob_bases,
        bob_results=measure_resp.bob_results,
    )

    # ------------------------------------------------------------------
    # Layer 1: Classical confirmation channel → Node B
    # ------------------------------------------------------------------
    confirm_req = ConfirmKeyRequest(
        session_id=session_id,
        sifted_indices=protocol.sifted_indices,
        qber=protocol.qber,
        valid=protocol.valid,
    )
    try:
        requests.post(
            f"{NODE_B_URL}/confirm-key",
            json=confirm_req.to_dict(),
            timeout=5,
        )
    except requests.RequestException:
        pass  # Non-fatal — observability loss, not a security failure

    # ------------------------------------------------------------------
    # Layer 5: Encrypt data and wrap key (only if key is valid)
    # ------------------------------------------------------------------
    result = SessionResult(
        session_id=session_id,
        qber=round(protocol.qber, 6),
        valid=protocol.valid,
        eve_detected=protocol.eve_detected,
        num_sifted_bits=protocol.num_sifted_bits,
        encrypted=False,
        timestamp=time.time(),
    )

    if protocol.valid:
        # Derive 256-bit key K from Alice's sifted bits
        K = derive_key_from_bits(protocol.key)

        # Generate ephemeral Data Key (DK)
        DK = generate_data_key()

        # C = Encrypt(DK, plaintext)
        C, nonce_data = encrypt_data(DK, req.plaintext.encode("utf-8"))

        # EK = Encrypt(K, DK)
        EK, nonce_key = wrap_key(K, DK)

        # Layer 6: Persist (C, EK) — no plaintext or raw keys written to disk
        store_session(
            session_id=session_id,
            ciphertext=C,
            wrapped_key=EK,
            nonce_data=nonce_data,
            nonce_key=nonce_key,
            qber=protocol.qber,
            eve=req.eve,
        )

        result.encrypted = True
        result.ciphertext_len = len(C)

    _sessions[session_id] = result.to_dict()
    return jsonify(result.to_dict())


# ---------------------------------------------------------------------------
# GET /status  — live state for Streamlit dashboard
# ---------------------------------------------------------------------------
@app.route("/status", methods=["GET"])
def status():
    recent = list(_sessions.values())[-5:]
    return jsonify({
        "node": "A",
        "port": 5001,
        "total_sessions": len(_sessions),
        "qber_threshold": BB84Core().qber_threshold,
        "min_sifted_bits": BB84Core().min_sifted_bits,
        "recent_sessions": recent,
    })


# ---------------------------------------------------------------------------
# GET /history  — full SQLite history for Streamlit QBER chart
# ---------------------------------------------------------------------------
@app.route("/history", methods=["GET"])
def history():
    return jsonify(get_all_sessions())


if __name__ == "__main__":
    app.run(port=5001, debug=True, use_reloader=False)
