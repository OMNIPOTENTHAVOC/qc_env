"""
Layer 6 — Storage Layer
Persists encrypted session data to SQLite.

Security property: this layer stores ONLY (C, EK) pairs.
It has no access to plaintext, DK, or K.
Even with full database access, an attacker cannot recover the original data
without K (the BB84-derived key, which is never written to disk).

Schema:
    sessions(
        id          TEXT PRIMARY KEY,   -- UUID
        ciphertext  BLOB,               -- C = Encrypt(DK, plaintext)
        wrapped_key BLOB,               -- EK = Encrypt(K, DK)
        nonce_data  BLOB,               -- nonce used for C
        nonce_key   BLOB,               -- nonce used for EK
        qber        REAL,               -- recorded for audit/observability
        eve_present INTEGER,            -- 0 or 1, recorded at session time
        timestamp   REAL                -- Unix epoch float
    )
"""
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "qkd.db"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create the sessions table if it does not exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT    PRIMARY KEY,
                ciphertext  BLOB    NOT NULL,
                wrapped_key BLOB    NOT NULL,
                nonce_data  BLOB    NOT NULL,
                nonce_key   BLOB    NOT NULL,
                qber        REAL    NOT NULL,
                eve_present INTEGER NOT NULL,
                timestamp   REAL    NOT NULL
            )
        """)
        conn.commit()


def store_session(
    session_id: str,
    ciphertext: bytes,
    wrapped_key: bytes,
    nonce_data: bytes,
    nonce_key: bytes,
    qber: float,
    eve: bool,
) -> None:
    """
    Persist an encrypted session record.
    Only call this after a valid key exchange — never store failed sessions.
    """
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions
                (id, ciphertext, wrapped_key, nonce_data, nonce_key, qber, eve_present, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                ciphertext,
                wrapped_key,
                nonce_data,
                nonce_key,
                qber,
                int(eve),
                time.time(),
            ),
        )
        conn.commit()


def get_all_sessions() -> list[dict]:
    """
    Return metadata for all stored sessions — no ciphertext or key material.
    Safe to expose to the observability layer.
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, qber, eve_present, timestamp FROM sessions ORDER BY timestamp DESC"
        ).fetchall()

    return [
        {
            "session_id": row[0],
            "qber": row[1],
            "eve_present": bool(row[2]),
            "timestamp": row[3],
        }
        for row in rows
    ]


def get_session_count() -> int:
    init_db()
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]


def update_wrapped_key(session_id: str, new_wrapped_key: bytes, new_nonce_key: bytes) -> None:
    """
    Replace EK for a session after key rotation.
    C (ciphertext) is unchanged — only the key wrapper is updated.
    """
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET wrapped_key = ?, nonce_key = ? WHERE id = ?",
            (new_wrapped_key, new_nonce_key, session_id),
        )
        conn.commit()
