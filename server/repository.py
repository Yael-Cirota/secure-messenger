"""
repository.py — Data access layer (Repository Pattern).

DESIGN PATTERN: Repository
  Routes describe WHAT to do (business logic).
  Repositories handle HOW to talk to the database.

  Benefits:
    - Routes stay thin and readable — no raw SQL scattered everywhere
    - Easy to mock in tests (swap the real DB for a fake one)
    - DB query logic lives in one place, not duplicated across routes

TWO REPOSITORIES:
  UserRepository    — user lookup and creation
  MessageRepository — message creation and retrieval
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, Message


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_username(self, username: str) -> User | None:
        result = await self._db.execute(
            select(User).where(User.username == username)
        )
        return result.scalars().first()

    async def create(self, username: str, password_hash: str) -> User:
        user = User(username=username, password_hash=password_hash)
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)
        return user


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, sender: str, recipient: str, ciphertext: str) -> Message:
        msg = Message(sender=sender, recipient=recipient, ciphertext=ciphertext)
        self._db.add(msg)
        await self._db.commit()
        await self._db.refresh(msg)
        return msg

    async def get_for_user(self, username: str) -> list[Message]:
        result = await self._db.execute(
            select(Message)
            .where((Message.sender == username) | (Message.recipient == username))
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())
