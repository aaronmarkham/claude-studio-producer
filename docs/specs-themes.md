---
layout: default
title: Specifications by Theme
---

# Specifications by Theme

Organized by architectural concerns to show how different aspects of the system work together.

## 🎬 Core Agent System

The seven agents that implement the multi-agent video production pipeline.

| Agent | Role | Key Innovation |
|-------|------|----------------|
| [ProducerAgent](specs/AGENT_PRODUCER.html) | Budget planning, pilot strategies | Competitive pilot system with dynamic budget allocation |
| [ScriptWriterAgent](specs/AGENT_SCRIPT_WRITER.html) | Scene breakdown from concept | Provider-aware prompt optimization using learnings |
| [VideoGeneratorAgent](specs/AGENT_VIDEO_GENERATOR.html) | Video generation | Pluggable providers with unified interface |
| [AudioGeneratorAgent](specs/AGENT_AUDIO_GENERATOR.html) | TTS narration | Multi-provider TTS (ElevenLabs, OpenAI, Google) |
| [QAVerifierAgent](specs/AGENT_QA_VERIFIER.html) | Vision-based verification | Claude Vision analysis of video frames |
| [CriticAgent](specs/AGENT_CRITIC.html) | Quality evaluation | Gap analysis, learning extraction |
| [EditorAgent](specs/AGENT_EDITOR.html) | EDL creation | Selects best scenes from multiple pilots |

**Design Philosophy:** Each agent has a single, well-defined responsibility. They communicate through structured data, enabling parallel execution and easy testing.

## 🏗️ System Architecture

Foundation and infrastructure specifications.

- [PROJECT_VISION.md](specs/PROJECT_VISION.html) - **Core mission statement**
  - Original "inception" use case
  - Competitive pilot innovation
  - Budget-aware production

- [ARCHITECTURE.md](specs/ARCHITECTURE.html) - System design
  - Data flow diagrams
  - Agent orchestration patterns
  - Integration points

- [STRANDS_INTEGRATION.md](specs/STRANDS_INTEGRATION.html) - Agent orchestration
  - Why Strands SDK
  - Agent initialization
  - Message passing

## 🔌 Provider System

Pluggable providers for video, audio, image, music, and storage.

- [PROVIDERS_COMPLETE.md](specs/PROVIDERS_COMPLETE.html) - Provider architecture
  - Unified interface design
  - Cost estimation
  - Error handling patterns
  - Mock mode for testing

- [LUMA_PROVIDER_SPEC.md](specs/LUMA_PROVIDER_SPEC.html) - Luma AI implementation
  - Text-to-video
  - Image-to-video
  - Extend/interpolate
  - Comprehensive API mapping

- [AUDIO_SYSTEM.md](specs/AUDIO_SYSTEM.html) - Audio production tiers
  - Tier 1: No audio
  - Tier 2: Background music
  - Tier 3+: Full TTS narration

- [SEED_ASSETS.md](specs/SEED_ASSETS.html) - Multi-modal inputs
  - User-provided images/video
  - Brand consistency
  - Voice cloning

**Key Innovation:** Providers are hot-swappable. Same script can be produced with Luma, Runway, or Pika just by changing a CLI flag.

## 🧠 Memory & Learning System

Continuous improvement through learning and knowledge integration.

- [MEMORY_AND_DASHBOARD.md](specs/MEMORY_AND_DASHBOARD.html) - Initial memory design
  - Provider-specific learnings
  - Tips, gotchas, preferences
  - Web dashboard

- [MULTI_TENANT_MEMORY_ARCHITECTURE.md](specs/MULTI_TENANT_MEMORY_ARCHITECTURE.html) - Enterprise multi-tenancy
  - Namespace hierarchy: SESSION → USER → ORG → PLATFORM
  - Security model and isolation
  - Learning promotion based on validation

- [KNOWLEDGE_TO_VIDEO.md](specs/KNOWLEDGE_TO_VIDEO.html) - Knowledge base system
  - Document ingestion (PDF, Markdown)
  - Atomic concept extraction
  - Context-aware video generation

- [DOCUMENT_TO_VIDEO.md](specs/DOCUMENT_TO_VIDEO.html) - Document pipeline
  - PDF atomization
  - Semantic chunking
  - Research paper to video

**Evolution:** Started with simple prompt optimization, evolved to full knowledge management and enterprise memory system.

## 🛠️ Developer Experience

Tools and infrastructure for building and testing.

- [TESTING_AND_PROVIDERS.md](specs/TESTING_AND_PROVIDERS.html) - Testing philosophy
  - Mock providers for testing
  - Integration testing strategies
  - Cost-aware testing

- [DOCKER_DEV_ENVIRONMENT.md](specs/DOCKER_DEV_ENVIRONMENT.html) - Containerized development
  - FFmpeg dependencies
  - Python environment
  - Hot reload

- [CLI_INTROSPECTION.md](specs/CLI_INTROSPECTION.html) - CLI enhancements
  - Package introspection
  - Command structure
  - Configuration management

**Focus:** Make it easy to develop without incurring API costs. Mock mode first, live mode when ready.

---

## View By Timeline

[Timeline View →](specs-timeline.html) | [Evolution Story →](specs-evolution.html)

[← Back to Home](index.html)
