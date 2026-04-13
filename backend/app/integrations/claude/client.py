"""Thin wrapper around the Anthropic Messages API for release-notes extraction.

Mirrors the pattern in ``jira/client.py``: custom exception, constructor with
auth params, module logger.  The Anthropic SDK handles 429 / 5xx retries
internally — we don't add our own.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from app.config import Settings

logger = logging.getLogger("claude.client")

# Pricing per 1M tokens (USD) — https://platform.claude.com/docs/en/about-claude/pricing
MODEL_PRICING: dict[str, dict[str, float]] = {
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
    ) -> tuple[list[dict], str, dict]:
        """Send a single request and collect all tool-use blocks.

        Claude can return multiple tool calls in one response. We use
        ``tool_choice: auto`` so Claude calls the tool as many times as
        needed and then stops with ``end_turn``.

        Returns ``(tool_use_blocks, stop_reason, usage_info)``.

        Raises :class:`ClaudeExtractionError` on auth failure, timeout, or
        when the response contains zero tool calls.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": content_blocks}],
                tools=tools,
            )
        except anthropic.AuthenticationError as exc:
            raise ClaudeExtractionError(
                f"Authentication failed — check ANTHROPIC_API_KEY: {exc}",
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise ClaudeExtractionError(
                f"API call timed out: {exc}",
            ) from exc

        # Collect all tool_use blocks
        tool_use_blocks = [
            {"id": block.id, "name": block.name, "input": block.input}
            for block in response.content
            if block.type == "tool_use"
        ]

        if not tool_use_blocks:
            raise ClaudeExtractionError(
                "Claude returned no tool calls",
                stop_reason=response.stop_reason,
                raw_response=response,
            )

        # Token usage + cost
        cost = compute_cost(self._model, response.usage.input_tokens, response.usage.output_tokens)
        usage_info = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": self._model,
            "cost_usd": round(cost, 4),
        }

        logger.info(
            "Extraction complete: %d item(s), %d input tokens, %d output tokens → $%.4f (%s)",
            len(tool_use_blocks),
            response.usage.input_tokens,
            response.usage.output_tokens,
            cost,
            self._model,
        )

        return tool_use_blocks, response.stop_reason, usage_info
