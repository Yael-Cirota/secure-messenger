"""
routes.py — All API route handlers.

╔══════════════════════════════════════════════╗
║  YOUR TASK: implement the four routes.       ║
╚══════════════════════════════════════════════╝

WHY A SEPARATE routes.py?
  In real projects, main.py only creates the app and wires things together.
  The actual logic lives in dedicated files — one per feature area.
  This keeps files small, focused, and easy to navigate.
  main.py imports this router and registers it with one line.

THE FOUR ROUTES YOU NEED TO IMPLEMENT:

  ┌─────────────────────────────────────────────────────────────────────┐
  │ POST /register                                                      │
  │   Receives: RegisterRequest (username, password)                    │
  │   1. Check if the username is already taken → return 400 if so     │
  │   2. Hash the password (NEVER store plain text)                     │
  │   3. Save the new User to the database                              │
  │   4. Return a success message                                       │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │ POST /login                                                         │
  │   Receives: LoginRequest (username, password)                       │
  │   1. Find the user in the database → return 401 if not found       │
  │   2. Verify the password against the stored hash → 401 if wrong    │
  │   3. Create and return a JWT token                                  │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │ POST /messages                          [requires valid JWT]        │
  │   Receives: SendMessageRequest (content, recipient)                 │
  │   1. Encrypt the content with encrypt()                             │
  │   2. Save a new Message row (sender=current user, recipient=...)    │
  │   3. Return the message as MessageResponse (with decrypted content) │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │ GET /messages                           [requires valid JWT]        │
  │   1. Fetch all messages from the database                           │
  │   2. Decrypt each message's ciphertext before returning             │
  │   3. Return a list of MessageResponse objects                       │
  │                                                                     │
  │   THINK ABOUT: should a user see ALL messages, or only those        │
  │   where they are the sender or recipient?                           │
  └─────────────────────────────────────────────────────────────────────┘

USEFUL IMPORTS ALREADY PROVIDED BELOW.
USEFUL PATTERN — how to query the database:
  user = db.query(User).filter(User.username == "alice").first()
  messages = db.query(Message).order_by(Message.created_at).all()

USEFUL PATTERN — how to save a new row:
  new_user = User(username="alice", password_hash="$2b$...")
  db.add(new_user)
  db.commit()
  db.refresh(new_user)   ← fills in the auto-generated id and created_at
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from .models import get_db
from .schemas import (
    RegisterRequest, LoginRequest, TokenResponse,
    SendMessageRequest, MessageResponse, BroadcastEvent,
)
from .auth import hash_password, verify_password, create_token, require_auth
from .crypto import encrypt, decrypt
from .repository import UserRepository, MessageRepository
from .broadcaster import broadcaster


log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# TODO 1 — Register a new user
# ---------------------------------------------------------------------------
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    users = UserRepository(db)
    if await users.get_by_username(body.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="username already taken")
    await users.create(body.username, await hash_password(body.password))
    log.info("Registered user: %s", body.username)
    return {"message": "User registered successfully"}


# ---------------------------------------------------------------------------
# TODO 2 — Login and receive a JWT token
# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    users = UserRepository(db)
    user = await users.get_by_username(body.username)
    if not user or not await verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_token(user.username)
    log.info("Login: %s", user.username)
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# TODO 3 — Send a message (authenticated)
# ---------------------------------------------------------------------------
@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(require_auth),
):
    messages = MessageRepository(db)
    msg = await messages.create(
        sender=username,
        recipient=body.recipient,
        ciphertext=encrypt(body.content),
    )
    log.info("Message from %s to %s", username, body.recipient)
    response = MessageResponse(
        id=msg.id,
        sender=msg.sender,
        recipient=msg.recipient,
        content=body.content,
        created_at=msg.created_at,
    )
    await broadcaster.publish(
        BroadcastEvent(
            id=msg.id,
            sender=msg.sender,
            recipient=msg.recipient,
            content=body.content,
            created_at=msg.created_at,
        )
    )
    return response


# ---------------------------------------------------------------------------
# TODO 4 — Fetch messages (authenticated)
# ---------------------------------------------------------------------------
@router.get("/messages", response_model=list[MessageResponse])
async def get_messages(
    db: AsyncSession = Depends(get_db),
    username: str = Depends(require_auth),
):
    messages = MessageRepository(db)
    rows = await messages.get_for_user(username)
    return [
        MessageResponse(
            id=row.id,
            sender=row.sender,
            recipient=row.recipient,
            content=decrypt(row.ciphertext),
            created_at=row.created_at,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# SSE Stream — persistent connection, receives messages in real time
# ---------------------------------------------------------------------------
@router.get("/stream")
async def stream(
    username: str = Depends(require_auth),
) -> EventSourceResponse:
    """SSE stream — client holds open connection, receives messages in real time."""

    async def event_generator():
        async with broadcaster.subscribe() as queue:
            while True:
                event: BroadcastEvent = await queue.get()
                # Stream isolation: a user receives only messages where they are
                # the sender or recipient.
                if event.sender != username and event.recipient != username:
                    continue
                yield {"data": event.model_dump_json()}

    return EventSourceResponse(event_generator())
