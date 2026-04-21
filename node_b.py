"""
Layer 1 — Node B (port 5002)
Responsibilities:
  - Receive encoded quantum circuit from Node A via /measure
  - Generate Bob's random measurement bases
  - Return measured bits to Node A
  - Acknowledge sifting confirmation from Node A
"""
from flask import Flask, request, jsonify
from qiskit import QuantumCircuit

# Adjust import path if running from project root
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quantum.basis import generate_bases
from quantum.measurement import measure_with_bases

app = Flask(__name__)

# In-memory session store for Node B
# Stores sifted metadata — no plaintext, no keys
_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# POST /measure
# Node A sends the (post-channel) QASM string.
# Node B generates random bases, measures, and returns results.
# ---------------------------------------------------------------------------
@app.route("/measure", methods=["POST"])
def measure():
    data = request.get_json(force=True)

    qasm: str = data["qasm"]
    num_qubits: int = data["num_qubits"]

    # Reconstruct the Qiskit circuit from QASM
    qc = QuantumCircuit.from_qasm_str(qasm)

    # Bob independently chooses random measurement bases
    bob_bases = generate_bases(num_qubits)

    # Measure — measure_with_bases copies internally, so qc is not mutated
    bob_results = measure_with_bases(qc, bob_bases)

    return jsonify({
        "bob_bases": bob_bases,
        "bob_results": bob_results,
    })


# ---------------------------------------------------------------------------
# POST /confirm-key
# Node A notifies Node B which indices survived sifting and the QBER result.
# Node B records this so it can reconstruct its half of the sifted key later.
# ---------------------------------------------------------------------------
@app.route("/confirm-key", methods=["POST"])
def confirm_key():
    data = request.get_json(force=True)

    session_id: str = data["session_id"]
    _sessions[session_id] = {
        "sifted_indices": data["sifted_indices"],
        "qber": data["qber"],
        "valid": data["valid"],
    }

    return jsonify({
        "acknowledged": True,
        "session_id": session_id,
    })


# ---------------------------------------------------------------------------
# GET /status
# Observability endpoint polled by the Streamlit dashboard.
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
