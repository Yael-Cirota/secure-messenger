"""
auth.py — Password hashing and JWT token logic.

╔══════════════════════════════════════════════╗
║  YOUR TASK: implement the five functions.    ║
╚══════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT 1 — WHY WE HASH PASSWORDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Imagine every password in your database was stored as plain text.
  One database leak → every user's password is exposed, forever.

  bcrypt solves this by being a ONE-WAY function:
    hash("secret123") → "$2b$12$eImiTXuW..." (a fingerprint)
    There is no reverse. The original password is gone.

  When a user logs in, we don't un-hash. Instead we re-hash the
  typed password and compare the two fingerprints. If they match —
  the password was correct, without ever knowing the original.

  bcrypt is also INTENTIONALLY SLOW (has a "cost factor").
  Even if someone steals your DB, brute-forcing takes years.

  Use:
    import bcrypt
    hash  = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    match = bcrypt.checkpw(password.encode(), stored_hash.encode())

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT 2 — WHY WE USE JWT TOKENS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  After a successful login, the server gives the client a JWT token.
  Think of it as a signed wristband at a concert:
    - It proves you paid (authenticated) without checking your ID again
    - It has an expiry date printed on it
    - The bouncer (server) can verify it's real by checking the signature
    - The server never needs to look up a database to validate it

  A JWT has three parts, separated by dots:
    header.payload.signature
    eyJhbGc...  .eyJzdWI...  .SflKxw...

  The payload contains the username and expiry time — readable but
  tamper-proof (changing anything breaks the signature).

  Use:
    from jose import jwt, JWTError
    token   = jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm="HS256")
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT 3 — FASTAPI DEPENDENCY INJECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  require_auth() is a FastAPI "dependency". Instead of copy-pasting
  token validation into every route, you declare it once here and
  inject it into any route that needs it:

    @router.get("/messages")
    def get_messages(username: str = Depends(require_auth)):
        # username is already validated — if we got here, the token was valid
        ...

  FastAPI calls require_auth() automatically before your route runs.
  If the token is missing or invalid, it raises HTTP 401 and your
  route never executes.

  The HTTPBearer() helper extracts the token from the header:
    Authorization: Bearer eyJhbGc...
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncio
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


SECRET_KEY = "change-this-to-a-long-random-string-in-production"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

_bearer = HTTPBearer()


# ---------------------------------------------------------------------------
# TODO 1 — Hash a plain-text password with bcrypt
# ---------------------------------------------------------------------------
async def hash_password(plain: str) -> str:
    """
    Return a bcrypt hash of the password.
    This is what gets stored in the database — never the plain text.
    """
    return await asyncio.to_thread(
        lambda: bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
    )


# ---------------------------------------------------------------------------
# TODO 2 — Check a plain-text password against a stored bcrypt hash
# ---------------------------------------------------------------------------
async def verify_password(plain: str, hashed: str) -> bool:
    """
    Return True if the plain password matches the stored hash.
    Used at login time.
    """
    return await asyncio.to_thread(
        lambda: bcrypt.checkpw(plain.encode(), hashed.encode())
    )


# ---------------------------------------------------------------------------
# TODO 3 — Create a signed JWT token for a given username
# ---------------------------------------------------------------------------
def create_token(username: str) -> str:
    """
    Build a JWT payload with the username and an expiry time,
    then sign and return it as a string.
    Hint: use TOKEN_EXPIRE_HOURS and datetime.now(timezone.utc).
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# TODO 4 — Decode and validate a JWT token
# ---------------------------------------------------------------------------
def decode_token(token: str) -> Optional[str]:
    """
    Decode the token and return the username ("sub" field).
    Return None if the token is invalid or expired — do not raise.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# TODO 5 — FastAPI dependency: enforce authentication on a route
# ---------------------------------------------------------------------------
def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    """
    Extract the Bearer token from the Authorization header,
    validate it with decode_token(), and return the username.
    Raise HTTP 401 if the token is missing, invalid, or expired.

    Usage in a route:
        def my_route(username: str = Depends(require_auth)):
    """
    username = decode_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return username
