"""Guard tests for the ClaudeClient → spiritwriter AnthropicProvider port.

``core/claude_client.py`` is now a thin re-export of spiritwriter's provider,
so the compatibility contract that protects CSP call sites lives in another
repo. These tests fail loudly if an upstream signature drifts or the keychain
service-name side effect regresses, instead of surfacing as a runtime
"ANTHROPIC_API_KEY not set" deep in a production run. See PR #19 / #15.
"""
import inspect

from core.claude_client import ClaudeClient, JSONExtractor
from spiritwriter.llm.anthropic import AnthropicProvider


def test_claudeclient_is_provider_with_expected_api():
    # ClaudeClient must be the provider itself (alias), with the methods and
    # backward-compatible kwargs every CSP call site relies on.
    assert ClaudeClient is AnthropicProvider
    for method in ("query", "query_with_image", "query_with_images"):
        assert callable(getattr(ClaudeClient, method)), method

    query_params = inspect.signature(ClaudeClient.query).parameters
    assert {"system_prompt", "return_usage"} <= query_params.keys()

    # query_with_image must still accept the kwarg-only `image_path` path.
    image_params = inspect.signature(ClaudeClient.query_with_image).parameters
    assert "image_path" in image_params

    # JSONExtractor must remain importable from the same module for back-compat.
    assert hasattr(JSONExtractor, "extract")


def test_importing_client_configures_keychain_service():
    # Importing the client must pin the keychain service to "claude-studio"
    # (via core.secrets' configure side effect), so the provider's keychain
    # lookup resolves CSP-stored keys regardless of import order.
    import core.claude_client  # noqa: F401  (re-import for the side effect)
    from spiritwriter.secrets import keychain

    assert keychain.SERVICE_NAME == "claude-studio"
