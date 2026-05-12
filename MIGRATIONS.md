# Database Migrations with Alembic

## The Problem

Look at `server/models.py` — on startup we call:

```python
Base.metadata.create_all(bind=engine)
```

This creates tables **only if they don't exist**. It will **never**:
- Add a new column to an existing table
- Change a column type
- Remove a column

So if you add `email` to the `User` model and restart the server — nothing happens.
The only fix without migrations is to **delete `messenger.db`** and lose all data.

Migrations solve this: they evolve the schema without destroying data.

---

## Setup (One Time)

### 1. Install Alembic

```bash
pip install alembic
```

(Already added to `requirements.txt`)

### 2. Initialize

```bash
cd /path/to/secure-messenger-full
alembic init migrations
```

This creates:
```
migrations/
├── env.py          ← configuration (edit this)
├── script.py.mako  ← template for new migrations
└── versions/       ← migration scripts live here
alembic.ini         ← database URL goes here
```

### 3. Configure `alembic.ini`

Find this line:
```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```

Replace with:
```ini
sqlalchemy.url = sqlite:///./messenger.db
```

### 4. Configure `migrations/env.py`

Find `target_metadata = None` and replace with:

```python
import sys
from pathlib import Path

# Add project root to path so we can import our models
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.models import Base

target_metadata = Base.metadata
```

This tells Alembic what your models look like, so it can detect changes.

---

## The Workflow

Every time you change a model, you do two steps:

### Step 1: Generate a migration

```bash
alembic revision --autogenerate -m "describe_the_change"
```

Alembic compares your current models to the actual database, and generates a Python file
with the difference.

### Step 2: Apply the migration

```bash
alembic upgrade head
```

This runs the migration and updates the database.

---

## Exercise: Add `email` to User

### 1. Modify the model

In `server/models.py`, add the `email` column:

```python
class User(Base):
    __tablename__ = "users"

    id:            Mapped[int] = mapped_column(primary_key=True, index=True)
    username:      Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    email:         Mapped[str | None] = mapped_column(String(100), nullable=True)  # ← NEW
    created_at:    Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
```

Note: `nullable=True` is important — existing rows don't have this value.

### 2. Generate the migration

```bash
alembic revision --autogenerate -m "add_email_to_users"
```

Check the generated file in `migrations/versions/`. It should look like:

```python
"""add_email_to_users"""

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('users', sa.Column('email', sa.String(100), nullable=True))

def downgrade():
    op.drop_column('users', 'email')
```

### 3. Apply it

```bash
alembic upgrade head
```

### 4. Verify

```bash
sqlite3 messenger.db ".schema users"
```

You should see the `email` column in the output.

---

## Useful Commands

| Command | What it does |
|---------|-------------|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade -1` | Undo the last migration |
| `alembic history` | Show all migrations |
| `alembic current` | Show which migration the DB is at |
| `alembic revision --autogenerate -m "msg"` | Generate migration from model changes |

---

## SQLite Limitation

SQLite does not support all `ALTER TABLE` operations. Specifically:
- No `DROP COLUMN` (before SQLite 3.35.0)
- No `ALTER COLUMN` (change type, add constraints)

Alembic handles this with **batch mode** — it copies the table, recreates it with changes,
and copies data back:

```python
def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('username', type_=sa.String(100))
```

When you use `--autogenerate`, Alembic detects SQLite and uses batch mode automatically
if you add this to `migrations/env.py`:

```python
# In the run_migrations_online() function, change context.configure():
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    render_as_batch=True,  # ← ADD THIS for SQLite compatibility
)
```

---

## Why This Matters in Production

| Without migrations | With migrations |
|---|---|
| Delete DB and lose all data | Schema evolves, data preserved |
| No history of schema changes | Full version history in git |
| "Works on my machine" issues | Everyone runs the same migrations |
| Impossible to roll back | `alembic downgrade -1` undoes mistakes |

---

## Relation to `create_all()`

Once you adopt Alembic, you can remove `create_tables()` from your startup.
Alembic's `alembic upgrade head` replaces it — it both creates tables from scratch
(on a fresh DB) and applies incremental changes (on an existing DB).

However, for this course, keeping both is fine:
- `create_all()` for quick startup during development
- Alembic for when you need to modify existing tables
