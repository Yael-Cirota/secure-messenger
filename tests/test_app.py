"""
test_app.py — Stage 1 test suite.

╔══════════════════════════════════════════════════════════════════════╗
║  YOUR TASK: the test structure is given. Some tests are complete,   ║
║  others have a TODO for you to finish.                              ║
╚══════════════════════════════════════════════════════════════════════╝

HOW TO RUN:
  pytest tests/ -v

HOW TESTS WORK HERE:
  We use FastAPI's TestClient — it sends real HTTP requests to your app
  without needing to start a server. Each test gets a fresh, empty
  database so tests never interfere with each other.

  The test database is a separate file (test_messenger.db) and is
  wiped clean before every single test.
"""

import asyncio
import json
from datetime import datetime, timezone
import httpx
import pytest
from jose import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from server.main import app
from server.models import Base, get_db
from server.crypto import encrypt, decrypt
from server.broadcaster import broadcaster
from server.routes import stream
from server.schemas import BroadcastEvent
from server.auth import SECRET_KEY, ALGORITHM


# ---------------------------------------------------------------------------
# Test database setup — uses a separate file, wiped before each test
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///./test_messenger.db"
test_engine = create_async_engine(TEST_DB_URL)
TestingSession = async_sessionmaker(bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False)


async def override_get_db():
    async with TestingSession() as db:
        yield db


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    async def setup():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    async def teardown():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register_and_login(client, username="alice", password="secret123") -> str:
    """Register a user and return their JWT token."""
    client.post("/register", json={"username": username, "password": password})
    response = client.post("/login", json={"username": username, "password": password})
    return response.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def next_sse_payload(response, timeout_seconds: float = 2.0):
    """Read one SSE data payload from an EventSourceResponse body iterator."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return None

        try:
            chunk = await asyncio.wait_for(response.body_iterator.__anext__(), remaining)
        except TimeoutError:
            return None

        # When testing the route function directly, body_iterator yields the
        # event dict before EventSourceResponse serializes it.
        if isinstance(chunk, dict):
            raw = chunk.get("data")
            if isinstance(raw, str):
                return json.loads(raw)
            if isinstance(raw, dict):
                return raw
            continue

        text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line.split("data:", 1)[1].strip()
                return json.loads(payload)
    return None


# ===========================================================================
# 1. Authentication tests
# ===========================================================================

class TestAuthentication:

    def test_register_success(self, client):
        response = client.post("/register", json={"username": "alice", "password": "secret123"})
        assert response.status_code == 201

    def test_register_duplicate_username(self, client):
        client.post("/register", json={"username": "alice", "password": "secret123"})
        response = client.post("/register", json={"username": "alice", "password": "other-password"})
        assert response.status_code == 400

    def test_register_password_too_short(self, client):
        response = client.post("/register", json={"username": "alice", "password": "abc"})
        assert response.status_code == 422   # Pydantic rejects it before your code runs

    def test_login_success(self, client):
        client.post("/register", json={"username": "alice", "password": "secret123"})
        response = client.post("/login", json={"username": "alice", "password": "secret123"})
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_login_wrong_password(self, client):
        client.post("/register", json={"username": "alice", "password": "secret123"})
        response = client.post("/login", json={"username": "alice", "password": "wrongpassword"})
        assert response.status_code == 401

    def test_login_unknown_user(self, client):
        response = client.post("/login", json={"username": "ghost", "password": "secret123"})
        assert response.status_code == 401

    def test_messages_require_token(self, client):
        response = client.get("/messages")
        assert response.status_code in (401, 403)

    def test_messages_reject_bad_token(self, client):
        response = client.get("/messages", headers={"Authorization": "Bearer fake-token"})
        assert response.status_code == 401

    def test_messages_accept_valid_token(self, client):
        token = register_and_login(client)
        response = client.get("/messages", headers=auth(token))
        assert response.status_code == 200


# ===========================================================================
# 2. Encryption tests
# ===========================================================================

class TestEncryption:

    def test_encrypt_is_not_plain_text(self):
        assert encrypt("hello world") != "hello world"

    def test_decrypt_round_trip(self):
        original = "this is a secret message"
        assert decrypt(encrypt(original)) == original

    def test_same_message_encrypts_differently_each_time(self):
        # fresh nonce every call → different ciphertext
        assert encrypt("hello") != encrypt("hello")

    def test_tampered_ciphertext_raises(self):
        blob = encrypt("original")
        tampered = blob[:-4] + "XXXX"
        with pytest.raises(Exception):
            decrypt(tampered)

    # TODO — complete this test:
    # After sending a message via POST /messages, query the database directly
    # and verify that the stored ciphertext is NOT the plain text,
    # but that decrypt(ciphertext) DOES return the original plain text.
    def test_messages_are_stored_encrypted(self, client):
        from server.models import Message
        token = register_and_login(client)
        original = "super secret message"
        client.post(
            "/messages",
            json={"content": original, "recipient": "alice"},
            headers=auth(token),
        )

        async def get_row():
            async with TestingSession() as db:
                result = await db.execute(sa_select(Message))
                return result.scalars().first()

        row = asyncio.run(get_row())
        assert row.ciphertext != original
        assert decrypt(row.ciphertext) == original


# ===========================================================================
# 3. Messaging tests
# ===========================================================================

class TestMessaging:

    def test_send_message_success(self, client):
        alice_token = register_and_login(client, "alice", "secret123")
        register_and_login(client, "bob", "secret456")

        response = client.post(
            "/messages",
            json={"content": "hello bob", "recipient": "bob"},
            headers=auth(alice_token),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "hello bob"   # returned decrypted
        assert data["sender"] == "alice"
        assert data["recipient"] == "bob"

    def test_get_messages_returns_decrypted(self, client):
        alice_token = register_and_login(client, "alice", "secret123")
        register_and_login(client, "bob", "secret456")

        client.post("/messages", json={"content": "hi bob", "recipient": "bob"}, headers=auth(alice_token))

        response = client.get("/messages", headers=auth(alice_token))
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) >= 1
        assert messages[0]["content"] == "hi bob"   # must be decrypted, not ciphertext

    # TODO — complete this test:
    # Alice sends a message to Bob. Bob sends a message to Alice.
    # Verify that GET /messages returns ONLY the messages
    # where the requesting user is sender OR recipient.
    def test_user_sees_only_their_messages(self, client):
        alice_token = register_and_login(client, "alice", "secret123")
        bob_token   = register_and_login(client, "bob",   "secret456")
        charlie_token = register_and_login(client, "charlie", "secret789")

        # alice → bob
        client.post("/messages", json={"content": "hi bob", "recipient": "bob"}, headers=auth(alice_token))
        # charlie → bob  (alice should NOT see this)
        client.post("/messages", json={"content": "hey bob from charlie", "recipient": "bob"}, headers=auth(charlie_token))

        # alice fetches her messages — should see only alice↔bob, not charlie→bob
        response = client.get("/messages", headers=auth(alice_token))
        assert response.status_code == 200
        messages = response.json()
        senders = {m["sender"] for m in messages}
        recipients = {m["recipient"] for m in messages}
        assert all("alice" in (m["sender"], m["recipient"]) for m in messages), \
            "Alice should only see messages where she is sender or recipient"
        assert not any(m["sender"] == "charlie" and m["recipient"] == "bob" for m in messages), \
            "Alice should not see charlie→bob messages"


# ===========================================================================
# 4. SSE tests
# ===========================================================================

class TestSSE:

    @pytest.mark.asyncio
    async def test_stream_connection_and_message_delivery(self, client):
        register_and_login(client, "alice", "secret123")

        alice_stream = await stream(username="alice")
        alice_task = None
        try:
            alice_task = asyncio.create_task(next_sse_payload(alice_stream, timeout_seconds=2.0))
            await asyncio.sleep(0.05)
            assert len(broadcaster._subscribers) >= 1

            await broadcaster.publish(
                BroadcastEvent(
                    id=999,
                    sender="bob",
                    recipient="alice",
                    content="hello from stream test",
                    created_at=datetime.now(timezone.utc),
                )
            )

            event = await alice_task
            assert event is not None
            assert event["sender"] == "bob"
            assert event["recipient"] == "alice"
            assert event["content"] == "hello from stream test"
        finally:
            if alice_task is not None and not alice_task.done():
                alice_task.cancel()
                try:
                    await alice_task
                except asyncio.CancelledError:
                    pass
            await alice_stream.body_iterator.aclose()

    @pytest.mark.asyncio
    async def test_realtime_delivery_for_concurrent_clients(self, client):
        alice_token = register_and_login(client, "alice", "secret123")
        bob_token = register_and_login(client, "bob", "secret456")
        charlie_token = register_and_login(client, "charlie", "secret789")

        alice_stream = await stream(username="alice")
        bob_stream = await stream(username="bob")
        charlie_stream = await stream(username="charlie")
        alice_task = None
        bob_task = None
        charlie_task = None

        try:
            alice_task = asyncio.create_task(next_sse_payload(alice_stream, timeout_seconds=2.0))
            bob_task = asyncio.create_task(next_sse_payload(bob_stream, timeout_seconds=2.0))
            charlie_task = asyncio.create_task(next_sse_payload(charlie_stream, timeout_seconds=0.4))

            await asyncio.sleep(0.05)
            assert len(broadcaster._subscribers) >= 3

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
                send_response = await ac.post(
                    "/messages",
                    json={"content": "team sync at 4", "recipient": "bob"},
                    headers=auth(alice_token),
                )
            assert send_response.status_code == 201

            alice_event = await alice_task
            bob_event = await bob_task

            assert alice_event is not None
            assert bob_event is not None
            assert alice_event["content"] == "team sync at 4"
            assert bob_event["content"] == "team sync at 4"
            assert alice_event["sender"] == "alice"
            assert bob_event["recipient"] == "bob"

            # Isolation: charlie should not receive alice→bob events.
            assert await charlie_task is None
        finally:
            for task in (alice_task, bob_task, charlie_task):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            await alice_stream.body_iterator.aclose()
            await bob_stream.body_iterator.aclose()
            await charlie_stream.body_iterator.aclose()

    def test_stream_rejects_invalid_token(self, client):
        response = client.get("/stream", headers={"Authorization": "Bearer fake-token"})
        assert response.status_code == 401

    def test_stream_rejects_expired_token(self, client):
        expired_payload = {
            "sub": "alice",
            "exp": datetime.now(timezone.utc).timestamp() - 60,
        }
        expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
        response = client.get("/stream", headers={"Authorization": f"Bearer {expired_token}"})
        assert response.status_code == 401

    def test_stream_requires_auth_header(self, client):
        response = client.get("/stream")
        assert response.status_code in (401, 403)
