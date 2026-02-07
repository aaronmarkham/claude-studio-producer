---
layout: default
title: Developer Journal
---

# Developer Journal

A chronological record of development decisions, discoveries, and lessons learned while building Claude Studio Producer.

[View full developer notes →](https://github.com/aaronmarkham/claude-studio-producer/blob/main/docs/dev_notes.md)

## Recent Updates

### Feb 6, 2026 (evening) - Figure-Aware Script Generation

Fixed a key architectural issue: training now knows about figures before generating scripts.

**The Problem**: Scripts were generated without knowing what figures existed, then we tried to match figures afterward via keyword guessing.

**The Solution**:
- Training extracts figures from the document graph
- Figure captions/descriptions are passed to Claude in the prompt
- Scripts now explicitly reference figures: "As shown in Figure 6..."
- Video production does exact matching instead of guessing

Also documented the `kb inspect` command - shows beautiful quality reports:

```bash
claude-studio kb inspect my-project --quality

# Output shows atom distribution with bar charts:
# equation    █████░░░░░   44 (26%)
# paragraph   ████░░░░░░   38 (23%)
# figure      ███░░░░░░░   26 (16%)
```

### Feb 6, 2026 - Training Pipeline & Video Production Integration

Big milestone: the podcast training pipeline and video production workflow are fully integrated!

**Training Pipeline** (`claude-studio training run`):
- Transcribes reference podcasts using Whisper
- Classifies segments (INTRO, BACKGROUND, METHODOLOGY, KEY_FINDING, etc.)
- Extracts style profiles for improved script generation

**Video Production** (`claude-studio produce-video`):
- Takes training output and produces explainer videos
- Budget tier system (micro=$0 to full=$15+)
- Scene importance scoring allocates images to high-impact moments
- KB figures from PDFs appear in videos synced to narration

```bash
claude-studio produce-video -t trial_000 --show-tiers
claude-studio produce-video -t trial_000 --budget medium --kb my-project --live
```

### Jan 30, 2026 - Security Hardening

Read some alarming posts about Clawdbot, so did a quick security check. Added `__repr__` to Config classes to prevent API key leaks in debug outputs.

Added keychain import feature:

```bash
claude-studio secrets import .env
```

This imports all API keys from `.env` into your OS keychain, allowing secure storage without environment variables.

### Jan 28, 2026 - DALL-E Provider

Stayed focused on core mission instead of getting distracted by Remotion graphics (saving that for later).

Successfully onboarded DALL-E using the provider onboarding agent:

```bash
claude-studio provider onboard -n dalle -t image --docs-url https://platform.openai.com/docs/guides/images
```

The system now supports:
- DALL-E 3 (high quality, 1024x1024)
- DALL-E 2 (faster, cheaper, multiple sizes)

This enables the **DALL-E → Runway** pipeline for image-to-video generation.

### Jan 26, 2026 - Multi-Provider Pipelines

Completed the pipeline capability to chain providers:
1. DALL-E generates seed image from text
2. Runway transforms image to video

This is a key architectural milestone - providers can now feed into each other.

### Jan 23, 2026 - Knowledge Base System

Major feature: Document-to-Video pipeline

- PDF ingestion with PyMuPDF
- Atomic concept extraction from papers/docs
- Knowledge base management CLI
- Generate videos from research papers or documentation

Example workflow:
```bash
claude-studio kb create "AI Research" -d "Latest papers on multi-agent systems"
claude-studio kb add "AI Research" --paper paper.pdf
claude-studio kb produce "AI Research" -p "Explain transformer architecture" --style educational
```

### Jan 20, 2026 - Multi-Tenant Memory

Upgraded memory system to support multi-tenant hierarchy:
- SESSION → USER → ORG → PLATFORM
- Namespace isolation and security model
- Learning promotion/demotion based on validation
- Production-ready with Bedrock AgentCore

### Jan 8, 2026 - Memory & Dashboard

- Provider learning system (tips, gotchas, preferences)
- Memory namespace per provider
- Web dashboard for viewing runs and QA scores

### Jan 7-8, 2026 - Luma Provider Implementation

First real video provider integration:
- Comprehensive Luma API spec
- Text-to-video without seed images
- Image-to-video with start frames
- Extend/interpolate capabilities
- Aspect ratio mapping
- Full error handling

### Jan 7, 2026 - Foundation Sprint

Late night/early morning sprint creating all foundation specs:
- All 7 agent specifications
- System architecture
- Strands integration
- Provider system design
- Audio system tiers
- Testing philosophy
- Docker dev environment

### Jan 6, 2026 - Agent Architecture

Initial agent system design:
- ScriptWriter, VideoGenerator, QAVerifier
- Editor, Producer, Critic agents
- Budget-aware competitive pilot system

---

## Jan 9, 2026 - What Is This Even For?

**The Vision**

This project demonstrates:
1. What you can do quickly with Claude
2. How to design and implement a working multi-agent workflow
3. Using learning/memory systems
4. Using rewards and feedback
5. Having fun!

**The Workflow**

A virtual studio where:
- **Producer** takes your budget and pitch, crafts pilots based on what works and what you can afford
- **Script Writer** creates scenes knowing the provider's capabilities and constraints
- **Video Generator** shoots scenes (parallelizable across providers)
- **QA Agents** perform technical review (parallelizable)
- **Critic** assesses overall quality and makes recommendations
- **Editor** creates Edit Decision List (EDL) for final candidate videos

**Studio Reinforcement Learning (StudioRL)**

The feedback loop stores learnings in memory for the producer and script writer to leverage. The budget system keeps costs under control, allowing re-runs on promising pilots within budget constraints.

### Are We Having Fun Yet?

![make-it-rain-coffee](screenshots/make-it-rain-coffee.gif)

**Prompt:**
*A 15-second story of a developer having a breakthrough: Scene 1 - Wide shot of developer at desk in cozy home office at night, hunched over laptop, frustrated expression, warm desk lamp lighting. Scene 2 - They lean back with a satisfied smile, stretch arms up in victory celebration, coffee cup visible nearby, cinematic triumph moment.*

**Result:** Make it rain coffee...!

Sometimes the AI interprets your vision in unexpected ways. This is part of why we have the QA and Critic agents - to catch these creative interpretations and decide whether they're happy accidents or need revision.

---

[← Back to Home](index.html) | [View Specifications →](specs-timeline.html) | [Full Developer Notes →](https://github.com/aaronmarkham/claude-studio-producer/blob/main/docs/dev_notes.md)
