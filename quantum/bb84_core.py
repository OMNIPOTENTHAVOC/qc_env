"""
Layer 2 + 3 — BB84 Core (distributed-aware)

Responsibilities:
  - Alice's quantum state preparation (Layer 2)
  - Sifting, QBER, and key validity logic (Layer 3)

The class is split into two phases to support a distributed architecture
where Bob measures on a separate node (Node B) over HTTP:

  Phase 1 — prepare()
      Alice generates bits/bases, encodes qubits, passes through channel.
      Returns the (post-channel) Qiskit circuit and Alice's internal state.
      Node A sends the circuit to Node B and waits for Bob's results.

  Phase 2 — process()
      Once Node A has Bob's bases and results back from Node B,
      this phase performs sifting, QBER calculation, and key acceptance.

Single-node usage (e.g. tests) can still call run() which executes both
phases with an internal Bob measurement.
"""
from dataclasses import dataclass

from qiskit import QuantumCircuit

from quantum.basis import generate_bits, generate_bases
from quantum.channel import transmit
from quantum.encoding import encode
from quantum.measurement import measure_with_bases


# ---------------------------------------------------------------------------
# Result dataclasses — typed return values instead of raw dicts
# ---------------------------------------------------------------------------

@dataclass
class PrepareResult:
    """Output of Phase 1 — Alice's state and the (post-channel) circuit."""
    circuit: QuantumCircuit   # Ready to send to Bob
    alice_bits: list[int]
    alice_bases: list[int]
    num_bits: int


@dataclass
class ProtocolResult:
    """Output of Phase 2 — sifting and key validity decision."""
    sifted_alice: list[int]
    sifted_bob: list[int]
    sifted_indices: list[int]
    qber: float
    valid: bool
    eve_detected: bool
    num_sifted_bits: int

    @property
    def key(self) -> list[int]:
        """Alice's half of the sifted key — used for key derivation."""
        return self.sifted_alice


# ---------------------------------------------------------------------------
# BB84Core
# ---------------------------------------------------------------------------

class BB84Core:
    def __init__(
        self,
        num_bits: int = 256,
        eve: bool = False,
        qber_threshold: float = 0.11,
        min_sifted_bits: int = 32,
    ):
        if num_bits <= 0:
            raise ValueError(f"num_bits must be positive, got {num_bits}")
        if not 0.0 <= qber_threshold <= 1.0:
            raise ValueError(f"qber_threshold must be in [0, 1], got {qber_threshold}")

        self.num_bits = num_bits
        self.eve = eve
        self.qber_threshold = qber_threshold
        self.min_sifted_bits = min_sifted_bits

    # ------------------------------------------------------------------
    # Phase 1 — Alice's preparation
    # ------------------------------------------------------------------
    def prepare(self) -> PrepareResult:
        """
        Generate Alice's bits and bases, encode into a Qiskit circuit,
        and pass through the quantum channel (with or without Eve).

        Returns the circuit and Alice's internal state. The circuit should
        be serialised (qasm()) and sent to Bob for measurement.
        """
        alice_bits = generate_bits(self.num_bits)
        alice_bases = generate_bases(self.num_bits)
        qc = encode(alice_bits, alice_bases)
        qc = transmit(qc, eve=self.eve)

        return PrepareResult(
            circuit=qc,
            alice_bits=alice_bits,
            alice_bases=alice_bases,
            num_bits=self.num_bits,
        )

    # ------------------------------------------------------------------
    # Phase 2 — Sifting, QBER, key validity
    # ------------------------------------------------------------------
    def process(
        self,
        alice_bits: list[int],
        alice_bases: list[int],
        bob_bases: list[int],
        bob_results: list[int],
    ) -> ProtocolResult:
        """
        Given Alice's internal state and Bob's returned bases/results,
        perform sifting and compute QBER.

        This phase runs on Node A after receiving Bob's response over HTTP.
        """
        # Sifting: keep only positions where Alice and Bob chose the same basis
        sifted_alice: list[int] = []
        sifted_bob: list[int] = []
        sifted_indices: list[int] = []

        for i in range(self.num_bits):
            if alice_bases[i] == bob_bases[i]:
                sifted_alice.append(alice_bits[i])
                sifted_bob.append(bob_results[i])
                sifted_indices.append(i)

        # QBER
        if not sifted_alice:
            qber = 1.0
        else:
            errors = sum(1 for a, b in zip(sifted_alice, sifted_bob) if a != b)
            qber = errors / len(sifted_alice)

        # Key validity: both QBER and minimum length must pass
        qber_ok = qber <= self.qber_threshold
        length_ok = len(sifted_alice) >= self.min_sifted_bits
        valid = qber_ok and length_ok

        # Eve is detectable via QBER spike
        eve_detected = qber > self.qber_threshold

        return ProtocolResult(
            sifted_alice=sifted_alice,
            sifted_bob=sifted_bob,
            sifted_indices=sifted_indices,
            qber=qber,
            valid=valid,
            eve_detected=eve_detected,
            num_sifted_bits=len(sifted_alice),
        )

    # ------------------------------------------------------------------
    # Convenience: run both phases locally (useful for unit tests)
    # ------------------------------------------------------------------
    def run(self) -> ProtocolResult:
        """
        Run the full BB84 protocol locally with an internal Bob measurement.
        Intended for testing — in production, Bob measures on Node B.
        """
        prep = self.prepare()
        bob_bases = generate_bases(self.num_bits)
        bob_results = measure_with_bases(prep.circuit, bob_bases)
        return self.process(prep.alice_bits, prep.alice_bases, bob_bases, bob_results)
