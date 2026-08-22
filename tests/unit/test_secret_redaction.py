"""Unit tests for secret redaction in checkpointed onboarding sessions.

Regression coverage for a leaked ElevenLabs key: ProviderTester captured a
provider's get_headers() output verbatim into
.claude-studio/onboarding_sessions/elevenlabs.json, which is committed to a
public repo.
"""

import json
import pytest

from core.secrets import REDACTED, redact_secrets, redact_structure


# Synthetic keys, shaped like the real thing but not valid credentials.
FAKE_ELEVENLABS = "sk_0123456789abcdef0123456789abcdef0123456789abcdef"
FAKE_ANTHROPIC = "sk-ant-api03-" + "A" * 40
FAKE_OPENAI = "sk-proj-" + "B" * 40
FAKE_LUMA = "luma-01234567-89ab-cdef-0123-456789abcdef"
FAKE_GOOGLE = "AIza" + "C" * 35


class TestRedactSecrets:
    """redact_secrets scrubs known key shapes and caller-supplied literals."""

    @pytest.mark.parametrize("secret", [
        FAKE_ELEVENLABS,
        FAKE_ANTHROPIC,
        FAKE_OPENAI,
        FAKE_LUMA,
        FAKE_GOOGLE,
        "ghp_" + "D" * 36,
        "xoxb-1234567890-abcdefghij",
    ])
    def test_redacts_known_key_shapes(self, secret):
        text = f"{{'api-key': '{secret}'}}"
        result = redact_secrets(text)
        assert secret not in result
        assert REDACTED in result

    def test_redacts_the_exact_leaked_header_shape(self):
        """The precise capture that leaked: an ElevenLabs headers dict."""
        captured = (
            "{'xi-api-key': '%s', 'Content-Type': 'application/json'}" % FAKE_ELEVENLABS
        )
        result = redact_secrets(captured)
        assert FAKE_ELEVENLABS not in result
        assert "Content-Type" in result  # non-secret content survives

    def test_redacts_keychain_sourced_literal_via_extra_values(self):
        """A key from the OS keychain is not in os.environ, so callers pass it."""
        opaque = "not-a-recognizable-key-shape-12345"
        assert redact_secrets(opaque) == opaque  # not caught by shape alone
        assert opaque not in redact_secrets(opaque, extra_values=[opaque])

    def test_redacts_env_var_values(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_API_KEY", "opaque-env-value-98765")
        result = redact_secrets("key is opaque-env-value-98765 here")
        assert "opaque-env-value-98765" not in result

    def test_ignores_short_literals(self, monkeypatch):
        """A short env value must not blank out unrelated text."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
        assert redact_secrets("this is a test string") == "this is a test string"

    def test_leaves_clean_text_untouched(self):
        clean = "AudioGenerationResult(success=True, format='mp3')"
        assert redact_secrets(clean) == clean

    @pytest.mark.parametrize("value", [None, 123, "", {"a": 1}])
    def test_passes_through_non_strings(self, value):
        assert redact_secrets(value) == value


class TestProviderTesterRedaction:
    """Captured test output is scrubbed before it reaches a session file."""

    @pytest.mark.asyncio
    async def test_headers_output_is_redacted(self):
        from agents.provider_onboarding import ProviderTester

        class FakeConfig:
            api_key = FAKE_ELEVENLABS

        class FakeProvider:
            config = FakeConfig()

            def get_headers(self):
                return {"xi-api-key": self.config.api_key}

        tester = ProviderTester(claude_client=None)
        result = await tester.run_test(
            {"name": "test_get_headers", "method": "get_headers", "inputs": {}},
            FakeProvider(),
        )

        assert FAKE_ELEVENLABS not in json.dumps(result)
        assert REDACTED in result["output"]

    @pytest.mark.asyncio
    async def test_error_text_is_redacted(self):
        from agents.provider_onboarding import ProviderTester

        class ExplodingProvider:
            api_key = FAKE_ELEVENLABS

            def get_headers(self):
                raise RuntimeError(f"auth failed for {FAKE_ELEVENLABS}")

        tester = ProviderTester(claude_client=None)
        result = await tester.run_test(
            {"name": "test_get_headers", "method": "get_headers", "inputs": {}},
            ExplodingProvider(),
        )

        assert FAKE_ELEVENLABS not in json.dumps(result)

    def test_provider_secrets_collects_from_instance_and_config(self):
        from agents.provider_onboarding import ProviderTester

        class FakeConfig:
            api_key = "config-level-secret-value"

        class FakeProvider:
            api_key = "instance-level-secret-value"
            config = FakeConfig()

        secrets = ProviderTester._provider_secrets(FakeProvider())
        assert "instance-level-secret-value" in secrets
        assert "config-level-secret-value" in secrets

    def test_provider_secrets_tolerates_bare_object(self):
        from agents.provider_onboarding import ProviderTester

        assert ProviderTester._provider_secrets(object()) == []


class TestSessionSaveRedaction:
    """OnboardingSession.save() scrubs the whole payload on the way to disk."""

    def test_save_redacts_secrets_anywhere_in_session(self, tmp_path):
        from agents.provider_onboarding import OnboardingSession

        from datetime import datetime

        session = OnboardingSession(
            provider_name="fakeprov",
            started_at=datetime(2026, 1, 1),
        )
        # Simulate a secret reaching a field other than captured test output.
        session.learnings = [f'client init uses API_KEY = "{FAKE_ELEVENLABS}"']

        path = tmp_path / "fakeprov.json"
        session.save(str(path))

        written = path.read_text()
        assert FAKE_ELEVENLABS not in written
        assert REDACTED in written
        json.loads(written)  # still valid JSON


class TestCommittedSessionFilesAreClean:
    """Guard: no committed onboarding checkpoint may carry a live key."""

    def test_no_secrets_in_committed_session_files(self):
        from pathlib import Path

        sessions = Path(".claude-studio/onboarding_sessions")
        if not sessions.is_dir():
            pytest.skip("no onboarding session files in this checkout")

        offenders = []
        for path in sorted(sessions.glob("*.json")):
            raw = path.read_text()
            if redact_secrets(raw) != raw:
                offenders.append(path.name)

        assert not offenders, f"secrets found in committed session files: {offenders}"


# Credentials containing characters that str()/json.dumps escape. A raw-literal
# match misses these once serialized, so redaction must happen first.
ESCAPING_SECRETS = [
    'abc"def\'ghi12345',   # both quote styles -> repr backslash-escapes one
    "abc\\def12345",        # backslash
    'quote"inside-12345',
    "apostrophe'inside-12345",
]


class TestEscapedCredentials:
    """Regression: escaping must not hide a credential from redaction."""

    @pytest.mark.parametrize("secret", ESCAPING_SECRETS)
    def test_redact_structure_beats_repr_escaping(self, secret):
        captured = str(redact_structure({"xi-api-key": secret}, [secret]))
        assert secret not in captured
        assert REDACTED in captured

    @pytest.mark.parametrize("secret", ESCAPING_SECRETS)
    def test_redact_structure_beats_json_escaping(self, secret):
        payload = json.dumps(redact_structure({"key": secret}, [secret]))
        assert secret not in payload
        assert json.dumps(secret)[1:-1] not in payload
        assert REDACTED in payload

    @pytest.mark.parametrize("secret", ESCAPING_SECRETS)
    def test_redact_secrets_matches_already_serialized_forms(self, secret):
        """Backstop for text that was serialized before redaction ran."""
        already = json.dumps({"key": secret})
        assert json.dumps(secret)[1:-1] not in redact_secrets(already, [secret])

    def test_redact_structure_recurses_and_preserves_shape(self):
        data = {"a": [{"b": FAKE_ELEVENLABS}], "c": ("x", FAKE_ANTHROPIC), "n": 1}
        out = redact_structure(data)
        assert out["a"][0]["b"] == REDACTED
        assert out["c"][1] == REDACTED
        assert isinstance(out["c"], tuple)
        assert out["n"] == 1

    @pytest.mark.asyncio
    async def test_run_test_redacts_escaped_credential(self):
        from agents.provider_onboarding import ProviderTester

        secret = 'abc"def\'ghi12345'

        class FakeProvider:
            def __init__(self):
                self.api_key = secret

            def get_headers(self):
                return {"xi-api-key": self.api_key}

        tester = ProviderTester(claude_client=None)
        result = await tester.run_test(
            {"name": "test_get_headers", "method": "get_headers", "inputs": {}},
            FakeProvider(),
        )
        assert secret not in json.dumps(result)

    def test_save_redacts_escaped_credential(self, tmp_path, monkeypatch):
        """save() has no provider instance, so it matches env values and shapes.

        This pins the escaping behaviour: a known credential containing escape
        characters must not survive serialization in escaped form.
        """
        from datetime import datetime
        from agents.provider_onboarding import OnboardingSession

        secret = 'tok"en\\with-escapes-12345'
        monkeypatch.setenv("ELEVENLABS_API_KEY", secret)

        session = OnboardingSession(provider_name="fakeprov", started_at=datetime(2026, 1, 1))
        session.learnings = [f"credential was {secret}"]

        path = tmp_path / "s.json"
        session.save(str(path))
        written = path.read_text()
        assert secret not in written
        assert json.dumps(secret)[1:-1] not in written
        assert REDACTED in written
        json.loads(written)


class TestAuthTypeCoverage:
    """_provider_secrets covers credentials for every supported AuthType."""

    @pytest.mark.parametrize("attr", [
        "api_key", "access_token", "refresh_token", "bearer_token",
        "client_secret", "password", "private_key", "secret_key",
    ])
    def test_collects_named_credential_attrs(self, attr):
        from agents.provider_onboarding import ProviderTester

        provider = type("P", (), {})()
        setattr(provider, attr, "opaque-credential-value-123")
        assert "opaque-credential-value-123" in ProviderTester._provider_secrets(provider)

    def test_collects_custom_auth_credential_by_name_pattern(self):
        """AuthType.CUSTOM: a provider may invent its own credential field."""
        from agents.provider_onboarding import ProviderTester

        provider = type("P", (), {})()
        provider.x_subscription_secret = "opaque-custom-cred-456"
        assert "opaque-custom-cred-456" in ProviderTester._provider_secrets(provider)

    def test_ignores_non_credential_attrs(self):
        from agents.provider_onboarding import ProviderTester

        provider = type("P", (), {})()
        provider.base_url = "https://api.example.com"
        provider.timeout = 300
        assert ProviderTester._provider_secrets(provider) == []

    @pytest.mark.asyncio
    async def test_oauth_token_in_headers_is_redacted(self):
        from agents.provider_onboarding import ProviderTester

        token = "opaque-oauth-access-token-no-recognizable-shape"

        class OAuthProvider:
            def __init__(self):
                self.access_token = token

            def get_headers(self):
                return {"Authorization": f"Bearer {self.access_token}"}

        tester = ProviderTester(claude_client=None)
        result = await tester.run_test(
            {"name": "test_get_headers", "method": "get_headers", "inputs": {}},
            OAuthProvider(),
        )
        assert token not in json.dumps(result)
