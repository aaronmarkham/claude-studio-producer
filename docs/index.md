---
layout: default
title: Home
---

# Claude Studio Producer

A budget-aware multi-agent video production system that uses competitive pilots to optimize quality and cost.

## What Is This?

From a simple idea:
> "A day in the life of a writer making a document about how to use a multi-agent system"

To a production-ready platform with:
- 🎬 **7 specialized agents** (Producer, ScriptWriter, VideoGenerator, QA, Critic, Editor, AudioGenerator)
- 🔌 **Pluggable providers** (Luma, Runway, DALL-E, ElevenLabs, OpenAI, Google TTS)
- 🧠 **Learning system** that improves prompts over time
- 📚 **Knowledge base** for document/research-based video production
- 💰 **Budget-aware** competitive pilot system
- 🔒 **Secure** API key management with OS keychain

## Example Videos

### Coffee Cup - Multi-Provider Pipeline
*DALL-E → Luma: Image generation → Video animation*

<video width="100%" controls>
  <source src="videos/coffee_layer3.mp4" type="video/mp4">
  Your browser does not support the video tag.
</video>

**Production Pipeline:**
1. **DALL-E**: Generated coffee cup image from text prompt
2. **Luma**: Transformed static image into dynamic video with realistic steam and lighting

**Prompt:** "Steam rises gently from the coffee cup, morning light shifts slowly across the wooden table, peaceful cozy atmosphere"

[View more examples →](examples.html)

---

## Documentation

### 📖 Understand the System

- [Design Evolution](specs-evolution.html) - How the system evolved from original vision to current state
- [Specifications by Timeline](specs-timeline.html) - Chronological view of design decisions
- [Specifications by Theme](specs-themes.html) - Organized by architectural concerns
- [Developer Journal](dev-journal.html) - Real development notes and lessons learned

### 🚀 Get Started

- [GitHub Repository](https://github.com/aaronmarkham/claude-studio-producer) - Source code, installation, quickstart
- [Examples](examples.html) - Command examples with real outputs
- [README](https://github.com/aaronmarkham/claude-studio-producer/blob/main/README.md) - Full project overview

### 🏗️ Architecture Deep Dives

**Core Concepts:**
- [Project Vision](specs/PROJECT_VISION.html) - Original "inception" use case and competitive pilot innovation
- [System Architecture](specs/ARCHITECTURE.html) - Data flow and agent orchestration

**Agent System:**
- [Producer Agent](specs/AGENT_PRODUCER.html) - Budget planning and pilot strategies
- [Script Writer](specs/AGENT_SCRIPT_WRITER.html) - Scene breakdown with provider optimization
- [Video Generator](specs/AGENT_VIDEO_GENERATOR.html) - Multi-provider video generation
- [Audio Generator](specs/AGENT_AUDIO_GENERATOR.html) - Multi-provider TTS narration
- [QA Verifier](specs/AGENT_QA_VERIFIER.html) - Claude Vision-based quality checking
- [Critic Agent](specs/AGENT_CRITIC.html) - Evaluation and learning extraction
- [Editor Agent](specs/AGENT_EDITOR.html) - EDL creation from best scenes

**Provider System:**
- [Provider Architecture](specs/PROVIDERS_COMPLETE.html) - Unified interface, cost estimation, mock mode
- [Luma Provider](specs/LUMA_PROVIDER_SPEC.html) - Comprehensive Luma AI implementation
- [Audio System](specs/AUDIO_SYSTEM.html) - TTS production tiers

**Advanced Features:**
- [Memory & Learning](specs/MEMORY_AND_DASHBOARD.html) - Provider-specific continuous improvement
- [Multi-Tenant Memory](specs/MULTI_TENANT_MEMORY_ARCHITECTURE.html) - Enterprise namespace hierarchy
- [Knowledge Base System](specs/KNOWLEDGE_TO_VIDEO.html) - Document/research to video pipeline
- [Document Ingestion](specs/DOCUMENT_TO_VIDEO.html) - PDF atomization and semantic chunking

---

## Quick Commands

```bash
# Production (mock mode - no API costs)
claude-studio produce "concept" --budget 5

# Live mode with real generation
claude-studio produce "concept" --budget 5 --live --provider luma

# Knowledge base workflow
claude-studio kb create "Research" -d "AI papers"
claude-studio kb add "Research" --paper paper.pdf
claude-studio kb produce "Research" -p "Explain transformers" --style educational

# Test providers
claude-studio provider test luma -p "coffee steam rising" -d 5 --live
claude-studio provider test dalle -t image -p "coffee cup on table" --live

# Memory/learning management
claude-studio memory list luma
claude-studio memory add luma tip "Use physical descriptions"

# Secure API key management
claude-studio secrets import .env
claude-studio secrets list
```
