"""
Shared Layer — Integration Contract
Defines all request/response shapes used between Flask nodes.

Both Node A and Node B import from here. Every inbound request is parsed
through these models (validate on ingress), and every response is built
from them (consistent serialisation on egress).

Usage pattern in Flask endpoints:
    # Parse inbound JSON
    req = MeasureRequest.from_dict(request.get_json(force=True))

    # Build and return response
    resp = MeasureResponse(bob_bases=..., bob_results=...)
    return jsonify(resp.to_dict())
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Base mixin — shared serialisation for all models
# ---------------------------------------------------------------------------

@dataclass
class _Model:
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        # Only pass keys that the dataclass actually declares — ignore extras
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in fields})


# ---------------------------------------------------------------------------
# Node A → Node B  (quantum channel: send encoded circuit)
# ---------------------------------------------------------------------------

@dataclass
class MeasureRequest(_Model):
    """Node A sends the (post-channel) QASM circuit to Node B for measurement."""
    qasm: str
    num_qubits: int


@dataclass
class MeasureResponse(_Model):
    """Node B returns its randomly chosen bases and measured bit results."""
    bob_bases: list[int]
    bob_results: list[int]


# ---------------------------------------------------------------------------
# Node A → Node B  (classical channel: sifting confirmation)
# ---------------------------------------------------------------------------

@dataclass
class ConfirmKeyRequest(_Model):
    """
    After sifting, Node A tells Node B which indices survived basis matching,
    the computed QBER, and whether the key was accepted.
    """
    session_id: str
    sifted_indices: list[int]
    qber: float
    valid: bool


@dataclass
class ConfirmKeyResponse(_Model):
    acknowledged: bool
    session_id: str


# ---------------------------------------------------------------------------
# External caller → Node A  (initiate a full BB84 session)
# ---------------------------------------------------------------------------

@dataclass
class InitiateRequest(_Model):
    num_bits: int = 256
    eve: bool = False
    plaintext: str = "Hello from Node A"

    def __post_init__(self):
        if self.num_bits < 64:
            raise ValueError("num_bits must be at least 64 for meaningful key material")
        if not isinstance(self.plaintext, str) or not self.plaintext:
            raise ValueError("plaintext must be a non-empty string")


# ---------------------------------------------------------------------------
# Node A → caller  (session summary — also stored in _sessions cache)
# ---------------------------------------------------------------------------

@dataclass
class SessionResult(_Model):
    session_id: str
    qber: float
    valid: bool
    eve_detected: bool
    num_sifted_bits: int
    encrypted: bool
    ciphertext_len: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
