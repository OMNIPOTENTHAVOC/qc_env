import numpy as np

rng = np.random.default_rng()

def generate_bits(n: int) -> list[int]:
    return rng.integers(0, 2, size=n).tolist()

def generate_bases(n: int) -> list[int]:
    return rng.integers(0, 2, size=n).tolist()
