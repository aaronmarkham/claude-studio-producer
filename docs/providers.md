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

## DALL-E Image Provider

The DALL-E provider generates images using OpenAI's DALL-E 2 and DALL-E 3 models. Useful for seed images, thumbnails, and storyboards.

### Quick Usage

```python
from core.providers.image.dalle import DalleProvider

# Initialize (uses OPENAI_API_KEY from environment)
provider = DalleProvider()

# Generate image
result = await provider.generate_image(
    prompt="A serene mountain landscape at sunset",
    size="1024x1024"
)

# Get the image URL (expires in 60 minutes)
print(result.image_url)

# Or download directly
result = await provider.generate_image(
    prompt="A red apple on white background",
    size="1024x1024",
    download=True  # Saves to artifacts/images/
)
print(result.image_path)
```

### DALL-E 3 Options

```python
# DALL-E 3 with quality and style controls
result = await provider.generate_image(
    prompt="A futuristic cityscape",
    size="1792x1024",      # landscape
    model="dall-e-3",
    quality="hd",          # standard or hd (2x cost)
    style="vivid"          # vivid (dramatic) or natural (realistic)
)

# Check the revised prompt (DALL-E 3 auto-expands prompts)
print(result.provider_metadata["revised_prompt"])
```

### Size Presets

| Preset | DALL-E 3 | DALL-E 2 |
|--------|----------|----------|
| `square` | 1024x1024 | 1024x1024 |
| `portrait` | 1024x1792 | - |
| `landscape` | 1792x1024 | - |

```python
# Use preset names
result = await provider.generate_image(prompt="...", size="landscape")
```

### Models

| Model | Capabilities | Limitations |
|-------|--------------|-------------|
| `dall-e-3` | Best quality, style/quality controls, prompt revision | n=1 only, no edits |
| `dall-e-2` | Edits, variations, batch (n>1) | Lower quality, 1024x1024 max |

### Pricing

| Model | Size | Quality | Cost |
|-------|------|---------|------|
| DALL-E 3 | 1024x1024 | standard | $0.04 |
| DALL-E 3 | 1024x1024 | hd | $0.08 |
| DALL-E 3 | 1792x1024 | standard | $0.08 |
| DALL-E 3 | 1792x1024 | hd | $0.12 |
| DALL-E 2 | 1024x1024 | - | $0.02 |
| DALL-E 2 | 512x512 | - | $0.018 |
| DALL-E 2 | 256x256 | - | $0.016 |

```python
cost = provider.estimate_cost("1024x1024", model="dall-e-3", quality="hd")
print(f"Estimated cost: ${cost:.4f}")
```

### Tips and Gotchas

**Tips:**
- DALL-E 3 revises prompts for safety/quality - check `revised_prompt` in response
- Use `natural` style for realistic images, `vivid` for dramatic/artistic
- Use `hd` quality only when fine details matter (costs 2x)
- Be specific and descriptive in prompts for best results

**Gotchas:**
- DALL-E 3 only supports n=1 (single image per request)
- Image URLs expire after 60 minutes - download if needed
- Image edits and variations are DALL-E 2 only
- Content policy violations return 400 errors