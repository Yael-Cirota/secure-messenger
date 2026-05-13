"""
schemas.py — The shapes of requests and responses.

╔══════════════════════════════════════════════════════════════╗
║  THIS FILE IS COMPLETE — you do not need to change anything. ║
╚══════════════════════════════════════════════════════════════╝

WHAT IS A SCHEMA?
  A schema describes what JSON the API expects to receive, and what
  JSON it promises to send back.

  FastAPI uses these classes to:
    - Automatically validate incoming requests
      (missing field? wrong type? → instant 422 error, your code never runs)
    - Automatically generate the /docs page
    - Document exactly what each route accepts and returns

WHY SEPARATE FROM MODELS?
  DB models (models.py) describe how data is STORED.
  Schemas describe what the API ACCEPTS and RETURNS.
  These are deliberately different — for example, we never expose
  password_hash in a response, even though it lives in the User model.
"""

from datetime import datetime
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class SendMessageRequest(BaseModel):
    content:   str = Field(min_length=1, max_length=2000)
    recipient: str = Field(min_length=3, max_length=50)   # who is this message for?


class MessageResponse(BaseModel):
    id:         int
    sender:     str
    recipient:  str
    content:    str       # always decrypted plain text — never expose ciphertext
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Broadcast (Value Object / Typed Event)
# ---------------------------------------------------------------------------

class BroadcastEvent(BaseModel):
    """Typed contract for events published to SSE subscribers."""
    id:         int
    sender:     str
    recipient:  str
    content:    str
    created_at: datetime
