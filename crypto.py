"""
Layer 5 — Security Layer
Implements the two-tier key architecture described in the design:

    C  = Encrypt(DK, Data)   — data encrypted with random Data Key
    EK = Encrypt(K,  DK)     — Data Key wrapped with BB84-derived key K

AES-256-GCM is used throughout:
  - 256-bit keys
  - 96-bit (12-byte) random nonces
  - Authentication tag included automatically by AESGCM

Key rotation is handled by re-wrapping DK under the new K₂:
    EK₂ = Encrypt(K₂, DK)
The ciphertext C never changes on rotation — only EK is replaced.
"""
import os
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def derive_key_from_bits(sifted_bits: list[int]) -> bytes:
    """
    Derive a 32-byte (256-bit) AES key from BB84 sifted bits.

    Uses SHA-256 to compress variable-length sifted output into a fixed-size key.
    Note: real QKD systems use privacy amplification here — SHA-256 is a
    simulation-appropriate shortcut.
    """
    if not sifted_bits:
        raise ValueError("Cannot derive key from empty bit list")
    raw = bytes(sifted_bits)
    return hashlib.sha256(raw).digest()


def generate_data_key() -> bytes:
    """
    Generate a random 256-bit Data Key (DK).
    DK is ephemeral — generated fresh for each encryption session.
    """
    return os.urandom(32)


# ---------------------------------------------------------------------------
# Data encryption  C = Encrypt(DK, plaintext)
# ---------------------------------------------------------------------------

def encrypt_data(dk: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """
    Encrypt plaintext using DK with AES-256-GCM.

    Returns:
        (ciphertext_with_tag, nonce)
    The 16-byte GCM authentication tag is appended to ciphertext by AESGCM.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(dk)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return ciphertext, nonce


def decrypt_data(dk: bytes, ciphertext: bytes, nonce: bytes) -> bytes:
    """
    Decrypt ciphertext using DK.
    Raises cryptography.exceptions.InvalidTag if authentication fails.
    """
    aesgcm = AESGCM(dk)
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)


# ---------------------------------------------------------------------------
# Key wrapping  EK = Encrypt(K, DK)
# ---------------------------------------------------------------------------

def wrap_key(k: bytes, dk: bytes) -> tuple[bytes, bytes]:
    """
    Wrap the Data Key (DK) under the BB84-derived key K.

    Returns:
        (wrapped_dk, nonce)
    Storing (C, EK) means the storage layer holds encrypted data whose key
    is itself encrypted — neither can be used without K, which is never stored.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(k)
    wrapped = aesgcm.encrypt(nonce, dk, associated_data=None)
    return wrapped, nonce


def unwrap_key(k: bytes, wrapped_dk: bytes, nonce: bytes) -> bytes:
    """
    Unwrap DK using K.
    Raises cryptography.exceptions.InvalidTag if K is wrong or data is tampered.
    """
    aesgcm = AESGCM(k)
    return aesgcm.decrypt(nonce, wrapped_dk, associated_data=None)


# ---------------------------------------------------------------------------
# Key rotation  EK₂ = Encrypt(K₂, DK)
# ---------------------------------------------------------------------------

def rotate_wrapped_key(old_k: bytes, new_k: bytes, wrapped_dk: bytes, nonce_old: bytes) -> tuple[bytes, bytes]:
    """
    Rotate the key wrapper without re-encrypting the data.

    Steps:
      1. Unwrap DK using old K
      2. Re-wrap DK using new K₂
      3. Return new (EK₂, nonce₂) to replace stored EK

    The ciphertext C is untouched.
    """
    dk = unwrap_key(old_k, wrapped_dk, nonce_old)
    return wrap_key(new_k, dk)
