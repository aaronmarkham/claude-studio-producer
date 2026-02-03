# Luma AI Integration Guidelines

Reference document for Luma Dream Machine API integration.

## API Overview

- **Endpoint**: `https://api.lumalabs.ai/dream-machine/v1/generations`
- **Auth**: Bearer token in header
- **Rate Limit**: 10 concurrent generations (standard tier)
- **Max Duration**: 5 seconds per generation

## Request Patterns

### Text-to-Video
```python
{
    "prompt": "descriptive scene prompt",
    "aspect_ratio": "16:9",  # or "9:16", "1:1"
    "loop": False
}
```

### Image-to-Video
```python
{
    "prompt": "motion description",
    "keyframes": {
        "frame0": {
            "type": "image",
            "url": "https://..."
        }
    }
}
```

### Video Extension
```python
{
    "prompt": "continuation prompt",
    "keyframes": {
        "frame0": {
            "type": "generation",
            "id": "previous-generation-id"
        }
    }
}
```

## Prompt Best Practices

### Do
- Use physical, cinematic descriptions
- Specify camera movement explicitly
- Include lighting and atmosphere details
- Describe motion in present continuous tense

### Don't
- Use abstract concepts without visual grounding
- Request text overlays (poor quality)
- Expect consistent faces across generations
- Use negative prompts (not supported)

### Example Prompts

**Good**: "A golden retriever running through shallow ocean waves at sunset, water splashing, warm orange light, slow motion, tracking shot following the dog"

**Bad**: "A happy dog at the beach feeling free and joyful"

## Polling Pattern

```python
while True:
    response = await client.get(f"/generations/{id}")
    if response.state == "completed":
        return response.assets.video
    elif response.state == "failed":
        raise GenerationError(response.failure_reason)
    await asyncio.sleep(5)
```

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| 429 | Rate limit | Exponential backoff, max 3 retries |
| 400 | Invalid prompt | Check for banned content terms |
| 500 | Server error | Retry after 30s |
| timeout | Long queue | Increase poll timeout to 5min |

## Cost Considerations

- ~$0.20-0.40 per 5s generation
- Failed generations may still be charged
- Loop generations cost same as non-loop
- Extensions count as full generations

## Quality Gotchas

1. **Face consistency**: Faces change between generations - avoid face-focused content
2. **Text rendering**: Luma cannot reliably render text
3. **Physics**: Complex physics (water, fire) work well; mechanical motion less so
4. **Camera limits**: Extreme camera moves may cause artifacts
