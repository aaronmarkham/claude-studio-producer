## Provider CLI Reference

### Provider Onboarding

The provider onboarding agent helps you integrate new AI providers by analyzing their documentation and generating implementations.

```bash
# Onboard a new provider from documentation
claude-studio provider onboard -n inworld -t audio -d https://docs.inworld.ai/docs/tts/tts

# Onboard from an existing stub file
claude-studio provider onboard -n runway -t video -s core/providers/video/runway_stub.py

# Combine docs + stub for best results
claude-studio provider onboard -n luma -t video \
    -d https://docs.lumalabs.ai/api \
    -s core/providers/video/luma_stub.py

# Resume a previous session
claude-studio provider onboard -n elevenlabs -t audio --resume

# Fully automatic mode (no prompts, runs all tests)
claude-studio provider onboard -n elevenlabs -t audio --resume --auto
```

### Managing Sessions

```bash
# List all saved onboarding sessions
claude-studio provider sessions

# Delete a session
claude-studio provider sessions -d elevenlabs
```

### Testing Providers

```bash
# Test a provider with default settings
claude-studio provider test elevenlabs -t audio --live

# Test with a specific voice (by name - much easier!)
claude-studio provider test elevenlabs -t audio -v Rachel --live

# Test with custom text
claude-studio provider test elevenlabs -t audio -v "Adam" -p "Hello world" --live

# List all available voices
claude-studio provider test elevenlabs -t audio --list-voices
```

Example voice list output:
```
                     Available Voices for elevenlabs
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Name           ┃ Category/Labels                      ┃ Description  ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Rachel         │ accent: american, age: young         │ Calm, warm   │
│ Adam           │ accent: american, age: middle aged   │ Deep, narrat │
│ Bella          │ accent: british, age: young          │ Soft, gentle │
│ ...            │ ...                                  │ ...          │
└────────────────┴──────────────────────────────────────┴──────────────┘

Use -v <name> to test with a specific voice (e.g., -v Rachel)
```

### Provider Analysis

```bash
# Analyze an existing provider implementation
claude-studio provider analyze core/providers/video/luma.py

# Output as JSON
claude-studio provider analyze core/providers/audio/elevenlabs.py --format json

# List all providers and their status
claude-studio provider list

# Filter by type
claude-studio provider list -t audio
```

### Creating Provider Scaffolds

```bash
# Create a new provider stub
claude-studio provider scaffold -n runway -t video

# Specify output path
claude-studio provider scaffold -n mubert -t music -o core/providers/music/mubert.py
```

### Exporting Tests

After onboarding, export generated tests as proper pytest files:

```bash
# Export tests from a completed session
claude-studio provider export-tests elevenlabs

# Specify output directory
claude-studio provider export-tests inworld -o tests/unit

# Regenerate test cases before exporting
claude-studio provider export-tests elevenlabs --regenerate
```

## ElevenLabs TTS Provider

The ElevenLabs provider offers high-quality text-to-speech with multiple voices and advanced controls.

### Quick Usage

```python
from core.providers.audio.elevenlabs import ElevenLabsProvider

# Initialize (uses ELEVENLABS_API_KEY from environment)
provider = ElevenLabsProvider()

# Generate speech
result = await provider.generate_speech(
    text="Hello, this is a test.",
    voice_id="Rachel"  # or use voice ID directly
)

# Save the audio
with open("output.mp3", "wb") as f:
    f.write(result.audio_data)
```

### Voice Control

```python
# With voice settings for fine control
result = await provider.generate_speech(
    text="This is expressive speech.",
    voice_id="Rachel",
    stability=0.5,        # 0-1: lower = more expressive
    similarity_boost=0.8, # 0-1: higher = closer to original voice
    style=0.3,            # 0-1: style variation
    use_speaker_boost=True
)
```

### List Available Voices

```python
voices = await provider.list_voices()
for voice in voices:
    print(f"{voice['name']}: {voice['voice_id']}")
```

### Streaming for Low Latency

```python
async for chunk in provider.generate_speech_stream(
    text="Stream this for lower latency.",
    voice_id="Rachel"
):
    # Process audio chunks as they arrive
    audio_buffer.write(chunk)
```

### Models

| Model | Description | Use Case |
|-------|-------------|----------|
| `eleven_monolingual_v1` | English-only, high quality | Default, best for English |
| `eleven_multilingual_v2` | 29 languages supported | International content |
| `eleven_turbo_v2` | Fastest, optimized latency | Real-time applications |

### Pricing

ElevenLabs charges ~$0.30 per 1K characters. Use `estimate_cost()` to check before generating:

```python
cost = provider.estimate_cost("Your text here...")
print(f"Estimated cost: ${cost:.4f}")
```