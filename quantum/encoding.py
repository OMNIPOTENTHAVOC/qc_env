from qiskit import QuantumCircuit

def encode(bits: list[int], bases: list[int]) -> QuantumCircuit:
    """
    Encode classical bits into a quantum circuit using BB84 rules.

    basis: 0 = Z, 1 = X
    """
    n = len(bits)
    qc = QuantumCircuit(n, n)

    for i in range(n):
        bit = bits[i]
        basis = bases[i]

        if bit == 0:
            if basis == 1:
                qc.h(i)
        else:  # bit == 1
            if basis == 0:
                qc.x(i)
            else:  # basis == 1
                qc.x(i)
                qc.h(i)

    qc.barrier()
    return qc
