"""Dependency providers for FastAPI.

These providers make route dependencies explicit and easy to override in tests.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .broadcaster import Broadcaster, broadcaster
from .models import get_db
from .repository import UserRepository, MessageRepository
from .services import (
    AuthService,
    MessagingService,
    DefaultAuthService,
    DefaultMessagingService,
)


def get_broadcaster() -> Broadcaster:
    return broadcaster


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_message_repository(db: AsyncSession = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)


def get_auth_service(users: UserRepository = Depends(get_user_repository)) -> AuthService:
    return DefaultAuthService(users)


def get_messaging_service(
    messages: MessageRepository = Depends(get_message_repository),
    app_broadcaster: Broadcaster = Depends(get_broadcaster),
) -> MessagingService:
    return DefaultMessagingService(messages, app_broadcaster)
