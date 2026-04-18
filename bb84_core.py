from quantum.basis import generate_bits, generate_bases
from quantum.encoding import encode
from quantum.measurement import measure_with_bases
from quantum.channel import transmit


class BB84Core:
    def __init__(self, bit_num: int = 20, eve: bool = False):
        self.bit_num = bit_num
        self.eve = eve

    def run(self):
        # -------------------------
        # STEP 1: Alice preparation
        # -------------------------
        alice_bits = generate_bits(self.bit_num)
        alice_bases = generate_bases(self.bit_num)

        qc = encode(alice_bits, alice_bases)

        # -------------------------
        # STEP 2: Channel (Eve or clean)
        # -------------------------
        qc = transmit(qc, eve=self.eve)

        # -------------------------
        # STEP 3: Bob measurement bases
        # -------------------------
        bob_bases = generate_bases(self.bit_num)

        bob_results = measure_with_bases(qc, bob_bases)

        # -------------------------
        # STEP 4: Sifting (basis match only)
        # -------------------------
        sifted_alice = []
        sifted_bob = []

        for i in range(self.bit_num):
            if alice_bases[i] == bob_bases[i]:
                sifted_alice.append(alice_bits[i])
                sifted_bob.append(bob_results[i])

        # -------------------------
        # STEP 5: QBER calculation
        # -------------------------
        if len(sifted_alice) == 0:
            qber = 1.0
        else:
            errors = sum(
                1 for a, b in zip(sifted_alice, sifted_bob) if a != b
            )
            qber = errors / len(sifted_alice)

        # -------------------------
        # STEP 6: Key validity
        # -------------------------
        threshold = 0.1
        valid = qber <= threshold

        # -------------------------
        # OUTPUT
        # -------------------------
        return {
            "alice_bits": alice_bits,
            "alice_bases": alice_bases,
            "bob_bases": bob_bases,
            "bob_results": bob_results,
            "sifted_alice": sifted_alice,
            "sifted_bob": sifted_bob,
            "qber": qber,
            "valid": valid
        }
