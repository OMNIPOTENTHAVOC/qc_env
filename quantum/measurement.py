from qiskit import Aer, execute, QuantumCircuit


# Use QASM simulator for probabilistic measurement
backend = Aer.get_backend('qasm_simulator')


def apply_measurement_basis(qc: QuantumCircuit, bases: list[int]) -> QuantumCircuit:
    """
    Apply Bob's measurement bases to the circuit.

    basis: 0 = Z (do nothing)
           1 = X (apply H before measurement)
    """
    n = len(bases)

    for i in range(n):
        if bases[i] == 1:
            qc.h(i)

    return qc


def measure(qc: QuantumCircuit) -> list[int]:
    """
    Perform measurement on all qubits and return results as list of bits.
    """
    n = qc.num_qubits

    # Add measurement operations
    qc.measure(range(n), range(n))

    # Execute circuit
    job = execute(qc, backend, shots=1)
    result = job.result()
    counts = result.get_counts()

    # Extract bitstring result
    bitstring = list(counts.keys())[0]

    # Reverse due to Qiskit bit order (IMPORTANT)
    bitstring = bitstring[::-1]

    return [int(b) for b in bitstring]


def measure_with_bases(qc: QuantumCircuit, bases: list[int]) -> list[int]:
    """
    Full measurement pipeline:
    1. Apply measurement bases
    2. Measure
    3. Return classical results
    """
    qc_copy = qc.copy()  # avoid mutating original circuit

    qc_copy = apply_measurement_basis(qc_copy, bases)
    results = measure(qc_copy)

    return results
