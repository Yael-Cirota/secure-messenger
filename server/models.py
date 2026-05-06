"""
models.py — Database tables as Python classes (SQLAlchemy ORM).

╔══════════════════════════════════════════════╗
║  YOUR TASK: fill in the two table classes.   ║
╚══════════════════════════════════════════════╝

WHAT IS AN ORM?
  Instead of writing raw SQL like:
      CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, ...)
  you write a Python class and SQLAlchemy creates the table for you.
  Reading and writing rows becomes reading and writing Python objects.

WHAT IS SQLITE?
  A database that lives in a single file (messenger.db).
  No server to install, no configuration — just a file.
  Perfect for development and learning.

THE TWO TABLES YOU NEED:

  User — one row per registered user
    id            : integer, primary key
    username      : string, must be unique (no two users with the same name)
    password_hash : string  (NEVER store the plain password — only the hash)
    created_at    : datetime, set automatically when the row is created

  Message — one row per sent message
    id         : integer, primary key
    sender     : string  (the username of who sent it)
    recipient  : string  (the username of who should receive it)
    ciphertext : text    (the AES-encrypted content — NEVER store plain text)
    created_at : datetime, set automatically when the row is created

USEFUL REFERENCE:
  Mapped column types: String, Text, DateTime
  mapped_column options: primary_key=True, index=True, unique=True, nullable=False
  Auto-set timestamp: default=lambda: datetime.now(timezone.utc)
"""

from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


DATABASE_URL = "sqlite+aiosqlite:///./messenger.db"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


async def get_db():
    """
    FastAPI dependency — opens a DB session for one request, closes it after.
    """
    async with SessionLocal() as db:
        yield db


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# TODO 1 — Define the User table
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id:            Mapped[int]      = mapped_column(primary_key=True)
    username:      Mapped[str]      = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str]      = mapped_column(String(255), nullable=False)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# TODO 2 — Define the Message table
# ---------------------------------------------------------------------------
class Message(Base):
    __tablename__ = "messages"

    id:         Mapped[int]      = mapped_column(primary_key=True)
    sender:     Mapped[str]      = mapped_column(String(50), nullable=False, index=True)
    recipient:  Mapped[str]      = mapped_column(String(50), nullable=False, index=True)
    ciphertext: Mapped[str]      = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


async def create_tables():
    """Creates all tables in the database if they don't exist yet."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
