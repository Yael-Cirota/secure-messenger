"""
crypto.py — AES-256-GCM encryption for messages stored in the database.

╔══════════════════════════════════════════════════════════════╗
║  THIS FILE IS COMPLETE — you do not need to change anything. ║
║  Read it, understand it, then use encrypt() and decrypt()    ║
║  in your routes.                                             ║
╚══════════════════════════════════════════════════════════════╝

HOW IT WORKS (the short version):
  The server has one secret key (256 bits, generated at startup).
  encrypt("hello") → scrambles the text into unreadable base64.
  decrypt(blob)    → unscrambles it back to "hello".
  Without the key, decryption is impossible.

WHY AES-GCM AND NOT JUST AES?
  GCM gives us two guarantees at once:
    1. Confidentiality — the content is hidden.
    2. Integrity      — if anyone tampers with the stored blob,
                        decryption raises an exception instead of
                        silently returning garbage.

WHY A FRESH NONCE EVERY TIME?
  Even if Alice sends "hello" ten times, each encrypted blob looks
  completely different. An attacker watching the database cannot
  detect repeated messages.

  The nonce is NOT secret — it is stored alongside the ciphertext.
  Its only job is to make each encryption unique.
"""

import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# 32 bytes = 256-bit key. Persisted to a local file so the key survives
# server restarts and stored messages remain decryptable.
# In production: load this from an environment variable instead.
_KEY_FILE = os.path.join(os.path.dirname(__file__), "..", "secret.key")

def _load_or_create_key() -> bytes:
    try:
        with open(_KEY_FILE, "rb") as f:
            key = f.read()
            if len(key) == 32:
                return key
    except FileNotFoundError:
        pass
    key = os.urandom(32)
    with open(_KEY_FILE, "wb") as f:
        f.write(key)
    return key

_KEY: bytes = _load_or_create_key()


def encrypt(plaintext: str) -> str:
    """
    Encrypt a string. Returns a base64 blob safe to store in the database.

    Blob layout (concatenated, then base64-encoded):
        [ nonce: 12 bytes ][ ciphertext + auth-tag: variable ]
    """
    aesgcm = AESGCM(_KEY)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(blob: str) -> str:
    """
    Decrypt a blob produced by encrypt(). Raises an exception if tampered with.
    """
    raw = base64.b64decode(blob.encode())
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_KEY)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
