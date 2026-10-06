"""Campus Customs backend.

Serves the product catalogue out of campus_customs.db and the product images
off disk, for the React storefront in ../frontend.

Run with:  uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, field_validator

from backend import audit, auth, history
from backend.models import (
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
    MatchedProduct,
    ProductRef,
)

# --------------------------------------------------------------------------
# Locating the database and the product images
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables from the repo-root .env as early as possible, so
# PORTKEY_API_KEY (and friends) are present before the agent is ever built.
# override=False keeps any value already set in the real environment.
load_dotenv(REPO_ROOT / ".env", override=False)

# How long to wait for the chatbot agent before giving up, in seconds.
CHAT_TIMEOUT_SECONDS = float(os.environ.get("CHAT_TIMEOUT_SECONDS", "30"))

# Database access and the shared parsing helpers live in backend/db.py so the
# agent's lookup tools can reuse them without importing this module.
from backend.db import (  # noqa: E402
    DB_PATH,
    MEDIA_ROOT,
    SIZE_ORDER,
    get_db,
    normalize_category as _normalize_category,
    parse_json_array as _parse_json_array,
    size_key as _size_key,
)


# --------------------------------------------------------------------------
# Serialization helpers
# --------------------------------------------------------------------------


def _image_url(image_file_path: str) -> str:
    return "/media/" + image_file_path.replace("\\", "/").lstrip("/")


def _serialize_product(row: sqlite3.Row, inventory: list[sqlite3.Row]) -> dict[str, Any]:
    sizes = sorted(
        ({"size": r["size"], "quantity": r["quantity"]} for r in inventory),
        key=lambda s: _size_key(s["size"]),
    )
    total_stock = sum(s["quantity"] for s in sizes)
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "garment_type": row["garment_type"],
        "category": _normalize_category(row["garment_type"]),
        "description": row["description"],
        "colors": _parse_json_array(row["colors"]),
        "search_tags": _parse_json_array(row["search_tags"]),
        "image_file_path": row["image_file_path"],
        "image_url": _image_url(row["image_file_path"]),
        "price": row["price"],
        "sizes": sizes,
        "available_sizes": [s["size"] for s in sizes if s["quantity"] > 0],
        "total_stock": total_stock,
        "in_stock": total_stock > 0,
    }


def _load_inventory(conn: sqlite3.Connection, product_ids: list[str]) -> dict[str, list[sqlite3.Row]]:
    """One query for all requested products, to avoid an N+1 per card."""
    if not product_ids:
        return {}
    placeholders = ",".join("?" * len(product_ids))
    rows = conn.execute(
        f"SELECT product_id, size, quantity FROM inventory WHERE product_id IN ({placeholders})",
        product_ids,
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {pid: [] for pid in product_ids}
    for row in rows:
        grouped[row["product_id"]].append(row)
    return grouped


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

app = FastAPI(
    title="Campus Customs API",
    description="Product catalogue and imagery for the Campus Customs storefront.",
    version="0.1.0",
)

# Applies to every response, including the /media mount below — Starlette
# middleware wraps the whole app, not just the API routes. The Vite dev server
# proxies /media, so images are same-origin in development; these headers are
# what let an <img> load straight from http://localhost:8001 as well.
app.add_middleware(
    CORSMiddleware,
    # Any localhost port, so a shifted Vite port still works.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Set explicitly rather than relying on the Starlette default, which varies
    # by version. Range and cache headers must be exposed for images.
    expose_headers=[
        "Content-Length",
        "Content-Range",
        "Content-Type",
        "Accept-Ranges",
        "ETag",
        "Last-Modified",
    ],
    max_age=600,
)

# Product imagery, served straight off disk at /media/products/<slug>.jpg
if not (MEDIA_ROOT / "products").is_dir():
    raise RuntimeError(
        f"Product image directory not found at {MEDIA_ROOT / 'products'}. "
        "Images would 404 and render as broken links."
    )

app.mount("/media", StaticFiles(directory=MEDIA_ROOT), name="media")

# Create the chat_history table (Problem 8) if it does not exist yet.
history.ensure_chat_history_table()


# --------------------------------------------------------------------------
# Authentication: request/response models
# --------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str

    @field_validator("first_name", "last_name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name fields cannot be blank.")
        return cleaned

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if len(value) < auth.MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {auth.MIN_PASSWORD_LENGTH} characters.")
        if len(value.encode("utf-8")) > auth.MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {auth.MAX_PASSWORD_BYTES} bytes.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PublicUser(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    name: str
    email: EmailStr


class AuthResponse(BaseModel):
    token: str
    user: PublicUser


def _public_user(row: sqlite3.Row) -> PublicUser:
    return PublicUser(
        id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        name=row["name"],
        email=row["email"],
    )


def current_user(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    """Resolve the Bearer token in the Authorization header to a user row.

    Raises 401 if the header is missing, malformed, expired, or points at a
    user that no longer exists. Used as a dependency on protected routes.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    token = authorization[len("bearer ") :].strip()
    user_id = auth.verify_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return row


def optional_current_user(authorization: str | None = Header(default=None)) -> sqlite3.Row | None:
    """Like current_user, but returns None instead of 401 for guests.

    Used by /api/chat so guests can chat without signing in, while logged-in
    shoppers are identified (for memory + personalization).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[len("bearer ") :].strip()
    user_id = auth.verify_token(token)
    if user_id is None:
        return None
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest) -> AuthResponse:
    """Create an account with a bcrypt-hashed password and return a session token."""
    email = payload.email.strip().lower()
    full_name = f"{payload.first_name} {payload.last_name}".strip()
    password_hash = auth.hash_password(payload.password)

    with get_db() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            # 409 rather than a generic 400 so the form can say "already registered".
            raise HTTPException(status_code=409, detail="An account with that email already exists.")
        cursor = conn.execute(
            """
            INSERT INTO users (name, email, password_hash, first_name, last_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (full_name, email, password_hash, payload.first_name, payload.last_name),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return AuthResponse(token=auth.issue_token(row["id"]), user=_public_user(row))


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    """Verify credentials and return a session token.

    The error is deliberately identical whether the email is unknown or the
    password is wrong, so the endpoint does not reveal which addresses have
    accounts.
    """
    email = payload.email.strip().lower()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if row is None or not auth.verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Incorrect email or password.")

        # Transparently upgrade a legacy pbkdf2 hash to bcrypt now that we have
        # the plaintext in hand and know it is correct.
        if auth.needs_rehash(row["password_hash"]):
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (auth.hash_password(payload.password), row["id"]),
            )
            conn.commit()

    return AuthResponse(token=auth.issue_token(row["id"]), user=_public_user(row))


@app.get("/api/auth/me", response_model=PublicUser)
def read_me(user: sqlite3.Row = Depends(current_user)) -> PublicUser:
    """Return the current user, for the frontend to restore a session on reload."""
    return _public_user(user)


# --------------------------------------------------------------------------
# Chatbot
# --------------------------------------------------------------------------


def _hydrate_products(refs: list[ProductRef]) -> list[MatchedProduct]:
    """Turn the agent's product picks into authoritative display cards.

    The agent only names products (id + reason). We look each one up in the
    catalogue and fill name/price/image/stock from the database, so the card is
    trustworthy and identical to the Problem 3 catalogue cards. Any product_id
    the agent invented that is not in the catalogue is silently dropped — the UI
    never shows a hallucinated product. Order and de-duplication follow the
    agent's list.
    """
    if not refs:
        return []

    seen: set[str] = set()
    ordered_ids: list[str] = []
    reasons: dict[str, str | None] = {}
    for ref in refs:
        if ref.product_id in seen:
            continue
        seen.add(ref.product_id)
        ordered_ids.append(ref.product_id)
        reasons[ref.product_id] = ref.reason

    placeholders = ",".join("?" * len(ordered_ids))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM catalogue WHERE product_id IN ({placeholders})", ordered_ids
        ).fetchall()
        by_id = {row["product_id"]: row for row in rows}
        inventory = _load_inventory(conn, list(by_id.keys()))

    cards: list[MatchedProduct] = []
    for product_id in ordered_ids:
        row = by_id.get(product_id)
        if row is None:
            continue  # agent named a product that does not exist — drop it
        total_stock = sum(r["quantity"] for r in inventory.get(product_id, []))
        cards.append(
            MatchedProduct(
                product_id=row["product_id"],
                name=row["name"],
                price=row["price"],
                image_url=_image_url(row["image_file_path"]),
                garment_type=row["garment_type"],
                in_stock=total_stock > 0,
                reason=reasons.get(product_id),
            )
        )
    return cards


def _to_message_history(turns: list[Any]) -> list[Any]:
    """Convert our ChatTurn list into PydanticAI message objects for replay."""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    history: list[Any] = []
    for turn in turns:
        if turn.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=turn.content)]))
    return history


def _resolve_page_title(product_id: str | None, title: str | None) -> str | None:
    """Fill in a page product's title from the DB if the frontend didn't send one."""
    if not product_id or title:
        return title
    with get_db() as conn:
        row = conn.execute("SELECT name FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
    return row["name"] if row else None


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: sqlite3.Row | None = Depends(optional_current_user),
) -> ChatResponse:
    """Send the shopper's message to the PydanticAI agent and return its reply.

    Logged-in shoppers are identified to the agent and their turns are persisted
    to chat_history (so the agent remembers them across sessions); guests chat
    without persistence. The product page the shopper is on is passed through as
    context so the agent can resolve "this"/"it". The agent is imported lazily so
    a missing PORTKEY_API_KEY surfaces here as a clean 503.
    """
    session = f"user:{user['id']}" if user is not None else "guest"
    user_id = user["id"] if user is not None else None
    page = payload.page_context

    try:
        from backend.agent import ChatDeps, get_agent

        agent = get_agent()
    except RuntimeError as exc:
        audit.log_interaction(
            session=session, user_id=user_id, message=payload.message, page_context=page,
            tools=[], status="error", finish_reason="agent_unconfigured", error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    page_product_id = page.product_id if page else None
    page_title = _resolve_page_title(page_product_id, page.title if page else None)

    deps = ChatDeps(
        user_id=user_id,
        first_name=user["first_name"] if user else None,
        email=user["email"] if user else None,
        page_product_id=page_product_id,
        page_product_title=page_title,
    )

    # Logged-in: replay the user's stored history (cross-session memory).
    # Guest: replay only the session history the frontend sent.
    if user is not None:
        prior_turns = history.load_history(user["id"])
    else:
        prior_turns = payload.history

    try:
        result = await asyncio.wait_for(
            agent.run(
                payload.message,
                message_history=_to_message_history(prior_turns),
                deps=deps,
            ),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        # The model took too long — tell the client to try again rather than
        # leaving the request hanging. 504 = upstream (the LLM) timed out.
        audit.log_interaction(
            session=session, user_id=user_id, message=payload.message, page_context=page,
            tools=[], status="error", finish_reason="timeout", error=str(exc),
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Handsome Dan took too long to respond (over {CHAT_TIMEOUT_SECONDS:.0f}s). "
                "Please try again."
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001 — surface any model/gateway error as 502
        audit.log_interaction(
            session=session, user_id=user_id, message=payload.message, page_context=page,
            tools=[], status="error", finish_reason="model_error", error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"The assistant is unavailable: {exc}") from exc

    reply = result.output
    cards = _hydrate_products(reply.products)

    # Append this interaction to the audit trail (tools called, status, etc.).
    audit.log_interaction(
        session=session, user_id=user_id, message=payload.message, page_context=page,
        tools=audit.summarize_tools(result), status="success", finish_reason="completed",
        reply_chars=len(reply.reply), products_returned=len(cards),
    )

    # Persist both turns for logged-in users only.
    if user is not None:
        history.save_message(user["id"], "user", payload.message, page_context=page)
        history.save_message(user["id"], "assistant", reply.reply, products=cards)

    return ChatResponse(reply=reply.reply, products=cards)


@app.get("/api/chat/history", response_model=ChatHistoryResponse)
def chat_history(user: sqlite3.Row = Depends(current_user)) -> ChatHistoryResponse:
    """Return the logged-in user's past conversation, to repopulate the chat window.

    Requires authentication (401 for guests, who have no stored history). Assistant
    turns carry the product cards that were shown, so the window re-renders exactly.
    """
    rows = history.load_messages_for_display(user["id"])
    messages = [
        ChatHistoryMessage(
            role=row["role"],
            content=row["content"],
            products=[MatchedProduct(**card) for card in row["products"]],
        )
        for row in rows
    ]
    return ChatHistoryResponse(messages=messages)


@app.get("/api/health")
def health() -> dict[str, Any]:
    with get_db() as conn:
        product_count = conn.execute("SELECT COUNT(*) FROM catalogue").fetchone()[0]
    return {
        "status": "ok",
        "database": str(DB_PATH),
        "media_root": str(MEDIA_ROOT),
        "products": product_count,
    }


@app.get("/api/products")
def list_products(
    q: str | None = Query(None, description="Free-text search over name, description and tags"),
    category: str | None = Query(None, description="Normalized category, e.g. hoodie or t-shirt"),
    color: str | None = Query(None, description="Match a single color, e.g. navy"),
    max_price: float | None = Query(None, ge=0),
    in_stock_only: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """The catalogue, with per-size inventory attached to every product."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM catalogue ORDER BY name").fetchall()
        inventory = _load_inventory(conn, [r["product_id"] for r in rows])

    products = [_serialize_product(row, inventory.get(row["product_id"], [])) for row in rows]

    if category:
        wanted = category.strip().lower()
        products = [p for p in products if p["category"] == wanted]

    if color:
        wanted = color.strip().lower()
        products = [p for p in products if any(wanted in c.lower() for c in p["colors"])]

    if max_price is not None:
        products = [p for p in products if p["price"] <= max_price]

    if in_stock_only:
        products = [p for p in products if p["in_stock"]]

    if q:
        # Match every whitespace-separated term against the product's text,
        # so "navy hoodie" narrows rather than widens the result set.
        terms = [t for t in re.split(r"\s+", q.strip().lower()) if t]

        def haystack(p: dict[str, Any]) -> str:
            return " ".join(
                [p["name"], p["description"], p["garment_type"], *p["colors"], *p["search_tags"]]
            ).lower()

        products = [p for p in products if all(t in haystack(p) for t in terms)]

    total = len(products)
    return {
        "total": total,
        "count": len(products[offset : offset + limit]),
        "offset": offset,
        "limit": limit,
        "products": products[offset : offset + limit],
    }


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    """A single product with its full size run, for the detail page."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM catalogue WHERE product_id = ?", (product_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"No product with id '{product_id}'")
        inventory = conn.execute(
            "SELECT product_id, size, quantity FROM inventory WHERE product_id = ?",
            (product_id,),
        ).fetchall()
    return _serialize_product(row, inventory)


@app.get("/api/categories")
def list_categories() -> dict[str, Any]:
    """Normalized categories with product counts, for the Products page filters."""
    with get_db() as conn:
        rows = conn.execute("SELECT garment_type FROM catalogue").fetchall()

    counts: dict[str, int] = {}
    for row in rows:
        key = _normalize_category(row["garment_type"])
        counts[key] = counts.get(key, 0) + 1

    return {
        "categories": [
            {"category": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
    }
