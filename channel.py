from quantum.measurement import measure_with_bases
from quantum.encoding import encode
from quantum.basis import generate_bases


def transmit_no_eve(qc):
    """
    No attack: direct transmission
    """
    return qc


def transmit_with_eve(qc):
    """
    Simulate intercept-resend attack by Eve.

    Steps:
    1. Eve chooses random bases
    2. Measures incoming qubits
    3. Re-encodes based on her measurement
    4. Sends new circuit to Bob
    """

    num_bits = qc.num_qubits

    # Step 1: Eve chooses random bases
    eve_bases = generate_bases(num_bits)

    # Step 2: Eve measures Alice's qubits
    eve_bits = measure_with_bases(qc, eve_bases)

    # Step 3: Eve re-encodes her measured bits
    new_qc = encode(eve_bits, eve_bases)

    return new_qc


def transmit(qc, eve: bool = False):
    """
    Main channel function used by core.

    If eve=False → clean channel  
    If eve=True → intercept-resend attack
    """
    if eve:
        return transmit_with_eve(qc)
    return transmit_no_eve(qc)
