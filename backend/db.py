"""Shared database access for the Campus Customs backend.

The catalogue API (main.py) and the agent's lookup tools (tools.py) both need
to read campus_customs.db. Keeping the connection factory and the small parsing
helpers here lets tools.py reuse them without importing main.py — which would
otherwise drag in the FastAPI app, the CORS setup, and the static-image mount
as import-time side effects.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent

# The database ships inside the homework data drop; allow an override so the
# backend keeps working if the file is ever relocated.
DB_CANDIDATES = [
    Path(p) for p in [os.environ.get("CAMPUS_CUSTOMS_DB", "")] if p
] + [
    REPO_ROOT / "HW 4" / "data" / "data" / "campus_customs.db",
    REPO_ROOT / "data" / "campus_customs.db",
    REPO_ROOT / "backend" / "data" / "campus_customs.db",
]


def _resolve_db() -> Path:
    for candidate in DB_CANDIDATES:
        if candidate.is_file():
            return candidate
    searched = "\n  ".join(str(c) for c in DB_CANDIDATES)
    raise RuntimeError(
        f"campus_customs.db not found. Looked in:\n  {searched}\n"
        "Set CAMPUS_CUSTOMS_DB to the database path to override."
    )


DB_PATH = _resolve_db()
# Images live in a products/ directory next to the database, and
# catalogue.image_file_path is relative to that directory's parent.
MEDIA_ROOT = DB_PATH.parent

# Every product carries this exact six-size run; used to order size results.
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite leaves foreign keys off by default; the schema declares
    # inventory.product_id -> catalogue.product_id, so turn enforcement on.
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def parse_json_array(raw: str | None) -> list[str]:
    """colors and search_tags are JSON arrays stored in TEXT columns."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def normalize_category(garment_type: str) -> str:
    """Collapse the 22 raw garment_type spellings into stable categories.

    The column is free text: 'short-sleeve T-shirt', 'short-sleeve t-shirt'
    and 't-shirt' all exist, as do 'pullover hoodie', 'hoodie' and
    'hooded sweatshirt'. Filtering on the raw value silently drops rows.
    """
    value = garment_type.lower()
    if "hood" in value:
        return "hoodie"
    if "quarter-zip" in value or "1/4" in value:
        return "quarter-zip"
    if "jacket" in value or "fleece" in value:
        return "jacket"
    if "crewneck" in value or "crew-neck" in value or "mockneck" in value:
        return "crewneck"
    if "long-sleeve" in value or "performance" in value:
        return "long-sleeve"
    if "t-shirt" in value or "tee" in value:
        return "t-shirt"
    return "other"


def size_key(size: str) -> tuple[int, str]:
    """Sort key that orders sizes XS→XXL, with unknown sizes last."""
    upper = size.upper()
    return (SIZE_ORDER.index(upper) if upper in SIZE_ORDER else len(SIZE_ORDER), upper)
