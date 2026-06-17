"""Claude client — now sourced from spiritwriter (single source of truth).

``ClaudeClient`` is spiritwriter's ``AnthropicProvider`` (re-exported via the
``ClaudeClient`` alias); ``JSONExtractor`` is its shared LLM-JSON parser. The
local implementations were consolidated into spiritwriter and deleted here —
see claude-studio-producer#15 / spiritwriter-core#76.

The consolidated provider supports everything the former local client did,
plus model configuration and multi-image vision (``query_with_images``).
``query_with_image`` accepts a path (``image_path=``) or raw bytes. One
intentional behavior change: it defaults to spiritwriter's current model
(``claude-sonnet-4-6``); the former local client hardcoded an older Sonnet.
"""

from spiritwriter.llm.anthropic import ClaudeClient, JSONExtractor  # noqa: F401

__all__ = ["ClaudeClient", "JSONExtractor"]
