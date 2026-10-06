"""PydanticAI agent for the Campus Customs chatbot.

Loads the system prompt from prompts/prompt.md and configures the LLM through
Portkey (an OpenAI-compatible gateway) using environment variables:

    PORTKEY_API_KEY   required — the Portkey API key
    PORTKEY_MODEL     optional — model name, defaults to gpt-4o-mini
    PORTKEY_BASE_URL  optional — gateway URL, defaults to Portkey's public endpoint

The agent is created lazily so that importing this module never fails just
because a key is missing — the failure surfaces only when a chat is actually
requested, with a clear message. backend/tools.py is imported here so its
database tools (placeholder for now) attach to the agent in one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI

from backend import tools
from backend.models import AgentReply


@dataclass
class ChatDeps:
    """Per-conversation context handed to the agent at run time (Problem 8).

    Carries who the agent is talking to (a logged-in customer, or a guest) and
    what product page they are currently viewing, so "this"/"it" can be resolved.
    """

    user_id: int | None = None
    first_name: str | None = None
    email: str | None = None
    page_product_id: str | None = None
    page_product_title: str | None = None


def _context_instructions(ctx: RunContext[ChatDeps]) -> str:
    """Dynamic instructions: tell the agent who and what it's dealing with.

    Appended to the static persona instructions on every run, with the live deps.
    Registered as instructions (not a system prompt) so they are re-applied even
    when a logged-in user's history is replayed.
    """
    deps = ctx.deps
    lines: list[str] = []

    if deps.first_name:
        who = f"You are speaking with {deps.first_name}"
        if deps.email:
            who += f" (a logged-in customer, {deps.email})"
        who += ". Address them by first name when it feels natural."
        lines.append(who)
    else:
        lines.append("You are speaking with a guest who is not signed in. Do not assume a name.")

    if deps.page_product_id:
        title = deps.page_product_title or "the product on screen"
        lines.append(
            f'The shopper is currently viewing this product page: "{title}" '
            f"(product_id: {deps.page_product_id}). If they say \"this\", \"it\", "
            f'"this one", or ask "how much is this?" / "do you have this in <size>?" '
            f"without naming a product, they mean THIS product — use this exact "
            f"product_id with your tools."
        )

    return "\n".join(lines)

BACKEND_DIR = Path(__file__).resolve().parent
PROMPT_PATH = BACKEND_DIR / "prompts" / "prompt.md"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.portkey.ai/v1"

# Load .env from the repo root so PORTKEY_* are available when run standalone.
load_dotenv(BACKEND_DIR.parent / ".env")


def load_system_prompt() -> str:
    """Read the persona/guidelines prompt from prompts/prompt.md."""
    if not PROMPT_PATH.is_file():
        raise RuntimeError(f"System prompt not found at {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_model() -> OpenAIChatModel:
    """Configure the LLM: our OpenAI client points at the Portkey gateway."""
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    base_url = os.environ.get("PORTKEY_BASE_URL", DEFAULT_BASE_URL)
    model_name = os.environ.get("PORTKEY_MODEL", DEFAULT_MODEL)

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers={"x-portkey-api-key": api_key},
    )
    return OpenAIChatModel(model_name, provider=OpenAIProvider(openai_client=client))


@lru_cache(maxsize=1)
def get_agent() -> Agent[ChatDeps, AgentReply]:
    """Return the singleton Campus Customs agent, building it on first use.

    output_type is AgentReply so the model returns structured {reply, products}
    rather than free text. deps_type is ChatDeps so each run can carry the
    customer and page context. Cached so the model/client are created once.
    """
    agent: Agent[ChatDeps, AgentReply] = Agent(
        _build_model(),
        output_type=AgentReply,
        deps_type=ChatDeps,
        # Use instructions, not a system_prompt: instructions are re-applied on
        # every run even when message_history is passed, whereas a system prompt
        # would be taken from the (system-prompt-less) replayed history and lost.
        # This matters for logged-in users, whose history we replay for memory.
        instructions=load_system_prompt(),
        # Database lookup tools: the agent calls these to read real catalogue
        # and inventory data instead of guessing prices or stock.
        tools=[
            tools.search_products,
            tools.get_product_details,
            tools.check_inventory,
            tools.size_guidance,
        ],
        retries=2,
    )
    # Dynamic instructions that inject the live customer + page context.
    agent.instructions(_context_instructions)
    return agent
