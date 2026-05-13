"""Seed script for Secure Messenger.

Usage:
    python seed.py

What it does:
- Creates tables if needed
- Deletes existing users/messages (clean slate)
- Inserts test users: alice, bob, charlie
- Inserts sample encrypted messages between them

This script is idempotent and safe to run multiple times.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete

from server.auth import hash_password
from server.crypto import encrypt
from server.models import Message, SessionLocal, User, create_tables


TEST_USERS = [
    ("alice", "alice123"),
    ("bob", "bob12345"),
    ("charlie", "charlie123"),
]

TEST_MESSAGES = [
    ("alice", "bob", "hey bob, are you around?"),
    ("bob", "alice", "yes, just got online."),
    ("charlie", "alice", "alice, can we sync later today?"),
    ("alice", "charlie", "sure, let's do 4 PM."),
    ("bob", "charlie", "pushing a quick update now."),
]


async def reset_database() -> None:
    """Remove existing rows so every seed run starts from a clean state."""
    async with SessionLocal() as db:
        await db.execute(delete(Message))
        await db.execute(delete(User))
        await db.commit()


async def insert_users() -> None:
    """Insert deterministic test users with hashed passwords."""
    async with SessionLocal() as db:
        for username, password in TEST_USERS:
            user = User(
                username=username,
                password_hash=await hash_password(password),
            )
            db.add(user)
        await db.commit()


async def insert_messages() -> None:
    """Insert encrypted sample messages between test users."""
    async with SessionLocal() as db:
        for sender, recipient, plaintext in TEST_MESSAGES:
            msg = Message(
                sender=sender,
                recipient=recipient,
                ciphertext=encrypt(plaintext),
            )
            db.add(msg)
        await db.commit()


async def seed() -> None:
    await create_tables()
    await reset_database()
    await insert_users()
    await insert_messages()


def main() -> None:
    asyncio.run(seed())
    print("Seed complete.")
    print("Users:")
    for username, password in TEST_USERS:
        print(f"  - {username} / {password}")
    print("Messages inserted:", len(TEST_MESSAGES))


if __name__ == "__main__":
    main()
