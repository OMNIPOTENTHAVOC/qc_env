"""
Layer 1 — Node A (port 5001)
Orchestrates the full end-to-end flow:

  1. Generate Alice's bits and bases
  2. Encode → Qiskit circuit
  3. Pass through channel (clean or via Eve)
  4. Serialise circuit as QASM, send to Node B /measure
  5. Receive Bob's bases and results, perform sifting
  6. Compute QBER, decide key validity
  7. Notify Node B via /confirm-key (classical channel)
  8. If valid: derive K, generate DK, encrypt data, wrap DK, store (C, EK)

Endpoints:
  POST /initiate   — start a key exchange session
  GET  /status     — live node state (last 5 sessions)
  GET  /history    — full session list from SQLite (for Streamlit)
"""
import hashlib
import sys
import os
import time
import uuid

import requests
from flask import Flask, jsonify, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quantum.basis import generate_bits, generate_bases
from quantum.channel import transmit
from quantum.encoding import encode
from security.crypto import (
    derive_key_from_bits,
    encrypt_data,
    generate_data_key,
    wrap_key,
)
from storage.db import get_all_sessions, store_session

app = Flask(__name__)

NODE_B_URL = "http://localhost:5002"
QBER_THRESHOLD = 0.11          # Reject key if QBER exceeds this
MIN_SIFTED_BITS = 32           # Reject key if too few bits survive sifting

# In-memory session summaries (no key material stored here)
_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# POST /initiate
# ---------------------------------------------------------------------------
@app.route("/initiate", methods=["POST"])
def initiate():
    data = request.get_json(force=True)
    num_bits: int = data.get("num_bits", 256)
    eve: bool = data.get("eve", False)
    plaintext: str = data.get("plaintext", "Hello from Node A")

    session_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Step 1: Alice generates bits and bases
    # ------------------------------------------------------------------
    alice_bits = generate_bits(num_bits)
    alice_bases = generate_bases(num_bits)

    # ------------------------------------------------------------------
    # Step 2: Encode qubits and pass through quantum channel
    # (Eve intercepts and re-encodes if eve=True)
    # ------------------------------------------------------------------
    qc = encode(alice_bits, alice_bases)
    qc = transmit(qc, eve=eve)

    # ------------------------------------------------------------------
    # Step 3: Send circuit to Node B for measurement (classical HTTP,
    # carrying the serialised quantum state — simulation of quantum channel)
    # ------------------------------------------------------------------
    try:
        resp = requests.post(
            f"{NODE_B_URL}/measure",
            json={"qasm": qc.qasm(), "num_qubits": num_bits},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"Node B unreachable: {exc}"}), 503

    b_data = resp.json()
    bob_bases: list[int] = b_data["bob_bases"]
    bob_results: list[int] = b_data["bob_results"]

    # ------------------------------------------------------------------
    # Step 4: Sifting — keep only bits where bases matched
    # ------------------------------------------------------------------
    sifted_alice: list[int] = []
    sifted_bob: list[int] = []
    sifted_indices: list[int] = []

    for i in range(num_bits):
        if alice_bases[i] == bob_bases[i]:
            sifted_alice.append(alice_bits[i])
            sifted_bob.append(bob_results[i])
            sifted_indices.append(i)

    # ------------------------------------------------------------------
    # Step 5: QBER calculation
    # ------------------------------------------------------------------
    if not sifted_alice:
        qber = 1.0
    else:
        errors = sum(1 for a, b in zip(sifted_alice, sifted_bob) if a != b)
        qber = errors / len(sifted_alice)

    # ------------------------------------------------------------------
    # Step 6: Key validity decision
    # ------------------------------------------------------------------
    qber_ok = qber <= QBER_THRESHOLD
    length_ok = len(sifted_alice) >= MIN_SIFTED_BITS
    valid = qber_ok and length_ok

    # Eve is detectable when QBER spikes above threshold
    eve_detected = qber > QBER_THRESHOLD

    # ------------------------------------------------------------------
    # Step 7: Notify Node B (classical confirmation channel)
    # ------------------------------------------------------------------
    try:
        requests.post(
            f"{NODE_B_URL}/confirm-key",
            json={
                "session_id": session_id,
                "sifted_indices": sifted_indices,
                "qber": qber,
                "valid": valid,
            },
            timeout=5,
        )
    except requests.RequestException:
        pass  # Non-fatal — observability loss, not a security failure

    # ------------------------------------------------------------------
    # Step 8: If key is valid → encrypt data and store (C, EK)
    # ------------------------------------------------------------------
    result: dict = {
        "session_id": session_id,
        "qber": round(qber, 6),
        "valid": valid,
        "eve_detected": eve_detected,
        "num_sifted_bits": len(sifted_alice),
        "encrypted": False,
        "timestamp": time.time(),
    }

    if valid:
        # Derive 256-bit key K from sifted bits (SHA-256 of bit array)
        K = derive_key_from_bits(sifted_alice)

        # Generate ephemeral Data Key
        DK = generate_data_key()

        # C = Encrypt(DK, plaintext)
        C, nonce_data = encrypt_data(DK, plaintext.encode("utf-8"))

        # EK = Encrypt(K, DK)
        EK, nonce_key = wrap_key(K, DK)

        # Persist (C, EK) — no plaintext or keys written to disk
        store_session(
            session_id=session_id,
            ciphertext=C,
            wrapped_key=EK,
            nonce_data=nonce_data,
            nonce_key=nonce_key,
            qber=qber,
            eve=eve,
        )

        result["encrypted"] = True
        result["ciphertext_len"] = len(C)

    _sessions[session_id] = result
    return jsonify(result)


# ---------------------------------------------------------------------------
# GET /status  — live state for dashboard
# ---------------------------------------------------------------------------
@app.route("/status", methods=["GET"])
def status():
    recent = list(_sessions.values())[-5:]
    return jsonify({
        "node": "A",
        "port": 5001,
        "total_sessions": len(_sessions),
        "qber_threshold": QBER_THRESHOLD,
        "min_sifted_bits": MIN_SIFTED_BITS,
        "recent_sessions": recent,
    })


# ---------------------------------------------------------------------------
# GET /history  — full SQLite history for Streamlit chart
# ---------------------------------------------------------------------------
@app.route("/history", methods=["GET"])
def history():
    return jsonify(get_all_sessions())


if __name__ == "__main__":
    app.run(port=5001, debug=True, use_reloader=False)
