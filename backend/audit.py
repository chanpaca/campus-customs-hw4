"""Append-only audit trail for agent interactions (Problem 12).

Every /api/chat interaction is appended as one JSON object per line to
output/audit_trail.json (JSON Lines). The file is opened in append mode and is
never truncated or rewritten, so it survives server restarts and accumulates a
complete, tamper-evident history. JSON Lines is used deliberately: a single
valid JSON array cannot be appended to without rewriting the whole file, which
would break the "append-only / never overwritten" guarantee.

Each record captures:
  - timestamp        ISO-8601 UTC
  - session/user_id  who the interaction belonged to (a guest or a user id)
  - message          the shopper's message (truncated)
  - tools            each tool call: name, arguments, and a short result summary
  - status           "success" or "error"
  - finish_reason    "completed" / "timeout" / "model_error" / "agent_unconfigured"
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "output" / "audit_trail.json"

# Serializes appends so concurrent requests (async handlers + any threadpool
# work in a single uvicorn process) can never interleave a half-written line.
# One record is written per locked open/write/flush, so each line stays a
# complete, valid JSON object. A multi-process deployment would additionally
# need an OS-level file lock (fcntl / msvcrt); a single worker is assumed here.
_WRITE_LOCK = threading.Lock()

# Tool name used by PydanticAI to deliver the structured output — not a real
# database tool, so it is excluded from the logged tool list.
_OUTPUT_TOOL = "final_result"
_MESSAGE_CAP = 500


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize_return(content: Any) -> str:
    """One-line summary of a tool's result, by result-model type."""
    name = type(content).__name__
    if name == "ProductSearchResults":
        return f"count={content.count}, category_matched={content.category_matched}"
    if name == "ProductDetails":
        return f"found={content.found}, name={content.name!r}, price={content.price}"
    if name == "InventoryResult":
        return f"found={content.found}, in_stock={content.in_stock}, total_stock={content.total_stock}"
    if name == "SizeGuidance":
        return f"category={content.category!r}, fit={content.fit!r}"
    text = str(content)
    return text[:120] + ("…" if len(text) > 120 else "")


def _arg_dict(part: Any) -> Any:
    """Tool call arguments as a plain dict, however PydanticAI stored them."""
    try:
        return part.args_as_dict()
    except Exception:  # noqa: BLE001
        args = getattr(part, "args", None)
        if isinstance(args, str):
            try:
                return json.loads(args)
            except ValueError:
                return args
        return args


def summarize_tools(result: Any) -> list[dict[str, Any]]:
    """Extract the tool calls (name, args, result summary) from a completed run."""
    returns_by_id: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []
    try:
        messages = result.all_messages()
    except Exception:  # noqa: BLE001
        return calls

    # First pass: collect tool returns keyed by their call id.
    for message in messages:
        for part in getattr(message, "parts", []):
            if type(part).__name__ == "ToolReturnPart":
                returns_by_id[getattr(part, "tool_call_id", "")] = part.content

    # Second pass: each tool call, paired with its return summary.
    for message in messages:
        for part in getattr(message, "parts", []):
            if type(part).__name__ != "ToolCallPart":
                continue
            if part.tool_name == _OUTPUT_TOOL:
                continue
            call_id = getattr(part, "tool_call_id", "")
            summary = (
                _summarize_return(returns_by_id[call_id]) if call_id in returns_by_id else None
            )
            calls.append(
                {"name": part.tool_name, "arguments": _arg_dict(part), "result_summary": summary}
            )
    return calls


def log_interaction(
    *,
    session: str,
    user_id: int | None,
    message: str,
    page_context: Any | None,
    tools: list[dict[str, Any]],
    status: str,
    finish_reason: str,
    reply_chars: int = 0,
    products_returned: int = 0,
    error: str | None = None,
) -> None:
    """Append one interaction record to output/audit_trail.json (never overwrites)."""
    record: dict[str, Any] = {
        "timestamp": now_iso(),
        "session": session,
        "user_id": user_id,
        "message": (message or "")[:_MESSAGE_CAP],
        "page_context": (
            page_context.model_dump() if hasattr(page_context, "model_dump") else page_context
        ),
        "tools": tools,
        "status": status,
        "finish_reason": finish_reason,
        "reply_chars": reply_chars,
        "products_returned": products_returned,
    }
    if error is not None:
        record["error"] = error[:_MESSAGE_CAP]

    # Serialize to a single line first (cheap), then hold the lock only for the
    # append so the critical section is as short as possible.
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        # Append mode preserves existing content across requests and restarts.
        with open(AUDIT_PATH, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()


def read_records(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the append-only JSON Lines trail back as a JSON array (list).

    Validates the file: each non-empty line must be a complete JSON object.
    Lets callers treat the append-only log as a normal array when they need to.
    """
    target = path or AUDIT_PATH
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(target, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
