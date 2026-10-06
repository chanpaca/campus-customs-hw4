"""Chat history persistence for logged-in customers (Problem 8).

Stores each turn of a logged-in shopper's conversation in a ``chat_history``
table so the agent can remember them across sessions. Guests are never written
here — their history lives only in the frontend's React state for the session.

(The database also ships a seeded ``chat_messages`` table from the original data
drop; it is left untouched. This feature uses its own ``chat_history`` table, as
the assignment names it, and adds a ``page_context`` column the old table lacks.)
"""

from __future__ import annotations

import json
from typing import Any

from backend.db import get_db
from backend.models import ChatTurn

# How many of a user's most recent turns to replay as agent context. Keeps the
# prompt bounded while still giving the agent cross-session memory.
HISTORY_WINDOW = 20

# How many past turns to return for display when a user reopens the chat. Larger
# than HISTORY_WINDOW (which bounds agent context) so the shopper can scroll back
# further than the agent reasons over.
DISPLAY_WINDOW = 50


def ensure_chat_history_table() -> None:
    """Create the chat_history table if it does not exist. Safe to call at startup."""
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                role          TEXT NOT NULL,
                content       TEXT NOT NULL,
                products_json TEXT,
                page_context  TEXT,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_history_user ON chat_history(user_id, id)"
        )
        conn.commit()


def save_message(
    user_id: int,
    role: str,
    content: str,
    products: list[Any] | None = None,
    page_context: Any | None = None,
) -> None:
    """Persist one turn for a logged-in user.

    ``products`` are the hydrated cards shown with an assistant reply (stored as
    JSON so a transcript can be re-rendered); ``page_context`` is the product the
    shopper was viewing when they sent the message.
    """
    products_json = (
        json.dumps([p.model_dump() if hasattr(p, "model_dump") else p for p in products])
        if products
        else None
    )
    page_json = (
        json.dumps(page_context.model_dump() if hasattr(page_context, "model_dump") else page_context)
        if page_context
        else None
    )
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO chat_history (user_id, role, content, products_json, page_context)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, role, content, products_json, page_json),
        )
        conn.commit()


def load_history(user_id: int, limit: int = HISTORY_WINDOW) -> list[ChatTurn]:
    """Return a user's most recent turns, oldest-first, for agent replay."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM chat_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    # Fetched newest-first for the LIMIT; reverse to oldest-first for replay.
    return [ChatTurn(role=row["role"], content=row["content"]) for row in reversed(rows)]


def load_messages_for_display(user_id: int, limit: int = DISPLAY_WINDOW) -> list[dict[str, Any]]:
    """Return a user's recent turns (oldest-first) with their stored product cards.

    Used by GET /api/chat/history to repopulate the chat window on login. Each
    item is {role, content, products} where products is the list of card dicts
    saved with an assistant reply (empty for user turns).
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT role, content, products_json FROM chat_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    messages: list[dict[str, Any]] = []
    for row in reversed(rows):
        products = json.loads(row["products_json"]) if row["products_json"] else []
        messages.append({"role": row["role"], "content": row["content"], "products": products})
    return messages
