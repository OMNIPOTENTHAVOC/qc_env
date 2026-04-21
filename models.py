"""
Shared Layer — Integration Contract
Defines all request/response shapes used between Flask nodes.
Both Node A and Node B import from here to ensure consistent serialisation.
"""
from dataclasses import dataclass, field
from typing import Optional
import time


# ---------------------------------------------------------------------------
# Node A → Node B  (quantum channel: send encoded circuit)
# ---------------------------------------------------------------------------

@dataclass
class MeasureRequest:
    """Node A sends the (post-channel) QASM circuit to Node B for measurement."""
    qasm: str
    num_qubits: int


@dataclass
class MeasureResponse:
    """Node B returns its randomly chosen bases and measured bit results."""
    bob_bases: list[int]
    bob_results: list[int]


# ---------------------------------------------------------------------------
# Node A → Node B  (classical channel: sifting confirmation)
# ---------------------------------------------------------------------------

@dataclass
class ConfirmKeyRequest:
    """
    After sifting, Node A tells Node B which indices survived basis matching,
    the computed QBER, and whether the key was accepted.
    """
    session_id: str
    sifted_indices: list[int]
    qber: float
    valid: bool


@dataclass
class ConfirmKeyResponse:
    acknowledged: bool
    session_id: str


# ---------------------------------------------------------------------------
# External caller → Node A  (initiate a full BB84 session)
# ---------------------------------------------------------------------------

@dataclass
class InitiateRequest:
    num_bits: int = 256
    eve: bool = False
    plaintext: str = "Hello from Node A"


# ---------------------------------------------------------------------------
# Node A → caller  (session summary)
# ---------------------------------------------------------------------------

@dataclass
class SessionResult:
    session_id: str
    qber: float
    valid: bool
    eve_detected: bool
    num_sifted_bits: int
    encrypted: bool
    ciphertext_len: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
