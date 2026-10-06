"""Pydantic models for the Campus Customs chatbot.

These are the shapes exchanged over the /api/chat boundary and produced by the
PydanticAI agent. Keeping them in one module lets the route handler, the agent,
and (later) the database tools all agree on the same contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

Role = Literal["user", "assistant"]


class ChatTurn(BaseModel):
    """One prior message in the conversation, replayed to give the agent context."""

    role: Role
    content: str


class PageContext(BaseModel):
    """What the shopper is currently looking at, sent with each chat message.

    Lets the agent resolve "this" / "it" to the product on screen. Populated by
    the frontend only on a product detail page; None elsewhere.
    """

    product_id: str | None = Field(default=None, description="Slug of the product being viewed.")
    title: str | None = Field(default=None, description="Display name of that product.")


class ChatRequest(BaseModel):
    """What the frontend POSTs to /api/chat."""

    message: str = Field(..., min_length=1, description="The shopper's new message.")
    history: list[ChatTurn] = Field(
        default_factory=list,
        description="Prior turns in this conversation, oldest first.",
    )
    page_context: PageContext | None = Field(
        default=None,
        description="The product page the shopper is on, if any.",
    )


class ProductRef(BaseModel):
    """A product the assistant chose to surface, for the frontend to render as a card.

    Deliberately thin: the product_id is the source of truth, and the route layer
    can hydrate full catalogue/inventory detail from the database when the tools
    land in a later problem.
    """

    product_id: str
    name: str
    reason: str | None = Field(
        default=None,
        description="One short line on why this product fits the request.",
    )


class AgentReply(BaseModel):
    """The agent's structured output.

    The LLM is asked to produce this shape so the reply text and any product
    recommendations arrive as separate, typed fields rather than one blob of
    prose the frontend would have to parse. The LLM only names products (by id
    + a reason); the backend hydrates the display data — see MatchedProduct.
    """

    reply: str = Field(..., description="The assistant's message to the shopper.")
    products: list[ProductRef] = Field(
        default_factory=list,
        description="Products to display alongside the reply, if any.",
    )


class MatchedProduct(BaseModel):
    """A product card returned to the frontend alongside a chat reply.

    Built by the /api/chat route, not the LLM: the agent supplies a product_id
    and a reason, and the backend fills name/price/image/stock from the database
    so the card is authoritative (no hallucinated prices or images) and matches
    the catalogue cards from Problem 3. product_id is the key the frontend uses
    to link to the existing /products/:id detail view.
    """

    product_id: str = Field(..., description="Slug id; the frontend links to /products/<id>.")
    name: str = Field(..., description="Display name.")
    price: float = Field(..., description="Base price in US dollars, from the catalogue.")
    image_url: str = Field(..., description="Served image path, e.g. /media/products/<slug>.jpg.")
    garment_type: str = Field(..., description="Raw garment type, shown as a subtitle.")
    in_stock: bool = Field(..., description="True if any size has stock.")
    reason: str | None = Field(
        default=None, description="The agent's one-line reason this product fits the request."
    )


class ChatResponse(BaseModel):
    """What /api/chat returns to the frontend.

    `products` are fully-hydrated cards (see MatchedProduct), ready to render.
    """

    reply: str
    products: list[MatchedProduct] = Field(default_factory=list)


class ChatHistoryMessage(BaseModel):
    """One stored turn, shaped for the frontend to drop straight into the chat window."""

    role: Role
    content: str
    products: list[MatchedProduct] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    """What GET /api/chat/history returns — a logged-in user's past conversation."""

    messages: list[ChatHistoryMessage] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Structured outputs for the agent's database lookup tools (Problem 6)
#
# These are what get_product_details() and check_inventory() return. Every
# model carries an explicit `found` flag and a human-readable `message` so the
# agent is never forced to guess when a product is missing or ambiguous — it
# can read the truth off the structured result instead of hallucinating.
# --------------------------------------------------------------------------


def stock_status(quantity: int) -> str:
    """Clean, explicit stock indicator for a count: never ambiguous."""
    return "in stock" if quantity > 0 else "out of stock"


class SizeStock(BaseModel):
    """Stock for one size of one product."""

    size: str = Field(..., description="Size label: XS, S, M, L, XL, or XXL.")
    quantity: int = Field(..., description="Exact units on hand for this size.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        """True when quantity > 0."""
        return self.quantity > 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        """Explicit 'in stock' / 'out of stock' label, so a 0 count is never ambiguous."""
        return stock_status(self.quantity)


class ProductDetails(BaseModel):
    """Result of get_product_details — a product's description and base price."""

    found: bool = Field(..., description="Whether a matching product was found.")
    product_id: str | None = Field(default=None, description="The matched product's slug id.")
    name: str | None = Field(default=None, description="Display name of the matched product.")
    garment_type: str | None = Field(default=None, description="Raw garment type, e.g. 'pullover hoodie'.")
    description: str | None = Field(default=None, description="Full product description.")
    price: float | None = Field(default=None, description="Base price in US dollars.")
    colors: list[str] = Field(default_factory=list, description="Available colors.")
    available_sizes: list[str] = Field(
        default_factory=list, description="Sizes currently in stock (quantity > 0)."
    )
    total_stock: int = Field(default=0, description="Total units on hand across all sizes.")
    message: str | None = Field(
        default=None,
        description="Human-readable note, e.g. a not-found explanation or disambiguation hint.",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Names of close matches, when the query was ambiguous or missed.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stock_status(self) -> str:
        """Explicit 'in stock' / 'out of stock' for the product as a whole."""
        return stock_status(self.total_stock)


class ProductMatch(BaseModel):
    """One product in a search result list (Problem 6 follow-up)."""

    product_id: str = Field(..., description="The product's slug id.")
    name: str = Field(..., description="Display name.")
    garment_type: str = Field(..., description="Raw garment type.")
    category: str = Field(..., description="Normalized category: hoodie, crewneck, t-shirt, etc.")
    price: float = Field(..., description="Base price in US dollars.")
    available_sizes: list[str] = Field(
        default_factory=list, description="Sizes currently in stock (quantity > 0)."
    )
    total_stock: int = Field(default=0, description="Total units on hand across all sizes.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        return self.total_stock > 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stock_status(self) -> str:
        """Explicit 'in stock' / 'out of stock', so a fully sold-out product is unambiguous."""
        return stock_status(self.total_stock)


class ProductSearchResults(BaseModel):
    """Result of search_products — every product matching a case-insensitive partial query."""

    query: str = Field(..., description="The original search query.")
    count: int = Field(..., description="Number of products matched.")
    category_matched: str | None = Field(
        default=None,
        description="The normalized category the query mapped to, if any (e.g. 'hoodie').",
    )
    products: list[ProductMatch] = Field(
        default_factory=list, description="All matching products, ordered by name."
    )
    message: str | None = Field(
        default=None, description="Human-readable note, e.g. a no-results explanation."
    )


class SizeGuidance(BaseModel):
    """Result of size_guidance — how a style fits, to help a shopper choose a size."""

    category: str = Field(..., description="Normalized category the advice applies to.")
    fit: str = Field(..., description="Short fit label, e.g. 'true to size' or 'runs roomy'.")
    advice: str = Field(..., description="One or two sentences of plain sizing advice.")
    sizes_offered: list[str] = Field(
        default_factory=list, description="The size run every style is cut in (XS–XXL)."
    )
    product_id: str | None = Field(default=None, description="Resolved product, if a name was given.")
    name: str | None = Field(default=None, description="Resolved product name, if any.")
    found: bool = Field(default=False, description="Whether a specific product was resolved.")
    message: str | None = Field(default=None, description="Any note, e.g. that advice is general.")


class InventoryResult(BaseModel):
    """Result of check_inventory — exact in-stock counts by size."""

    found: bool = Field(..., description="Whether a matching product was found.")
    product_id: str | None = Field(default=None, description="The matched product's slug id.")
    name: str | None = Field(default=None, description="Display name of the matched product.")
    sizes: list[SizeStock] = Field(
        default_factory=list,
        description="Per-size stock. One entry per size, or just the requested size if one was given.",
    )
    total_stock: int = Field(default=0, description="Total units on hand across the returned sizes.")
    in_stock: bool = Field(default=False, description="True if any returned size has stock.")
    message: str | None = Field(
        default=None, description="Human-readable note, e.g. 'sold out' or a not-found explanation."
    )
    suggestions: list[str] = Field(
        default_factory=list, description="Names of close matches, when the query missed."
    )
