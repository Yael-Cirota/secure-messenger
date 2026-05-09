# Secure Messenger: From Stage 1 to Full Implementation

Congratulations! You've built the foundation. Now let's add **real-time messaging**.

In Stage 1, you created a REST API where clients poll for messages (call `GET /messages` repeatedly).
In Stage 2, you'll add **Server-Sent Events (SSE)** so the server *pushes* messages to clients instantly,
and build a **CLI client** that runs in your terminal.

---

## What You'll Add

### 1. **Broadcaster Module** (`server/broadcaster.py`) — NEW FILE
The backbone of real-time messaging. When any user sends a message, this broadcasts it to all
connected clients instantly.

**What it does:**
- Maintains a queue of connected SSE clients
- When a new message arrives, publishes it to all connected clients
- Clients receive updates without polling

**Complexity:** Medium — it's a concurrent queue manager with async/await

**Key concepts:**
- `asyncio.Queue` for fan-out messaging
- Background task management

---

### 2. **SSE Stream Endpoint** (`server/main.py`) — NEW ROUTE
Add a new route `GET /stream` that opens a persistent connection to each client.

**Route signature:**
```python
@app.get("/stream")
async def stream(
    db: Session = Depends(get_db),
    username: str = Depends(require_auth),
) -> EventSourceResponse:
    """SSE stream — client holds open connection, receives messages in real time."""
    # Connect to broadcaster
    # Send each message as it arrives
    # Client never disconnects until they close the terminal
```

**What happens:**
- Client calls `GET /stream` with their auth token
- Connection stays open indefinitely
- When a message is sent (via `POST /messages`), the server publishes it to this stream
- The client receives it instantly without polling

**Key concepts:**
- `sse_starlette.sse.EventSourceResponse` — SSE protocol wrapper
- Async generators for streaming
- Connection persistence

---

### 3. **Update `/messages` Route** (`server/main.py`)
Your POST /messages route already encrypts and saves. Now add broadcasting:

**After saving the message, add:**
```python
# Broadcast the decrypted message to all connected SSE clients
await broadcaster.publish(response.model_dump(mode="json"))
```

This is just **one extra line** in your existing send_message() function.

---

### 4. **CLI Client** (`client/client.py`) — NEW FILE
A terminal program that connects to the server, lets users send/receive messages interactively.

**What it does:**
- Prompt user to register or login
- Display message history
- Let user type messages and press Enter to send
- Listen to SSE stream in a background thread
- Print incoming messages as they arrive

**Complexity:** Medium — threading + httpx streaming

**Key components:**
- `prompt_auth()` — handle login/registration
- `listen_for_messages()` — background thread that reads SSE stream
- Main loop — read user input, send messages
- `getpass` module — hide password input

**How to run:**
```bash
python -m client.client
```

**Example interaction:**
```
=== Secure Messenger ===
1) Register
2) Login
Choose (1/2): 2
Username: alice
Password: ••••••••

Welcome, alice!  (type your message and press Enter, or 'quit' to exit)

  [bob → alice]: hey, are you there?
  > yes, just arrived!
  [bob → alice]: great, let's sync later
  >
```

---

### 5. **Seed Script** (`seed.py`) — ENHANCEMENTS
You may have a basic seed.py. Enhance it to:
- Create 3 test users (alice, bob, charlie)
- Send a few messages between them
- Make sure the database is clean before seeding

**Use it to populate the database:**
```bash
python seed.py
```

---

### 6. **Full Test Suite** (`tests/test_app.py`) — EXPAND
Extend your Stage 1 tests to cover:
- **SSE stream connection:** client opens `/stream`, receives broadcast messages
- **Real-time delivery:** message sent via POST → appears in all connected SSE streams
- **Token validation:** invalid/expired tokens are rejected on `/stream`
- **Broadcast isolation:** only the authenticated user's messages arrive in their stream

**New test examples:**
```python
def test_sse_stream_receives_broadcast():
    """Connect to /stream, send message, verify it arrives."""

def test_only_sender_sees_targeted_messages():
    """Alice sends to Bob. Charlie shouldn't see it if /stream is not targeted."""

def test_concurrent_clients():
    """Two clients send simultaneously — both receive both messages."""
```

---

## Implementation Order

Follow these steps in sequence:

### Step 1: Add the Broadcaster
- Create `server/broadcaster.py`
- Implement a simple queue-based broadcaster with `publish()` and `subscribe()` methods
- Test it in isolation (optional but recommended)

### Step 2: Update `/messages` route
- In `server/main.py`, find your `send_message()` function
- Make it async: change `def` to `async def`
- Add one line after `db.commit()`: `await broadcaster.publish(...)`
- Update the return type to match

### Step 3: Add `/stream` endpoint
- In `server/main.py`, add a new route function
- Use `@app.get("/stream")`
- Return an `EventSourceResponse` that yields messages from the broadcaster
- Keep the connection open for the lifetime of the client connection

### Step 4: Build the CLI client
- Create `client/client.py`
- Start with auth (register/login)
- Then add the background SSE listener thread
- Finally add the main loop for sending messages

### Step 5: Create seed.py
- Populate test data for manual testing
- Make it idempotent (safe to run multiple times)

### Step 6: Expand tests
- Test SSE stream connection and message delivery
- Test concurrent clients
- Test auth enforcement on `/stream`

---

## Key Files to Review in Full Implementation

The `secure-messenger-full/` folder contains the complete solution. Compare these files with yours:

| File | What to notice |
|------|---|
| `server/broadcaster.py` | How to manage concurrent subscriptions with asyncio |
| `server/main.py` | How routes are wired to broadcaster; async/await patterns |
| `client/client.py` | Threading pattern for concurrent I/O; SSE parsing |
| `seed.py` | How to set up test data |
| `tests/test_app.py` | Patterns for testing async endpoints and SSE |

---

## Bonus Challenges

If you finish quickly, try these extensions:

### Bonus 1: Private Messages (Low Complexity)

**Goal:** Send a message to a specific recipient (not broadcast to all).

**Changes needed:**
1. Add `recipient` field to Message schema and model (you already have this!)
2. Modify `/stream` to only send messages where the client is sender OR recipient
3. Update seed.py to use the recipient field

**Complexity:** Low — just add a WHERE clause filter

**Implementation:**
```python
# In /stream, when publishing:
# Only send to user if they are the sender OR the recipient
if message.sender == username or message.recipient == username:
    await send_to_client(message)
```

**Time estimate:** 30 minutes

---

### Bonus 2: Prevent Duplicate Login (Medium Complexity)

**Goal:** If a user logs in from two terminals, the second login invalidates the first.

**Approach 1 — Token versioning (simpler):**
- Add a `login_version` field to the User table
- Each time a user logs in, increment their version
- Include the version in the JWT
- On each protected route, validate that the token version matches the user's current version

**Changes needed:**
1. Migrate User model: add `login_version` integer field
2. Update `create_token()` to include version in JWT
3. Update `decode_token()` to extract version
4. Update `require_auth()` to compare token version with DB version
5. In `/login`, increment the user's version

**Complexity:** Medium — requires JWT changes and DB migration

**Time estimate:** 45 minutes

**Approach 2 — Token blocklist (more secure, harder):**
- Maintain a Redis set of revoked tokens
- On new login, revoke all previous tokens
- On protected routes, check if token is in blocklist

**Complexity:** High — requires Redis setup; overkill for a learning project

**Time estimate:** 1-2 hours

**Recommendation:** Use Approach 1 (token versioning) — it's simpler and teaches JWT concepts better.

---

### Bonus 3: User Presence Indicator (Medium Complexity)

**Goal:** Show which users are currently connected and receiving messages.

**Changes needed:**
1. Add an endpoint `GET /users/online` that returns list of connected users
2. Broadcaster tracks who's subscribed
3. Send presence updates when users connect/disconnect

**Implementation:**
```python
@app.get("/users/online")
def get_online_users(username: str = Depends(require_auth)):
    """Return list of currently connected users."""
    return {"online_users": list(broadcaster.subscribers.keys())}
```

**Complexity:** Medium — requires tracking subscriptions

**Time estimate:** 30 minutes

---

### Bonus 4: Message Editing / Deletion (Medium-High Complexity)

**Goal:** Allow users to edit or delete messages they sent.

**Changes needed:**
1. Add to Message model: `updated_at`, `is_deleted` (soft delete)
2. Add new routes: `PATCH /messages/{id}`, `DELETE /messages/{id}`
3. Update `/messages` GET to exclude deleted messages
4. When editing/deleting, broadcast the update

**Complexity:** Medium-High — requires transaction handling, soft deletes, broadcast coordination

**Time estimate:** 1 hour

---

## Testing Checklist

Before you claim Stage 2 complete:

```
 □  Client can register via /register
 □  Client can login via /login and stores token
 □  Client opens /stream and receives messages
 □  When user A sends a message, user B receives it in real time via /stream
 □  Open two clients side-by-side
      - Type in one terminal
      - Message appears in the other instantly
 □  Close one client — the other keeps receiving messages
 □  /stream rejects requests without valid token
 □  All Stage 1 tests still pass
 □  New tests for SSE stream pass
 □  seed.py runs without errors
```

---

## Common Pitfalls

**Pitfall 1: Forgetting `await` on async calls**
```python
# ❌ WRONG
await broadcaster.publish(msg)  # without async in function signature

# ✅ RIGHT
async def send_message(...):
    await broadcaster.publish(msg)
```

**Pitfall 2: Holding onto the token in the browser**
The token is valid for 24 hours. If you modify the code and restart the server with a different key,
old tokens won't work. This is expected.

**Pitfall 3: SSE clients not reconnecting**
If the server crashes, the client's SSE connection dies. The client should gracefully handle this
(catch the exception, prompt to reconnect).

**Pitfall 4: Database locks under concurrent writes**
SQLite has limited concurrent write capacity. If tests fail with "database is locked", use `check_same_thread=False`
or switch to PostgreSQL.

---

## Files to Create or Modify

### New files:
- `server/broadcaster.py` — SSE fan-out manager
- `client/client.py` — CLI client program
- `seed.py` — (if not present) database seeding

### Modified files:
- `server/main.py` — add `/stream` route, make send_message async
- `tests/test_app.py` — add SSE and concurrency tests
- `requirements.txt` — add `sse-starlette` and `httpx`

---

## Helpful Links & Concepts

- **Server-Sent Events (SSE):** https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- **Starlette SSE:** https://github.com/sysid/sse-starlette
- **Python asyncio:** https://docs.python.org/3/library/asyncio.html
- **httpx streaming:** https://www.python-httpx.org/quickstart/#streaming-responses

---

## How to Get Unstuck

1. **Check the full implementation** in `secure-messenger-full/` — it has all the answers
2. **Read the complete solution carefully** — don't just copy-paste; understand each line
3. **Run the full implementation first** — get a feel for how it should work
4. **Compare your output with the reference** — use `diff` or your IDE's comparison tool
5. **Print debug info** — add `print()` statements to trace execution flow
6. **Read error messages carefully** — they usually tell you exactly what's wrong

---

## Final Notes

Stage 2 is where things get real. You're no longer just storing data — you're building live,
concurrent systems. Pay attention to:

- **Async/await:** Understand why routes need to be async
- **Concurrency:** Multiple clients connecting at once; what could go wrong?
- **Thread safety:** The broadcaster is accessed from multiple threads
- **Error handling:** What happens if the client disconnects mid-stream?

Good luck! 🚀
