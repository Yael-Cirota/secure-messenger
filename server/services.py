"""Application service layer.

Defines explicit service interfaces and implementations so route handlers
depend on abstractions rather than direct repository orchestration.
"""
from __future__ import annotations

from typing import Protocol

from fastapi import HTTPException, status

from .auth import hash_password, verify_password, create_token
from .broadcaster import Broadcaster
from .crypto import encrypt, decrypt
from .repository import UserRepository, MessageRepository
from .schemas import MessageResponse, TokenResponse, BroadcastEvent


class AuthService(Protocol):
    async def register(self, username: str, password: str) -> None:
        ...

    async def login(self, username: str, password: str) -> TokenResponse:
        ...


class MessagingService(Protocol):
    async def send_message(self, sender: str, recipient: str, content: str) -> MessageResponse:
        ...

    async def list_messages(self, username: str) -> list[MessageResponse]:
        ...


class DefaultAuthService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def register(self, username: str, password: str) -> None:
        if await self._users.get_by_username(username):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="username already taken")
        await self._users.create(username, await hash_password(password))

    async def login(self, username: str, password: str) -> TokenResponse:
        user = await self._users.get_by_username(username)
        if not user or not await verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return TokenResponse(access_token=create_token(user.username))


class DefaultMessagingService:
    def __init__(self, messages: MessageRepository, broadcaster: Broadcaster) -> None:
        self._messages = messages
        self._broadcaster = broadcaster

    async def send_message(self, sender: str, recipient: str, content: str) -> MessageResponse:
        msg = await self._messages.create(
            sender=sender,
            recipient=recipient,
            ciphertext=encrypt(content),
        )
        response = MessageResponse(
            id=msg.id,
            sender=msg.sender,
            recipient=msg.recipient,
            content=content,
            created_at=msg.created_at,
        )
        await self._broadcaster.publish(
            BroadcastEvent(
                id=msg.id,
                sender=msg.sender,
                recipient=msg.recipient,
                content=content,
                created_at=msg.created_at,
            )
        )
        return response

    async def list_messages(self, username: str) -> list[MessageResponse]:
        rows = await self._messages.get_for_user(username)
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
