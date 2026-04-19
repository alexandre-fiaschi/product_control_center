"""Thin wrapper around the Anthropic Messages API for release-notes extraction.

Mirrors the pattern in ``jira/client.py``: custom exception, constructor with
auth params, module logger.  The Anthropic SDK handles 429 / 5xx retries
internally — we don't add our own.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import anthropic

from app.config import Settings

logger = logging.getLogger("claude.client")

# Pricing per 1M tokens (USD) — https://platform.claude.com/docs/en/about-claude/pricing
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7":   {"input": 5.0, "output": 25.0},
    "claude-opus-4-6":   {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a Claude API call. Returns 0.0 for unknown models."""
    prices = MODEL_PRICING.get(model)
    if not prices:
        logger.warning("Unknown model %r for cost calculation, reporting $0", model)
        return 0.0
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


class ClaudeExtractionError(Exception):
    """Raised when a Claude API call fails or returns an unusable response."""

    def __init__(
        self,
        message: str,
        *,
        stop_reason: str | None = None,
        raw_response: Any = None,
    ):
        self.stop_reason = stop_reason
        self.raw_response = raw_response
        super().__init__(message)


class ClaudeClient:
    """Low-level wrapper around ``anthropic.Anthropic`` for extraction calls."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-opus-4-6",
        max_tokens: int = 16384,
        timeout_s: int = 120,
    ):
        if not api_key:
            raise ClaudeExtractionError("ANTHROPIC_API_KEY is empty — cannot create client")
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=float(timeout_s),
            max_retries=2,  # default — handles connection errors; we handle 429s ourselves
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> ClaudeClient:
        """Build a client from the application settings + pipeline.json."""
        claude_cfg = settings.pipeline_config.get("pipeline", {}).get("claude", {})
        return cls(
            api_key=settings.ANTHROPIC_API_KEY,
            model=claude_cfg.get("model", "claude-opus-4-6"),
            max_tokens=claude_cfg.get("max_tokens", 16384),
            timeout_s=claude_cfg.get("timeout_s", 120),
        )

    # ------------------------------------------------------------------
    # Extraction call
    # ------------------------------------------------------------------

    def send_extraction(
        self,
        content_blocks: list[dict],
        tools: list[dict],
        system_prompt: str,
        *,
        max_items: int = 15,
    ) -> tuple[list[dict], str, dict]:
        """Run the agentic tool-use loop per Anthropic docs.

        Uses ``tool_choice: auto`` (default). Claude returns one or more
        tool_use blocks per response. We execute them, send results back,
        and loop while ``stop_reason == "tool_use"``.  Stops when Claude
        sends ``end_turn`` or when ``max_items`` is reached (safety cap).

        Returns ``(all_tool_calls, stop_reason, usage_info)``.
        """
        messages = [{"role": "user", "content": content_blocks}]
        all_tool_calls: list[dict] = []
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        turn = 0

        while True:
            turn += 1

            # Log what we're sending this turn
            if logger.isEnabledFor(logging.DEBUG):
                for i, msg in enumerate(messages):
                    role = msg["role"]
                    content = msg["content"]
                    if isinstance(content, list):
                        block_summary = []
                        for b in content:
                            if isinstance(b, dict):
                                btype = b.get("type", "?")
                                if btype == "document":
                                    data_len = len(b.get("source", {}).get("data", ""))
                                    block_summary.append(f"document({data_len} b64 chars)")
                                elif btype == "image":
                                    data_len = len(b.get("source", {}).get("data", ""))
                                    block_summary.append(f"image({data_len} b64 chars)")
                                elif btype == "text":
                                    block_summary.append(f"text({len(b.get('text', ''))} chars)")
                                elif btype == "tool_use":
                                    block_summary.append(f"tool_use({b.get('name', '?')})")
                                elif btype == "tool_result":
                                    block_summary.append(f"tool_result({b.get('tool_use_id', '?')[:8]})")
                                else:
                                    block_summary.append(btype)
                            else:
                                block_summary.append(f"{getattr(b, 'type', '?')}")
                        logger.debug("  msg[%d] %s: %s", i, role, ", ".join(block_summary))
                    else:
                        logger.debug("  msg[%d] %s: text(%d chars)", i, role, len(str(content)))

            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    cache_control={"type": "ephemeral"},
                )
            except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
                if isinstance(exc, anthropic.RateLimitError):
                    retry_after = getattr(exc.response, "headers", {}).get("retry-after")
                    wait = int(retry_after) if retry_after else 60
                    logger.info("Rate limited on turn %d, waiting %ds...", turn, wait)
                else:
                    wait = 10
                    logger.warning("Connection error on turn %d, retrying in %ds...", turn, wait)
                time.sleep(wait)
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    cache_control={"type": "ephemeral"},
                )
            except anthropic.AuthenticationError as exc:
                raise ClaudeExtractionError(
                    f"Authentication failed — check ANTHROPIC_API_KEY: {exc}",
                ) from exc
            except anthropic.APITimeoutError as exc:
                raise ClaudeExtractionError(
                    f"API call timed out: {exc}",
                ) from exc

            # Detailed usage from this turn
            u = response.usage
            cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
            cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
            uncached = u.input_tokens  # tokens NOT from cache

            total_input += u.input_tokens
            total_output += u.output_tokens
            total_cache_read += cache_read
            total_cache_write += cache_write

            # Collect tool_use blocks from this turn
            turn_tool_calls = [
                {"id": block.id, "name": block.name, "input": block.input}
                for block in response.content
                if block.type == "tool_use"
            ]
            all_tool_calls.extend(turn_tool_calls)

            # Log each item extracted
            for tc in turn_tool_calls:
                inp = tc["input"]
                logger.info(
                    "  → %s [%s] %s",
                    inp.get("am_card", "?"),
                    ", ".join(inp.get("customers", [])) or "—",
                    inp.get("title", "?")[:80],
                )

            # Log how many messages we're sending
            n_messages = len(messages)
            total_cost = compute_cost(self._model, total_input, total_output)
            logger.info(
                "Turn %d: %d tool call(s), stop_reason=%s, total_items=%d | "
                "uncached=%d, cache_read=%d, cache_write=%d, out=%d | "
                "messages=%d | cumulative: %d in / %d out ($%.4f)",
                turn, len(turn_tool_calls), response.stop_reason, len(all_tool_calls),
                uncached, cache_read, cache_write, u.output_tokens,
                n_messages,
                total_input, total_output, total_cost,
            )

            # Stop conditions
            if response.stop_reason != "tool_use":
                break
            if len(all_tool_calls) >= max_items:
                logger.warning("Safety cap reached (%d items), stopping loop", max_items)
                break

            # Send tool results back and continue
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": tc["id"], "content": "saved"}
                    for tc in turn_tool_calls
                ],
            })

        if not all_tool_calls:
            raise ClaudeExtractionError(
                "Claude returned no tool calls",
                stop_reason=response.stop_reason,
                raw_response=response,
            )

        cost = compute_cost(self._model, total_input, total_output)
        usage_info = {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cache_read,
            "cache_write_tokens": total_cache_write,
            "model": self._model,
            "cost_usd": round(cost, 4),
        }

        logger.info(
            "Extraction complete: %d item(s), %d in (%d cached_read, %d cached_write) / %d out → $%.4f (%s)",
            len(all_tool_calls), total_input, total_cache_read, total_cache_write,
            total_output, cost, self._model,
        )

        return all_tool_calls, response.stop_reason, usage_info
