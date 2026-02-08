---
layout: default
title: Developer Journal
---

# Developer Journal

A chronological record of development decisions, discoveries, and lessons learned while building Claude Studio Producer.

[View full developer notes →](https://github.com/aaronmarkham/claude-studio-producer/blob/main/docs/dev_notes.md)

<img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> = Aaron &nbsp;&nbsp; <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> = Claude

## Recent Updates

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 7, 2026 - Content Model Expansion

Extended StructuredScript with content-agnostic vocabulary and source attribution for broader use cases beyond scientific podcasts.

**Content-Agnostic Intent Vocabulary**: Replaced paper-specific intents (METHODOLOGY, KEY_FINDING, etc.) with 19 universal intents that work across content types:
- Structural: INTRO, TRANSITION, RECAP, OUTRO
- Exposition: CONTEXT, EXPLANATION, DEFINITION, NARRATIVE
- Evidence: CLAIM, EVIDENCE, DATA_WALKTHROUGH, FIGURE_REFERENCE
- Analysis: ANALYSIS, COMPARISON, COUNTERPOINT, SYNTHESIS
- Editorial: COMMENTARY, QUESTION, SPECULATION

**Source Attribution**: New `SourceType` (PAPER, NEWS, DATASET, GOVERNMENT, TRANSCRIPT, NOTE, ARTIFACT, URL) and `SourceAttribution` models track content provenance with confidence scores.

**Variant/Perspective Support**: `perspective` field on segments and scripts enables bias analysis workflows (left/right news variants sharing same source attributions).

**Backward Compatibility**: Intent mapping preserves existing scripts:
- BACKGROUND → CONTEXT
- METHODOLOGY → EXPLANATION
- KEY_FINDING → CLAIM
- FIGURE_WALKTHROUGH → FIGURE_REFERENCE
- DATA_DISCUSSION → DATA_WALKTHROUGH

This enables news comparison, multi-source synthesis, and policy analysis workflows while maintaining compatibility with the existing podcast training pipeline.

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 7, 2026 - DoP and Unified Production (Phase 4)

Implemented Phase 4 of the Unified Production Architecture: the Director of Photography (DoP) module and ContentLibrarian integration.

**DoP Module** (`core/dop.py`):
- Assigns visual display modes to script segments (figure_sync, dall_e, carry_forward, text_only)
- Respects budget tier ratios for proportional image allocation
- Prioritizes segments by importance score for DALL-E generation
- Links to existing approved assets in ContentLibrary
- Generates visual direction hints for image prompts
- 100% deterministic - no LLM calls needed

**Integration** (`cli/produce_video.py`):
- ContentLibrarian now wired into video production pipeline
- StructuredScript is the source of truth when available
- DoP replaces manual budget allocation logic
- Visual planning now shows figure_sync, dall_e, carry_forward, and text_only modes
- Asset reuse across runs - approved images aren't regenerated

**Example Output**:
```
DoP visual assignment:
  figure_sync: 3 segments (KB figures)
  dall_e: 5 segments (new generation needed)
  carry_forward: 7 segments (reuse previous)
  text_only: 2 segments (transitions)

Estimated cost: $0.40 (5 DALL-E images)
```

The pipeline is now unified - both `produce` and `produce-video` commands share the same StructuredScript and ContentLibrary data layer. This enables incremental regeneration and asset reuse across runs.

**Test Coverage**: 116 tests passing (81 unit + 35 integration) covering all phases of the unified architecture, provider integrations, and end-to-end workflows.

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 7, 2026 - Training Outputs StructuredScript (Phase 3)

Training pipeline now outputs structured scripts alongside flat text files.

**What Changed**:
- After generating `_script.txt`, trainer parses it with `StructuredScript.from_script_text()`
- Enriches figure inventory with captions from the document graph
- Saves `{pair_id}_structured_script.json` per training pair

This bridges training and production: video production can now load structured scripts directly instead of re-parsing flat text. Figure references in scripts are pre-resolved with full metadata.

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 7, 2026 - Unified Production Architecture (Phase 1)

Implemented Phase 1 of the UNIFIED_PRODUCTION_ARCHITECTURE.md spec, establishing new data models as the foundation for the unified pipeline.

**StructuredScript Model**: Single source of truth replacing flat `_script.txt` files. The `from_script_text()` parser extracts Figure N references and section boundaries from existing scripts, enabling structured access to script content.

**ContentLibrary Model**: Persistent asset registry with approval tracking. Includes `from_asset_manifest_v1()` for migrating existing asset manifests to the new format. Tracks image/audio assets with generation status and approval state.

All 55 unit tests passing.

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 7, 2026 - Proportional Budgets & Audio Source Fix

Fixed architectural issues in the video production pipeline:

**1. Proportional Budget Tiers**

Previously, budget tiers used absolute image counts (e.g., "medium = 40 images"). This caused inconsistent quality when testing with scene subsets.

Now tiers use **ratios**:
- `low`: 10% of scenes get images
- `medium`: 27% of scenes get images
- `high`: 55% of scenes get images
- `full`: 100% of scenes get images

This ensures consistent quality across runs. Testing 5 scenes with medium tier now produces ~1 image (not 5), matching what would happen proportionally in a full production.

**2. Audio Uses Generated Script**

Audio was incorrectly generated from the original Whisper transcription ("Welcome to Journal Club...") instead of the new script ("Welcome back to another deep dive...").

Fixed: Audio now comes from `_script.txt` paragraphs, not `aligned_segments` from the original transcription.

**3. Audio Respects --limit Parameter**

Audio was generating all 45 paragraphs even with `--limit 5`. Now slices paragraphs proportionally to match scene range.

**4. Clear Visual Source Display**

Scene list now distinguishes between:
- `DALL-E` - gets unique generated image
- `shared` - shares image with primary scene
- `text only` - no image generated

```bash
# Output now shows which scene gets the image:
#  UAV positioning       intro  DALL-E     Ken Burns
#  multi-sensor info     intro  shared     Ken Burns
#  Kalman filter         intro  shared     Ken Burns
```

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 6, 2026 (late evening) - Scene-by-Scene Audio Generation

Added audio generation directly to `produce-video`, fixing a key architectural issue.

**The Problem**: Training was generating a full script, then trying to send it all to ElevenLabs at once. This hit character limits and was wasteful - training doesn't need audio, only production does.

**The Solution**:
- Training generates scripts only (no audio)
- `produce-video` generates audio scene-by-scene during production
- Each scene gets its own `.mp3` file
- Avoids ElevenLabs character limits by chunking naturally
- Asset manifest tracks `image_path` + `audio_path` per scene

```bash
# Produce video with scene-by-scene audio (default: enabled)
claude-studio produce-video -t trial_000 --budget medium --live --voice lily

# Or specify a different voice
claude-studio produce-video -t trial_000 --budget medium --live --voice rachel
```

Output structure:
```
artifacts/video_production/20260206_204449/
├── images/
│   ├── scene_000.png
│   └── scene_001.png
├── audio/
│   ├── scene_000.mp3
│   └── scene_001.mp3
├── visual_plans.json
└── asset_manifest.json  # Links images + audio per scene
```

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 6, 2026 (evening) - Figure-Aware Script Generation

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

### <img src="https://avatars.githubusercontent.com/u/81847?s=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Feb 6, 2026 - Training Pipeline & Video Production Integration

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

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 30, 2026 - Security Hardening

Read some alarming posts about Clawdbot, so did a quick security check. Added `__repr__` to Config classes to prevent API key leaks in debug outputs.

Added keychain import feature:

```bash
claude-studio secrets import .env
```

This imports all API keys from `.env` into your OS keychain, allowing secure storage without environment variables.

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 28, 2026 - DALL-E Provider

Stayed focused on core mission instead of getting distracted by Remotion graphics (saving that for later).

Successfully onboarded DALL-E using the provider onboarding agent:

```bash
claude-studio provider onboard -n dalle -t image --docs-url https://platform.openai.com/docs/guides/images
```

The system now supports:
- DALL-E 3 (high quality, 1024x1024)
- DALL-E 2 (faster, cheaper, multiple sizes)

This enables the **DALL-E → Runway** pipeline for image-to-video generation.

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 26, 2026 - Multi-Provider Pipelines

Completed the pipeline capability to chain providers:
1. DALL-E generates seed image from text
2. Runway transforms image to video

This is a key architectural milestone - providers can now feed into each other.

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 23, 2026 - Knowledge Base System

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

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 20, 2026 - Multi-Tenant Memory

Upgraded memory system to support multi-tenant hierarchy:
- SESSION → USER → ORG → PLATFORM
- Namespace isolation and security model
- Learning promotion/demotion based on validation
- Production-ready with Bedrock AgentCore

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 8, 2026 - Memory & Dashboard

- Provider learning system (tips, gotchas, preferences)
- Memory namespace per provider
- Web dashboard for viewing runs and QA scores

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 7-8, 2026 - Luma Provider Implementation

First real video provider integration:
- Comprehensive Luma API spec
- Text-to-video without seed images
- Image-to-video with start frames
- Extend/interpolate capabilities
- Aspect ratio mapping
- Full error handling

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 7, 2026 - Foundation Sprint

Late night/early morning sprint creating all foundation specs:
- All 7 agent specifications
- System architecture
- Strands integration
- Provider system design
- Audio system tiers
- Testing philosophy
- Docker dev environment

### <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 6, 2026 - Agent Architecture

Initial agent system design:
- ScriptWriter, VideoGenerator, QAVerifier
- Editor, Producer, Critic agents
- Budget-aware competitive pilot system

---

## <img src="https://github.com/aaronmarkham.png?size=20" width="20" height="20" style="border-radius:50%; vertical-align:middle"/> Jan 9, 2026 - What Is This Even For?

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
