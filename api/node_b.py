"""
Layer 1 — Node B (port 5002)
Responsibilities:
  - Receive encoded quantum circuit from Node A via /measure
  - Generate Bob's random measurement bases
  - Return measured bits to Node A
  - Acknowledge sifting confirmation from Node A

All request parsing and response building uses shared/models.py
to enforce a consistent integration contract with Node A.
"""
import sys
import os

from flask import Flask, request, jsonify
from qiskit import QuantumCircuit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quantum.basis import generate_bases
from quantum.measurement import measure_with_bases
from shared.models import (
    MeasureRequest,
    MeasureResponse,
    ConfirmKeyRequest,
    ConfirmKeyResponse,
)

app = Flask(__name__)

# In-memory session store — sifting metadata only, no key material
_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# POST /measure
# ---------------------------------------------------------------------------
@app.route("/measure", methods=["POST"])
def measure():
    # Parse and validate via shared model
    try:
        req = MeasureRequest.from_dict(request.get_json(force=True))
    except (TypeError, KeyError) as exc:
        return jsonify({"error": f"Invalid MeasureRequest: {exc}"}), 400

    # Reconstruct Qiskit circuit from QASM
    qc = QuantumCircuit.from_qasm_str(req.qasm)

    # Bob independently generates random measurement bases
    bob_bases = generate_bases(req.num_qubits)

    # Measure — measure_with_bases copies internally so qc is not mutated
    bob_results = measure_with_bases(qc, bob_bases)

    resp = MeasureResponse(bob_bases=bob_bases, bob_results=bob_results)
    return jsonify(resp.to_dict())


# ---------------------------------------------------------------------------
# POST /confirm-key
# ---------------------------------------------------------------------------
@app.route("/confirm-key", methods=["POST"])
def confirm_key():
    try:
        req = ConfirmKeyRequest.from_dict(request.get_json(force=True))
    except (TypeError, KeyError) as exc:
        return jsonify({"error": f"Invalid ConfirmKeyRequest: {exc}"}), 400

    _sessions[req.session_id] = {
        "sifted_indices": req.sifted_indices,
        "qber": req.qber,
        "valid": req.valid,
    }

    resp = ConfirmKeyResponse(acknowledged=True, session_id=req.session_id)
    return jsonify(resp.to_dict())


# ---------------------------------------------------------------------------
# GET /status  — polled by Streamlit dashboard
# ---------------------------------------------------------------------------
@app.route("/status", methods=["GET"])
def status():
    recent = [
        {"session_id": sid, "qber": s["qber"], "valid": s["valid"]}
        for sid, s in list(_sessions.items())[-5:]
    ]
    return jsonify({
        "node": "B",
        "port": 5002,
        "total_sessions": len(_sessions),
        "recent_sessions": recent,
    })


if __name__ == "__main__":
    app.run(port=5002, debug=True, use_reloader=False)
