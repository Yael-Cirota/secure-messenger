# Secure Messenger — Stage 1

A secured REST API for private messaging built with FastAPI, SQLAlchemy, and SQLite.

Passwords are stored as bcrypt hashes (one-way, never reversible).  
Messages are stored as AES-256-GCM ciphertext (encrypted at rest, decrypted on read).  
Every protected endpoint requires a signed JWT token.

---

## Project Structure

```
secure-messenger-stage1/
├── client/
│   └── index.html    # Browser client — gradient UI, no build step required
├── server/
│   ├── main.py       # App entry point — creates FastAPI app, registers router
│   ├── models.py     # SQLAlchemy ORM tables (User, Message)
│   ├── auth.py       # Password hashing (bcrypt) + JWT token logic
│   ├── crypto.py     # AES-256-GCM encrypt/decrypt helpers
│   ├── routes.py     # The four API route handlers
│   └── schemas.py    # Pydantic request/response shapes
├── tests/
│   └── test_app.py   # Full test suite (17 tests)
├── requirements.txt
└── STAGE_1.md        # Full project spec and learning material
```

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Running the Server

```bash
cd secure-messenger-stage1
uvicorn server.main:app --reload
```

Then open **http://localhost:8000/docs** for the interactive API UI.

---

## Browser Client

Open `client/index.html` directly in your browser (no build step needed).  
Make sure the server is running first — the client talks to `http://localhost:8000`.

Features:
- Register and login with a username/password
- Send encrypted messages to any registered user
- View your sent and received messages (automatically decrypted)

---

## API Endpoints

| Method | Endpoint | Auth required | Description |
|--------|----------|:---:|-------------|
| `POST` | `/register` | No | Create a new account |
| `POST` | `/login` | No | Log in and receive a JWT token |
| `POST` | `/messages` | Yes | Send an encrypted message |
| `GET` | `/messages` | Yes | Read your messages (decrypted) |

### Example flow

**Register**
```http
POST /register
{"username": "alice", "password": "secret123"}
→ 201 Created
```

**Login**
```http
POST /login
{"username": "alice", "password": "secret123"}
→ {"access_token": "eyJ...", "token_type": "bearer"}
```

**Send a message** *(Authorization: Bearer <token>)*
```http
POST /messages
{"content": "Can we meet at 3pm?", "recipient": "bob"}
→ 201 Created, returns message with decrypted content
```

**Read messages** *(Authorization: Bearer <token>)*
```http
GET /messages
→ [{"sender": "alice", "recipient": "bob", "content": "Can we meet at 3pm?", ...}]
```

---

## Running Tests

```bash
pytest tests/ -v
```

All 17 tests should pass. The test suite covers:
- Registration (success, duplicate username, short password)
- Login (success, wrong password, unknown user)
- Token validation (missing, fake, valid)
- Encryption (round-trip, nonce uniqueness, tamper detection, DB storage)
- Messaging (send, read, user isolation)

---

## Security Properties

| Threat | Protection |
|--------|-----------|
| Database stolen | Passwords are bcrypt hashes — uncrackable without brute force. Messages are AES-256-GCM ciphertext — unreadable without the key. |
| Forged identity | JWT tokens are signed with a server secret — any tampering breaks the signature. |
| Token replay | Tokens expire after 24 hours. |
| Message tampering | AES-GCM provides integrity — a modified ciphertext raises an exception instead of silently decrypting garbage. |
| User snooping | `GET /messages` only returns messages where the requester is sender **or** recipient. |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM / SQLite access |
| `bcrypt` | Password hashing |
| `python-jose` | JWT creation and validation |
| `cryptography` | AES-256-GCM encryption |
| `pytest` / `httpx` | Testing |
