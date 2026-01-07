"""Integration tests for OpenAI TTS provider

These tests make real API calls to OpenAI's TTS service.
They will be skipped if OPENAI_API_KEY is not set in environment.

Run with: pytest tests/integration/test_openai_tts.py -m live_api -v
"""

import os
import pytest
from pathlib import Path
from core.providers.audio.openai_tts import OpenAITTSProvider
from core.providers.base import AudioProviderConfig


# Skip all tests in this file if API key not available
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping live API tests"
)


@pytest.fixture
def openai_config():
    """Create OpenAI TTS provider configuration"""
    api_key = os.getenv("OPENAI_API_KEY")
    return AudioProviderConfig(
        api_key=api_key,
        timeout=30
    )


@pytest.fixture
def openai_provider(openai_config):
    """Create OpenAI TTS provider instance"""
    return OpenAITTSProvider(config=openai_config, model="tts-1")


@pytest.fixture
def openai_hd_provider(openai_config):
    """Create OpenAI TTS HD provider instance"""
    return OpenAITTSProvider(config=openai_config, model="tts-1-hd")


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_basic_generation(openai_provider):
    """Test basic speech generation with OpenAI TTS"""
    text = "Hello, this is a test of OpenAI text to speech."

    result = await openai_provider.generate_speech(
        text=text,
        voice_id="alloy"
    )

    # Check result
    assert result.success is True
    assert result.error_message is None
    assert result.audio_path is not None
    assert result.duration is not None
    assert result.cost is not None
    assert result.cost > 0

    # Check file was created
    audio_file = Path(result.audio_path)
    assert audio_file.exists()
    assert audio_file.stat().st_size > 0

    # Check metadata
    assert result.provider_metadata["model"] == "tts-1"
    assert result.provider_metadata["voice"] == "alloy"
    assert result.format == "mp3"

    # Clean up
    audio_file.unlink()


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_hd_generation(openai_hd_provider):
    """Test HD speech generation"""
    text = "This is a high definition audio test."

    result = await openai_hd_provider.generate_speech(
        text=text,
        voice_id="nova"
    )

    assert result.success is True
    assert result.audio_path is not None

    # Check cost is higher for HD model
    assert result.cost > 0
    assert result.provider_metadata["model"] == "tts-1-hd"

    # Clean up
    Path(result.audio_path).unlink()


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_different_voices(openai_provider):
    """Test generation with different voices"""
    text = "Testing voice variation."

    for voice in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]:
        result = await openai_provider.generate_speech(
            text=text,
            voice_id=voice
        )

        assert result.success is True
        assert result.provider_metadata["voice"] == voice
        assert Path(result.audio_path).exists()

        # Clean up
        Path(result.audio_path).unlink()


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_speed_control(openai_provider):
    """Test speech speed control"""
    text = "This is a speed test."

    # Test slow speed
    result_slow = await openai_provider.generate_speech(
        text=text,
        speed=0.5
    )
    assert result_slow.success is True
    assert result_slow.provider_metadata["speed"] == 0.5

    # Test fast speed
    result_fast = await openai_provider.generate_speech(
        text=text,
        speed=2.0
    )
    assert result_fast.success is True
    assert result_fast.provider_metadata["speed"] == 2.0

    # Duration should be different (slow is longer)
    assert result_slow.duration > result_fast.duration

    # Clean up
    Path(result_slow.audio_path).unlink()
    Path(result_fast.audio_path).unlink()


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_wav_format(openai_provider):
    """Test WAV format output"""
    text = "Testing WAV format."

    result = await openai_provider.generate_speech(
        text=text,
        voice_id="alloy",
        response_format="wav"
    )

    assert result.success is True
    assert result.format == "wav"
    assert result.audio_path.endswith(".wav")
    assert Path(result.audio_path).exists()

    # Clean up
    Path(result.audio_path).unlink()


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_invalid_voice(openai_provider):
    """Test error handling for invalid voice"""
    text = "Testing error handling."

    result = await openai_provider.generate_speech(
        text=text,
        voice_id="invalid_voice"
    )

    assert result.success is False
    assert "Invalid voice" in result.error_message


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_invalid_speed(openai_provider):
    """Test error handling for invalid speed"""
    text = "Testing error handling."

    # Speed too low
    result = await openai_provider.generate_speech(
        text=text,
        speed=0.1
    )
    assert result.success is False
    assert "Speed must be between" in result.error_message

    # Speed too high
    result = await openai_provider.generate_speech(
        text=text,
        speed=5.0
    )
    assert result.success is False
    assert "Speed must be between" in result.error_message


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_list_voices(openai_provider):
    """Test listing available voices"""
    voices = await openai_provider.list_voices()

    assert len(voices) == 6
    voice_ids = [v["id"] for v in voices]
    assert "alloy" in voice_ids
    assert "echo" in voice_ids
    assert "fable" in voice_ids
    assert "onyx" in voice_ids
    assert "nova" in voice_ids
    assert "shimmer" in voice_ids


def test_openai_tts_cost_estimation(openai_provider):
    """Test cost estimation"""
    # Test short text
    short_text = "Hello"
    cost_short = openai_provider.estimate_cost(short_text)
    assert cost_short > 0
    assert cost_short < 0.01  # Should be very cheap

    # Test longer text (1000 characters)
    long_text = "a" * 1000
    cost_long = openai_provider.estimate_cost(long_text)
    assert cost_long == 0.015  # Exactly 1K chars at $0.015/1K


def test_openai_tts_hd_cost_estimation(openai_hd_provider):
    """Test HD model cost estimation"""
    text = "a" * 1000  # 1K characters
    cost = openai_hd_provider.estimate_cost(text)
    assert cost == 0.030  # HD model is $0.030/1K


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_validate_credentials(openai_provider):
    """Test credential validation"""
    is_valid = await openai_provider.validate_credentials()
    assert is_valid is True


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_validate_credentials_invalid():
    """Test credential validation with invalid key"""
    config = AudioProviderConfig(
        api_key="invalid_key_12345",
        timeout=10
    )
    provider = OpenAITTSProvider(config=config)

    is_valid = await provider.validate_credentials()
    assert is_valid is False


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_long_text(openai_provider):
    """Test generation with longer text"""
    # Generate a paragraph of text
    text = """
    This is a longer text to test the OpenAI TTS API with more content.
    It includes multiple sentences and should generate a longer audio file.
    The duration estimation should be more accurate with longer text.
    This helps verify that the provider works correctly with realistic use cases.
    """

    result = await openai_provider.generate_speech(
        text=text,
        voice_id="nova"
    )

    assert result.success is True
    assert result.duration > 5.0  # Should be several seconds
    assert result.provider_metadata["word_count"] > 20

    # Clean up
    Path(result.audio_path).unlink()


@pytest.mark.live_api
@pytest.mark.asyncio
async def test_openai_tts_file_creation_in_artifacts(openai_provider):
    """Test that files are created in the correct directory"""
    text = "Testing file location."

    result = await openai_provider.generate_speech(
        text=text,
        voice_id="alloy"
    )

    assert result.success is True

    # Check file is in artifacts/audio directory
    audio_path = Path(result.audio_path)
    assert "artifacts" in str(audio_path)
    assert "audio" in str(audio_path)

    # Clean up
    audio_path.unlink()
