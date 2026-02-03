---
name: provider-integration
description: >
  Guidelines for integrating video and audio generation providers.
  Includes API patterns, rate limits, and provider-specific gotchas.
context: fork
agent: spec-implementer
---

# Provider Integration Skill

Apply provider-specific patterns when implementing or debugging provider integrations.

## When to Activate

- Adding a new video/audio/image provider
- Debugging provider API issues
- Optimizing provider usage for cost/quality
- Running `provider onboard` or `provider test`

## Core Instructions

1. Check existing provider implementations in `core/providers/`
2. Follow the base provider interface pattern
3. Apply provider-specific guidelines from reference docs
4. Implement proper error handling and retries
5. Add to provider registry

## Provider Interface

All providers implement:

```python
class BaseProvider(ABC):
    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        pass

    @abstractmethod
    def estimate_cost(self, request: GenerationRequest) -> float:
        pass
```

## Integration Checklist

- [ ] Implement base interface
- [ ] Add to `PROVIDER_REGISTRY`
- [ ] Handle rate limiting
- [ ] Implement cost estimation
- [ ] Add provider-specific tests
- [ ] Document in docs/providers.md
- [ ] Add memory learnings for gotchas

## Return Value

When analyzing provider issues, return:
- `provider_name`: Which provider
- `issue_type`: API, rate_limit, quality, cost
- `recommendation`: Specific fix or workaround
- `reference`: Link to relevant guideline

## Reference Documents

- [luma-guidelines.md](luma-guidelines.md) - Luma AI integration details
- [elevenlabs-guidelines.md](elevenlabs-guidelines.md) - ElevenLabs TTS details
