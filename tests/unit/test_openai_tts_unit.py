"""Unit tests for OpenAI TTS provider (no API calls)"""

import pytest
from core.providers.audio.openai_tts import OpenAITTSProvider
from core.providers.base import AudioProviderConfig


def test_openai_tts_initialization():
    """Test provider initialization"""
    config = AudioProviderConfig(api_key="test_key")
    provider = OpenAITTSProvider(config=config, model="tts-1")

    assert provider.name == "openai_tts"
    assert provider.model == "tts-1"
    assert provider._cost_per_1k == 0.015


def test_openai_tts_hd_initialization():
    """Test HD model initialization"""
    config = AudioProviderConfig(api_key="test_key")
    provider = OpenAITTSProvider(config=config, model="tts-1-hd")

    assert provider.model == "tts-1-hd"
    assert provider._cost_per_1k == 0.030


def test_openai_tts_requires_api_key():
    """Test that API key is required"""
    config = AudioProviderConfig(api_key=None)

    with pytest.raises(ValueError, match="OpenAI API key required"):
        OpenAITTSProvider(config=config)


def test_openai_tts_is_not_stub():
    """Test that provider is not a stub"""
    assert OpenAITTSProvider._is_stub is False


@pytest.mark.asyncio
async def test_openai_tts_list_voices():
    """Test listing available voices"""
    config = AudioProviderConfig(api_key="test_key")
    provider = OpenAITTSProvider(config=config)

    voices = await provider.list_voices()

    assert len(voices) == 6
    voice_ids = [v["id"] for v in voices]
    assert "alloy" in voice_ids
    assert "echo" in voice_ids
    assert "fable" in voice_ids
    assert "onyx" in voice_ids
    assert "nova" in voice_ids
    assert "shimmer" in voice_ids


def test_openai_tts_cost_estimation():
    """Test cost estimation"""
    config = AudioProviderConfig(api_key="test_key")
    provider = OpenAITTSProvider(config=config, model="tts-1")

    # Test 1000 characters
    text_1k = "a" * 1000
    cost = provider.estimate_cost(text_1k)
    assert cost == 0.015  # $0.015 per 1K chars for tts-1

    # Test 2000 characters
    text_2k = "a" * 2000
    cost = provider.estimate_cost(text_2k)
    assert cost == 0.030  # Double the cost


def test_openai_tts_hd_cost_estimation():
    """Test HD model cost estimation"""
    config = AudioProviderConfig(api_key="test_key")
    provider = OpenAITTSProvider(config=config, model="tts-1-hd")

    text_1k = "a" * 1000
    cost = provider.estimate_cost(text_1k)
    assert cost == 0.030  # $0.030 per 1K chars for tts-1-hd


def test_openai_tts_voices_constant():
    """Test that VOICES constant is correct"""
    expected_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    assert OpenAITTSProvider.VOICES == expected_voices


def test_openai_tts_api_url():
    """Test API URL is correct"""
    assert OpenAITTSProvider.API_URL == "https://api.openai.com/v1/audio/speech"
