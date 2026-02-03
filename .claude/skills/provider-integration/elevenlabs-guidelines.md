# ElevenLabs TTS Integration Guidelines

Reference document for ElevenLabs Text-to-Speech API integration.

## API Overview

- **Endpoint**: `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
- **Auth**: `xi-api-key` header
- **Rate Limit**: Varies by tier (10-100 concurrent)
- **Max Text**: 5000 characters per request

## Voice Selection

### Pre-made Voices
```python
VOICES = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",  # Calm, professional
    "adam": "pNInz6obpgDQGcFmaJgB",     # Deep, authoritative
    "bella": "EXAVITQu4vr4xnSDxMaL",    # Warm, conversational
}
```

### Voice Cloning
- Requires 1+ minute of clean audio
- Better results with 3-5 minutes
- Must comply with consent requirements

## Request Patterns

### Standard TTS
```python
{
    "text": "Your text here",
    "model_id": "eleven_multilingual_v2",
    "voice_settings": {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True
    }
}
```

### Streaming
```python
async with client.stream(
    "POST",
    f"/text-to-speech/{voice_id}/stream",
    json=payload
) as response:
    async for chunk in response.aiter_bytes():
        yield chunk
```

## Voice Settings

| Setting | Range | Effect |
|---------|-------|--------|
| stability | 0-1 | Higher = more consistent, lower = more expressive |
| similarity_boost | 0-1 | Higher = closer to original voice |
| style | 0-1 | Higher = more expressive (v2 only) |
| speaker_boost | bool | Enhances clarity |

### Recommended Settings by Use Case

**Narration**: stability=0.65, similarity=0.75, style=0.3
**Podcast**: stability=0.5, similarity=0.8, style=0.5
**Dramatic**: stability=0.3, similarity=0.75, style=0.8

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| 401 | Invalid API key | Check key configuration |
| 422 | Invalid voice_id | Verify voice exists |
| 429 | Rate/quota limit | Backoff or upgrade tier |
| 400 | Text too long | Chunk into <5000 char segments |

## Cost Optimization

- Characters are charged, not audio duration
- Punctuation counts as characters
- Use `eleven_turbo_v2` for lower cost (slightly lower quality)
- Cache common phrases

## Audio Quality

### Recommended Output Settings
- Format: MP3 320kbps or WAV
- Sample rate: 44.1kHz
- Normalize: -14 LUFS for YouTube

### Known Issues

1. **Number pronunciation**: Spell out numbers for consistency
2. **Acronyms**: Add periods (U.S.A.) or spell phonetically
3. **Emphasis**: Use CAPS sparingly, prefer italics markers
4. **Pacing**: Add "..." for natural pauses

## SSML Support

Limited SSML via `<break>` tags:
```
"This is a sentence.<break time=\"1s\"/> This comes after a pause."
```
