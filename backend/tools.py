"""Database lookup tools for the Campus Customs agent (Problem 6).

These are registered on the PydanticAI agent (see backend/agent.py) so the LLM
can read real catalogue and inventory data instead of guessing. Every tool
returns a structured model with an explicit ``found`` flag, so the agent is
never put in a position where it has to invent a price or a stock count.

Both tools read the same SQLite database the catalogue API uses, through the
shared helpers in backend/db.py.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import string

from backend.db import SIZE_ORDER, get_db, normalize_category, parse_json_array, size_key
from backend.models import (
    InventoryResult,
    ProductDetails,
    ProductMatch,
    ProductSearchResults,
    SizeGuidance,
    SizeStock,
)

# Number of close-match names to offer when a lookup is ambiguous or misses.
_MAX_SUGGESTIONS = 5

# Extra search terms per normalized category, so a partial query like "tees" or
# "hoodies" matches every variant — including ones whose name says "Hood" rather
# than "Hoodie". Added into each product's searchable text.
_CATEGORY_SYNONYMS = {
    "hoodie": ["hoodie", "hoodies", "hooded", "hoody"],
    "crewneck": ["crewneck", "crewnecks", "crew neck"],
    # Note: "tshirt"/"tshirts" (no hyphen) are deliberately omitted — "tshirt"
    # is a substring of "sweatshirt", so it would wrongly match every crewneck
    # and hoodie. The hyphenated "t-shirt" does not collide; typos like "tshirt"
    # or "tshit" are caught by the fuzzy pass and corrected to "t-shirt".
    "t-shirt": ["t-shirt", "t-shirts", "tee", "tees"],
    "quarter-zip": ["quarter-zip", "quarter-zips", "quarter zip", "quarterzip"],
    "jacket": ["jacket", "jackets", "fleece"],
    "long-sleeve": ["long-sleeve", "long sleeve", "longsleeve"],
}

# Punctuation to trim from the ends of query words, keeping internal - and /.
_EDGE_PUNCT = "".join(c for c in string.punctuation if c not in "-/")


def _inventory_rows(conn: sqlite3.Connection, product_id: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT size, quantity FROM inventory WHERE product_id = ?",
        (product_id,),
    ).fetchall()
    return sorted(rows, key=lambda r: size_key(r["size"]))


def _resolve_product(conn: sqlite3.Connection, query: str) -> sqlite3.Row | None:
    """Find the single best catalogue row for a free-text query.

    Resolution order, most precise first:
      1. exact product_id (slug) match
      2. exact name match (case-insensitive)
      3. name contains the query (case-insensitive)
      4. the query appears in name, description, or search_tags
    Returns None if nothing matches at all.
    """
    q = query.strip()
    if not q:
        return None
    lowered = q.lower()

    # 1. exact slug
    row = conn.execute("SELECT * FROM catalogue WHERE product_id = ?", (q,)).fetchone()
    if row:
        return row

    # 2. exact name
    row = conn.execute(
        "SELECT * FROM catalogue WHERE LOWER(name) = ?", (lowered,)
    ).fetchone()
    if row:
        return row

    # 3. name substring — prefer the shortest name, which is the tightest match
    rows = conn.execute(
        "SELECT * FROM catalogue WHERE LOWER(name) LIKE ? ORDER BY LENGTH(name) ASC",
        (f"%{lowered}%",),
    ).fetchall()
    if rows:
        return rows[0]

    # 4. description / search_tags substring
    rows = conn.execute(
        """
        SELECT * FROM catalogue
        WHERE LOWER(description) LIKE ? OR LOWER(search_tags) LIKE ?
        ORDER BY LENGTH(name) ASC
        """,
        (f"%{lowered}%", f"%{lowered}%"),
    ).fetchall()
    if rows:
        return rows[0]

    # 5. typo-tolerant fallback: _find_matches corrects misspellings, so
    #    get_product_details / check_inventory also survive a shopper's typo.
    fuzzy = _find_matches(conn, q)
    return fuzzy[0] if fuzzy else None


def _suggest(conn: sqlite3.Connection, query: str) -> list[str]:
    """Offer a few product names that share any word with the query."""
    words = [w for w in query.lower().split() if len(w) > 2]
    if not words:
        return [r["name"] for r in conn.execute(
            "SELECT name FROM catalogue ORDER BY name LIMIT ?", (_MAX_SUGGESTIONS,)
        ).fetchall()]
    clause = " OR ".join("LOWER(name) LIKE ?" for _ in words)
    params = [f"%{w}%" for w in words]
    rows = conn.execute(
        f"SELECT DISTINCT name FROM catalogue WHERE {clause} ORDER BY LENGTH(name) ASC LIMIT ?",
        (*params, _MAX_SUGGESTIONS),
    ).fetchall()
    return [r["name"] for r in rows]


def _query_words(query: str) -> list[str]:
    """Lowercase the query and split into trimmed words, keeping hyphens/slashes.

    Single-character tokens are dropped: they carry no search signal and would
    otherwise match every product (e.g. a bare "s" or "t").
    """
    words = [w.strip(_EDGE_PUNCT) for w in query.lower().split()]
    return [w for w in words if len(w) >= 2]


def _searchable_text(row: sqlite3.Row) -> str:
    """All text a product can be matched against, lowercased.

    Includes the normalized category label and its synonyms, so a query like
    "hoodie" matches every hoodie variant even when the name says "Hood".
    """
    category = normalize_category(row["garment_type"])
    parts = [row["name"], row["garment_type"], category, row["description"]]
    parts += parse_json_array(row["colors"])
    parts += parse_json_array(row["search_tags"])
    parts += _CATEGORY_SYNONYMS.get(category, [])
    return " ".join(parts).lower()


def _word_in(haystack: str, word: str) -> bool:
    """True if `word` begins a word in `haystack` (boundary-anchored prefix match).

    Prefix-at-a-boundary, not raw substring: "hood" matches "hooded" and
    "hoodie", but "tshirt" does NOT match inside "sweatshirt" and "shirt" does
    not match "sweatshirt" — avoiding the substring collisions that would pull
    unrelated garments into a result.
    """
    return re.search(r"\b" + re.escape(word), haystack) is not None


def _all_words_match(haystack: str, words: list[str]) -> bool:
    """Every query word (or its singular form) must begin a word in the text."""
    for word in words:
        singular = word.rstrip("s")
        if _word_in(haystack, word) or (len(singular) >= 2 and _word_in(haystack, singular)):
            continue
        return False
    return True


# Minimum similarity for a typo to be corrected to a real catalogue word.
# High enough that "navy" is not "corrected" to something else, low enough that
# "hoodei" -> "hoodie" and "crewnck" -> "crewneck" are caught.
_FUZZY_CUTOFF = 0.75


# Bare tokens kept OUT of the fuzzy vocabulary because they are substrings of a
# garment word and would cause a correction to over-match. "shirt" ⊂ "sweatshirt",
# so correcting a typo to "shirt" would wrongly pull in every crewneck/hoodie;
# the hyphenated "t-shirt" (also in the vocab) is the right target instead.
_VOCAB_DENY = {"shirt"}


def _vocabulary(rows: list[sqlite3.Row]) -> list[str]:
    """Build the set of real words a typo can be corrected toward.

    Drawn from product names, garment types, tags, and the category synonyms —
    i.e. everything a shopper might be trying to type.
    """
    vocab: set[str] = set()
    for row in rows:
        text = " ".join(
            [row["name"], row["garment_type"], *parse_json_array(row["search_tags"])]
        ).lower()
        vocab.update(w for w in re.split(r"[^a-z0-9]+", text) if len(w) >= 3)
    for synonyms in _CATEGORY_SYNONYMS.values():
        vocab.update(s for s in synonyms if len(s) >= 3)
    return list(vocab - _VOCAB_DENY)


def _fuzzy_correct(words: list[str], vocab: list[str]) -> tuple[list[str], bool]:
    """Correct each query word to its nearest catalogue word, for typo tolerance.

    A word already in the vocabulary is returned unchanged (it is its own closest
    match). A misspelling is swapped for the closest real word above the cutoff;
    a word with no close match is left as-is. Returns (corrected_words, changed?).
    """
    corrected: list[str] = []
    changed = False
    for word in words:
        if len(word) < 3:
            corrected.append(word)
            continue
        close = difflib.get_close_matches(word, vocab, n=1, cutoff=_FUZZY_CUTOFF)
        if close and close[0] != word:
            corrected.append(close[0])
            changed = True
        else:
            corrected.append(word)
    return corrected, changed


def _find_matches(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    """Every catalogue row matching a case-insensitive partial query, by name.

    Falls back to typo-tolerant (fuzzy) matching: if the query as typed matches
    nothing, each word is corrected to the nearest real catalogue word and the
    search is retried, so "hoodei" still finds the hoodies.
    """
    words = _query_words(query)
    if not words:
        return []
    rows = conn.execute("SELECT * FROM catalogue ORDER BY name").fetchall()
    matches = [row for row in rows if _all_words_match(_searchable_text(row), words)]
    if matches:
        return matches

    corrected, changed = _fuzzy_correct(words, _vocabulary(rows))
    if changed:
        matches = [row for row in rows if _all_words_match(_searchable_text(row), corrected)]
    return matches


def search_products(query: str) -> ProductSearchResults:
    """Find every product matching a case-insensitive, partial query.

    Use this for browse-style questions — "what hoodies do you have?",
    "navy crewnecks", "anything for The Game". A category word like "hoodie",
    "tee", or "quarter-zip" returns ALL variants in that category, not just one.
    Each result carries an explicit in-stock / out-of-stock status. For the
    description and price of a single specific product, use get_product_details.
    """
    words = _query_words(query)
    if not words:
        return ProductSearchResults(
            query=query, count=0, message="Please provide something to search for."
        )

    category = normalize_category(query)
    with get_db() as conn:
        matches: list[ProductMatch] = []
        for row in _find_matches(conn, query):
            inventory = _inventory_rows(conn, row["product_id"])
            matches.append(
                ProductMatch(
                    product_id=row["product_id"],
                    name=row["name"],
                    garment_type=row["garment_type"],
                    category=normalize_category(row["garment_type"]),
                    price=row["price"],
                    available_sizes=[r["size"] for r in inventory if r["quantity"] > 0],
                    total_stock=sum(r["quantity"] for r in inventory),
                )
            )

    return ProductSearchResults(
        query=query,
        count=len(matches),
        category_matched=category if category != "other" else None,
        products=matches,
        message=None if matches else f"No products matched '{query}'.",
    )


def get_product_details(product_name_or_query: str) -> ProductDetails:
    """Look up a product's description and base price by name or search query.

    Use this for any question about what a product is, what it costs, what
    colors it comes in, or which sizes are available. Pass the shopper's words
    directly — a product name, a slug, or a description like "navy hoodie".
    Returns found=False with suggestions if nothing matches; never guess a
    price or description that this tool did not return.
    """
    query = product_name_or_query.strip()
    with get_db() as conn:
        row = _resolve_product(conn, query)
        if row is None:
            return ProductDetails(
                found=False,
                message=f"No product matched '{product_name_or_query}'.",
                suggestions=_suggest(conn, product_name_or_query),
            )

        inventory = _inventory_rows(conn, row["product_id"])

        # Was the query specific, or did it match many products? An exact slug
        # or exact name means the shopper named one product; otherwise this is
        # a broad term like "hoodie" and returning a single product silently
        # would be misleading, so flag the ambiguity instead of hiding it.
        is_exact = query.lower() in (row["product_id"].lower(), row["name"].lower())
        matches = [] if is_exact else _find_matches(conn, query)
        other_names = [m["name"] for m in matches if m["product_id"] != row["product_id"]]

    available = [r["size"] for r in inventory if r["quantity"] > 0]
    total = sum(r["quantity"] for r in inventory)

    if len(matches) > 1:
        message = (
            f"'{query}' matches {len(matches)} products — showing {row['name']}. "
            "Use search_products to list them all, or name one product for its details."
        )
        suggestions = other_names[:_MAX_SUGGESTIONS]
    else:
        message = None if available else "This product is currently sold out in every size."
        suggestions = []

    return ProductDetails(
        found=True,
        product_id=row["product_id"],
        name=row["name"],
        garment_type=row["garment_type"],
        description=row["description"],
        price=row["price"],
        colors=parse_json_array(row["colors"]),
        available_sizes=available,
        total_stock=total,
        message=message,
        suggestions=suggestions,
    )


def check_inventory(product_id: str, size: str | None = None) -> InventoryResult:
    """Return exact in-stock counts by size for a product.

    ``product_id`` is the product's slug id (e.g. "basic-hoodie-big-yale"), but
    a product name or search query also works — it is resolved the same way as
    get_product_details. Optionally pass ``size`` (XS, S, M, L, XL, XXL) to get
    just that size. Always call this before telling a shopper whether something
    is in stock; report sold-out sizes honestly rather than assuming stock.
    """
    with get_db() as conn:
        row = _resolve_product(conn, product_id)
        if row is None:
            return InventoryResult(
                found=False,
                message=f"No product matched '{product_id}'.",
                suggestions=_suggest(conn, product_id),
            )

        inventory = _inventory_rows(conn, row["product_id"])

    if size is not None:
        wanted = size.strip().upper()
        inventory = [r for r in inventory if r["size"].upper() == wanted]
        if not inventory:
            return InventoryResult(
                found=True,
                product_id=row["product_id"],
                name=row["name"],
                sizes=[],
                total_stock=0,
                in_stock=False,
                message=f"{row['name']} is not offered in size {wanted}.",
            )

    sizes = [SizeStock(size=r["size"], quantity=r["quantity"]) for r in inventory]
    total = sum(s.quantity for s in sizes)
    any_stock = any(s.in_stock for s in sizes)

    if not any_stock:
        where = f"size {size.strip().upper()}" if size else "any size"
        message = f"{row['name']} is sold out in {where}."
    else:
        message = None

    return InventoryResult(
        found=True,
        product_id=row["product_id"],
        name=row["name"],
        sizes=sizes,
        total_stock=total,
        in_stock=any_stock,
        message=message,
    )


# Fit conventions by category. The catalogue has no measurement data, so these
# are general collegiate-apparel conventions (heavyweight fleece runs roomy;
# garment-washed tees and classic crewnecks sit true to size; performance wear
# is cut trimmer). They give the agent consistent, honest sizing guidance.
_FIT_BY_CATEGORY: dict[str, tuple[str, str]] = {
    "hoodie": (
        "runs slightly roomy",
        "Our hoodies have a relaxed, heavyweight-fleece fit. Take your usual size for a "
        "classic campus drape, or size down one if you want it more fitted.",
    ),
    "crewneck": (
        "true to size",
        "Crewnecks fit true to size with a classic cut — take your normal size. Size up "
        "one if you like to layer underneath.",
    ),
    "t-shirt": (
        "true to size",
        "Tees are garment-washed and fit true to size. If you prefer a looser tee, size up one.",
    ),
    "quarter-zip": (
        "true to size, lightly relaxed",
        "Quarter-zips fit true to size with a little room for a layer underneath.",
    ),
    "jacket": (
        "roomy for layering",
        "Jackets are cut with room to layer — take your usual size over a sweater, or size "
        "up if you plan to layer heavily.",
    ),
    "long-sleeve": (
        "athletic / trimmer",
        "Performance long-sleeves have a trimmer, athletic cut — size up one if you want more room.",
    ),
    "other": ("true to size", "This style fits true to size."),
}


def size_guidance(
    product_name_or_query: str | None = None, garment_type: str | None = None
) -> SizeGuidance:
    """Advise on how a style fits, to help a shopper pick the right size.

    Call this for any fit or sizing question ("will this run big?", "should I
    size up?", "how do your hoodies fit?"). Pass the product name/query, or just
    a garment type like "hoodie". Returns a fit label and plain advice. Every
    style is cut XS-XXL. Pair this with check_inventory to confirm the suggested
    size is actually in stock.
    """
    with get_db() as conn:
        row = _resolve_product(conn, product_name_or_query) if product_name_or_query else None
        if garment_type:
            category = normalize_category(garment_type)
        elif row is not None:
            category = normalize_category(row["garment_type"])
        else:
            category = None

    if category is None:
        return SizeGuidance(
            category="general",
            fit="mostly true to size",
            advice=(
                "Most of our collegiate styles fit true to size, though heavyweight hoodies "
                "run a little roomy. Tell me the specific item and I'll be exact."
            ),
            sizes_offered=list(SIZE_ORDER),
            found=False,
            message="No specific product identified; giving general guidance.",
        )

    fit, advice = _FIT_BY_CATEGORY.get(category, _FIT_BY_CATEGORY["other"])
    return SizeGuidance(
        category=category,
        fit=fit,
        advice=advice,
        sizes_offered=list(SIZE_ORDER),
        product_id=row["product_id"] if row else None,
        name=row["name"] if row else None,
        found=row is not None,
    )


__all__ = [
    "search_products",
    "get_product_details",
    "check_inventory",
    "size_guidance",
]
