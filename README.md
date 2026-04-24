# QKD System — BB84 Simulation

A distributed simulation of the BB84 Quantum Key Distribution protocol with
intercept-resend eavesdropping, AES-256-GCM encryption, and a live observability
dashboard.

---

## Architecture

The system is organised into seven layers, each with a single responsibility:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 7 — Observability     ui/dashboard.py            │
│            Streamlit dashboard, QBER graph, Eve alerts  │
├─────────────────────────────────────────────────────────┤
│  Layer 6 — Storage           storage/db.py              │
│            SQLite: stores (C, EK) only — no plaintext   │
├─────────────────────────────────────────────────────────┤
│  Layer 5 — Security          security/crypto.py         │
│            AES-256-GCM data encryption + key wrapping   │
├─────────────────────────────────────────────────────────┤
│  Layer 4 — Attack Simulation quantum/channel.py         │
│            Eve intercept-resend model                   │
├─────────────────────────────────────────────────────────┤
│  Layer 3 — Protocol          quantum/bb84_core.py       │
│            Sifting, QBER, key acceptance/rejection      │
├─────────────────────────────────────────────────────────┤
│  Layer 2 — Quantum           quantum/{basis, encoding,  │
│            Qiskit BB84 state  measurement}.py           │
├─────────────────────────────────────────────────────────┤
│  Layer 1 — API               api/node_a.py (5001)       │
│            Flask nodes        api/node_b.py (5002)      │
└─────────────────────────────────────────────────────────┘
         Shared: shared/models.py (integration contract)
```

### End-to-end flow

```
Node A                              Node B
  │                                   │
  │── BB84Core.prepare() ────────────▶│  (QASM over HTTP /measure)
  │                                   │── generate_bases()
  │                                   │── measure_with_bases()
  │◀─ MeasureResponse ───────────────│
  │                                   │
  │── BB84Core.process() (sifting, QBER)
  │                                   │
  │── ConfirmKeyRequest ─────────────▶│  (classical /confirm-key)
  │                                   │
  │── if valid:
  │     K  = SHA-256(sifted_bits)
  │     DK = os.urandom(32)
  │     C  = AES-GCM(DK, plaintext)
  │     EK = AES-GCM(K, DK)
  │     SQLite ← (C, EK)
```

---

## Key security properties

| Property | Implementation |
|---|---|
| Data never stored in plaintext | Only `C = Encrypt(DK, data)` written to disk |
| BB84 key never stored | `K` exists only in memory for the duration of the session |
| Storage layer compromise is non-fatal | `(C, EK)` is useless without `K` |
| Eve is detectable | QBER > 11% → key rejected automatically |
| Key rotation doesn't require re-encryption | Only `EK` is replaced; `C` is unchanged |

> **Note on key derivation:** `derive_key_from_bits()` uses SHA-256 as a
> simulation shortcut. Production QKD systems use privacy amplification
> (e.g. universal hash families) to remove Eve's partial information from
> the sifted key. This is a known simplification.

---

## Project structure

```
qkd/
├── api/
│   ├── node_a.py          # Flask node A — port 5001 (orchestrator)
│   └── node_b.py          # Flask node B — port 5002 (Bob)
├── quantum/
│   ├── bb84_core.py       # BB84 protocol — prepare() + process()
│   ├── basis.py           # Random bit/basis generation
│   ├── encoding.py        # Qiskit circuit encoding (BB84 states)
│   ├── measurement.py     # Qiskit measurement + basis application
│   └── channel.py        # Quantum channel + Eve intercept-resend
├── security/
│   └── crypto.py          # AES-256-GCM encryption + key wrapping
├── storage/
│   └── db.py              # SQLite persistence — (C, EK) only
├── shared/
│   └── models.py          # Request/response dataclasses (integration contract)
├── ui/
│   └── dashboard.py       # Streamlit observability dashboard
├── run.sh                 # Start/stop all three processes
└── requirements.txt
```

---

## Installation

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> Requires Python 3.10+ and Qiskit 0.45.x. If you are on Qiskit 1.x,
> `measurement.py` needs to be ported from `Aer`/`execute` to
> `qiskit_aer.AerSimulator` and the `Sampler` primitive.

---

## Running

```bash
# Start all three processes (Node B → Node A → Dashboard)
chmod +x run.sh
./run.sh

# Or manually in three separate terminals:
python api/node_b.py          # terminal 1
python api/node_a.py          # terminal 2
streamlit run ui/dashboard.py # terminal 3

# Stop
./run.sh stop
```

### Triggering a session manually (without the dashboard)

```bash
# Clean key exchange
curl -s -X POST http://localhost:5001/initiate \
  -H "Content-Type: application/json" \
  -d '{"num_bits": 256, "eve": false, "plaintext": "secret message"}' | python -m json.tool

# With Eve active
curl -s -X POST http://localhost:5001/initiate \
  -H "Content-Type: application/json" \
  -d '{"num_bits": 256, "eve": true, "plaintext": "secret message"}' | python -m json.tool
```

Expected QBER without Eve: ~0.00  
Expected QBER with Eve (intercept-resend): ~0.25

---

## Dashboard

Open `http://localhost:8501` after starting the system.

- **Session control** (sidebar): set qubit count, toggle Eve, set plaintext
- **QBER chart**: historical QBER per session, coloured by Eve presence
- **Last session metrics**: QBER, key validity, Eve detection, ciphertext length
- **Node status**: live health check for both Flask nodes
