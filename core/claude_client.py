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

Importing ``core.secrets`` here is load-bearing, not incidental: it calls
``spiritwriter.secrets.configure(service_name="claude-studio")`` at import
time, and the provider reads that service name at call time when it resolves
``ANTHROPIC_API_KEY`` from the OS keychain. The former local client pulled the
key via ``core.secrets`` too, so importing it here keeps keychain resolution
on the same "claude-studio" service regardless of import order — without it, a
caller that imports only this module would silently fall back to spiritwriter's
default service and miss a CSP-stored key.
"""

from core import secrets as _secrets  # noqa: F401  (side effect: configure keychain service)
from spiritwriter.llm.anthropic import ClaudeClient, JSONExtractor  # noqa: F401

__all__ = ["ClaudeClient", "JSONExtractor"]
