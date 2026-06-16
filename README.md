# Secure Messenger — Stage 1

A secured REST API for private messaging built with FastAPI, SQLAlchemy, and SQLite.

Passwords are stored as bcrypt hashes (one-way, never reversible).  
Messages are stored as AES-256-GCM ciphertext (encrypted at rest, decrypted on read).  
Every protected endpoint requires a signed JWT token.

This stage focuses on security fundamentals and clarity over scale. The stack is intentionally small so each security property is easy to inspect and test.

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

## Design Decisions and Trade-offs

### Why FastAPI + SQLAlchemy + SQLite (for Stage 1)

- FastAPI gives typed request/response models and automatic OpenAPI docs, which makes API behavior explicit and testable.
- SQLAlchemy keeps data access structured and easy to migrate later.
- SQLite is zero-setup and ideal for local development and automated tests.

Trade-offs:
- SQLite is not designed for high write concurrency and multi-instance production deployments.
- This architecture is optimized for a single-process learning environment, not horizontal scale.

What production would change:
- Move to PostgreSQL (or equivalent) with managed backups and connection pooling.
- Add migrations (Alembic), index tuning, and observability around slow queries.

### Why bcrypt for passwords

- Passwords must be one-way and intentionally expensive to verify.
- bcrypt includes a per-password salt and configurable work factor, reducing practical offline cracking speed if hashes leak.

Trade-offs:
- bcrypt verification is slower by design, so login throughput has a CPU cost.
- Work factor must be tuned: too low weakens security, too high hurts latency.

What production would change:
- Periodically increase cost factor as hardware improves.
- Add rate limiting and account lockout/backoff on repeated failed logins.

### Why AES-256-GCM for message encryption (and not AES-CBC)

- AES-GCM provides confidentiality and integrity in one primitive (AEAD).
- If ciphertext or tag is modified, decryption fails instead of returning corrupted plaintext.

Why not AES-CBC:
- CBC does not provide built-in integrity; it requires an additional MAC and careful composition.
- Getting CBC + MAC composition wrong is a common source of security bugs.

Trade-offs:
- Nonce management is critical; nonce reuse under the same key breaks security guarantees.
- Key management is out-of-scope in Stage 1 (single server secret), which is acceptable for learning but not production.

What production would change:
- Store encryption keys in a KMS/HSM, not source or plain env files.
- Introduce key rotation and key versioning per message.
- Add structured handling for crypto failures and alerting.

### Why JWT bearer tokens for auth

- JWTs allow stateless auth checks on each request.
- Signed tokens prevent tampering without server-side session storage.

Trade-offs:
- Revocation is harder than server sessions unless you add blocklists/version checks.
- Token lifetime tuning is a balance between usability and replay window.

What production would change:
- Use short-lived access tokens plus refresh tokens.
- Add token revocation strategy (e.g., jti blacklist or user token version).
- Rotate signing keys and publish key IDs.

### Why request/response polling model (and not SSE/WebSockets)

- Stage 1 uses simple REST endpoints to keep authentication, encryption, and authorization logic easy to reason about.
- Polling keeps deployment and debugging straightforward for beginners.

Trade-offs:
- Polling adds latency and unnecessary requests compared to push channels.
- It is less efficient for real-time chat UX.

What production would change:
- Add WebSockets (or SSE for one-way server push) for near real-time delivery.
- Keep the same auth/encryption boundaries but enforce per-connection auth and message rate limits.

### What breaks on server restart in Stage 1

- In-memory process state (if any) is lost immediately.
- Existing JWTs remain valid only if signing secret and validation settings are unchanged.
- Encrypted messages in DB remain decryptable only if encryption key material is unchanged.

What production would change:
- Use explicit secret management, key versioning, and documented rotation procedures.
- Add startup checks to fail fast when required secrets are missing/mismatched.
- Run multi-instance deployment with health checks and graceful restarts.

---

## Stage Scope vs Production

This project is intentionally scoped as a secure-learning baseline:
- Strong primitives (bcrypt, JWT signatures, AES-GCM)
- Clear trust boundaries
- Automated tests around auth and crypto behavior

It is not yet a full production messaging system. A production hardening roadmap would include:
- Secret management (KMS/HSM), key rotation, and key IDs
- Database upgrade and migrations
- Rate limiting, abuse prevention, and auditing
- Real-time transport (WebSockets/SSE)
- Monitoring, alerting, and incident response runbooks

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
