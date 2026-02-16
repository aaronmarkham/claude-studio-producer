# Developer Notes

### What's Working Now

- **Content generation** with Luma AI (image-to-video), ElevenLabs (text to speech), and Runway (implemented); several other image, text to audio, music, and storage providers are stubbed out
- **Vision-based QA** using Claude to analyze extracted video frames
- **Provider onboarding and learning system** that improves prompts and production quality over time
- **Web dashboard** to view runs, preview videos, and see QA scores
- **CLI tool** with live progress and detailed feedback
- **Multi-tenant memory** using Strands and Bedrock AgentCore
- **Podcast training pipeline** - ML-style iterative improvement for podcast generation quality
- **Transcript-led video production** - Budget-aware visual generation from training outputs
- **Budget tier system** - micro/low/medium/high/full tiers for controlling image generation costs


### Feb 15, 2026 - YouTube Publishing

I spent the last week playing with OpenClaw and even had my new agent, Lilit, start working with the codebase. Some of the most recent updates like getting the OpenTTS provider working and the YouTube publishing working was courtesy of Lilit.

I think the most interesting aspect of this was able to teach Lilit to use this studio CLI, and now I can just ask for a podcast about x topic and I'll get one. 

Yesterday I wanted to learn about the latest advances in memory, and she provided two papers from 2026. I selected said make a podcast for each. One was very long, 17 pages, and something was causing the subagent to fail extracting the pdf, so she made a [github issue about it](https://github.com/aaronmarkham/claude-studio-producer/issues/10). I probably need to figure out how to have that agent get a proper identity like when Claude Code makes an update and you see that we committed together, rather that it coming up as an issue from me.

Anyways, the [second paper about "FadeMem"]( https://arxiv.org/abs/2601.18642), had no such issue. Here's the video:
https://youtu.be/eToEeH0yz4o

<iframe width="560" height="315" src="https://www.youtube.com/embed/eToEeH0yz4o" frameborder="0" allowfullscreen></iframe>

This video is a culmination of several advances:
1. karaoke style text renderings
2. more selective image inputs (oh yeah, we have a new wikimedia provider!)
3. knowledge base has better alignment with the content and we're also timeline aware so that the spoken word of the script is better about trigger relevant visuals
4. there's probably more, but I can't recall right now because it has been a pretty intense week!

I'll see if Lilit cares to chime in on that. No doubt she will.

Oh! Classic burying the lede: you can just have OpenClaw (or your agent of choice) drive this studio and generate videos from w/e source content you want. The CLI is so feature rich that they can tinker with it and make a wide variety of content about your source material, so my focus on science papers was purely self-limiting on my laser focus. GLHF!

### Feb 9, 2026 - Content-Aware Document Classification

The KB ingestion pipeline was treating all documents identically — scientific papers, news articles, and blog posts all got the same LLM prompts and the same topic extraction logic. This caused metadata pollution: author affiliations, university names, and journal/conference names were leaking into `key_themes`.

**ContentClassifier** (`core/content_classifier.py`):
- Runs *before* the LLM, using heuristics on raw PyMuPDF extraction (font sizes, positions, text patterns)
- Detects document type (scientific paper, news article, blog post, dataset readme, etc.)
- Identifies structural zones: front matter, body, back matter, biographical, boilerplate
- Produces a `ContentProfile` that the ingestor uses to guide LLM prompts

**Zone-Aware Topic Filtering**:
- Blocks in metadata zones (affiliations, author bios) get `topics = []` — no theme extraction
- `is_theme_candidate()` filter catches institutional names, journal/conference venues
- Integrated into both LLM and mock analysis paths, plus KB topic quality checks

**Chunked LLM Classification**:
- Large documents (100+ blocks) were hitting output token limits, producing truncated JSON
- Now sends blocks in batches of ~30, each getting a complete JSON response
- Added `_repair_truncated_json()` to JSONExtractor as an additional safety net

**New Data Models** (`core/models/document.py`):
- `DocumentType` enum (scientific_paper, news_article, blog_post, etc.)
- `ZoneRole` enum (front_matter, body, back_matter, biographical, boilerplate)
- `DocumentZone` dataclass for contiguous regions
- `ContentProfile` with `is_metadata_block()` and `get_zone_for_block()` helpers

### Feb 7, 2026 - Unified Production Architecture (Phases 1-4)

Implemented all four phases of the Unified Production Architecture spec, which unifies the original agent pipeline and the transcript-led video production pipeline.

**Phase 1: Data Models**

Created `core/models/structured_script.py` and `core/models/content_library.py`:

- `StructuredScript` — single source of truth for scripts with segments, figure refs, and visual direction
- `StructuredScript.from_script_text()` parses "Figure N" references from flat `_script.txt` files
- `ScriptSegment` has intent classification (INTRO, KEY_FINDING, METHODOLOGY, etc.)
- `ContentLibrary` tracks all generated assets with approval status (DRAFT, APPROVED, REJECTED)
- `AssetRecord` stores metadata for audio, images, figures, and videos

**Phase 2: ContentLibrarian Module**

Created `core/content_librarian.py`:

- `ContentLibrarian.build_assembly_manifest()` creates figure sync points from structured scripts
- `get_generation_plan()` identifies which segments need new assets (skips approved ones)
- Asset registration methods for audio, images, and KB figures
- Enables asset reuse across runs — no more regenerating approved content

**Phase 3: Training Pipeline Integration**

Training pipeline now outputs structured scripts alongside flat text files:
- After generating `_script.txt`, trainer parses it with `StructuredScript.from_script_text()`
- Enriches figure inventory with captions from the document graph
- Saves `{pair_id}_structured_script.json` per training pair

**Phase 4: Director of Photography (DoP) Module**

Created `core/dop.py` - deterministic visual planning module:

**Key Functions**:
- `assign_visuals()` - Main DoP function that assigns display modes to all segments
- `get_visual_plan_summary()` - Returns counts of each display mode
- `estimate_visual_cost()` - Calculates DALL-E generation costs
- `get_generation_list()` - Lists segments needing DALL-E generation
- `get_figure_sync_list()` - Lists segments syncing to KB figures

**Visual Assignment Logic**:
1. **Phase 1**: Assign `figure_sync` to segments with figure references (always prioritized)
2. **Phase 2**: If micro tier, assign `text_only` to everything else
3. **Phase 3**: Calculate DALL-E budget based on tier ratio (e.g., medium = 27% of segments)
4. **Phase 4**: Score remaining segments by importance, assign `dall_e` to top N
5. **Phase 5**: Assign `carry_forward` to remaining segments (reuse previous image)
6. **Phase 6**: Generate visual direction hints for dall_e and figure_sync segments

**Display Modes**:
- `figure_sync` - Show KB figure from document (e.g., charts from PDF)
- `dall_e` - Generate new image via DALL-E
- `carry_forward` - Reuse previous segment's image with Ken Burns effect
- `text_only` - Just text overlay on background (transitions, micro tier)

**Integration with produce-video**:
- ContentLibrarian now wired into the video production pipeline
- StructuredScript is the source of truth when available (replaces flat text parsing)
- DoP replaces manual budget allocation logic in `cli/produce_video.py`
- Visual planning shows figure_sync, dall_e, carry_forward, text_only modes
- Asset reuse: approved images aren't regenerated (checks ContentLibrary first)

**Intent-Based Visual Direction**:
DoP generates visual guidance based on segment intent:
- INTRO: Abstract visualization, minimalist design
- METHODOLOGY: Technical diagrams, system flowcharts
- KEY_FINDING: Data visualization with vivid accent colors
- FIGURE_WALKTHROUGH: Frame sync with specific figure, annotations
- COMPARISON: Side-by-side visualizations

**Implementation Details**:
- Budget tier ratios applied ONLY to DALL-E images (figures don't count toward budget)
- Transitions always get `text_only` (never waste images on transitions)
- Segments with approved assets are prioritized for DALL-E assignment (reuse)
- Importance scores range 0.0-1.0; scores ≥0.8 get "compelling composition" guidance
- Ken Burns effect suggested for segments with importance ≥0.6

**Test coverage**: 116 tests passing (81 unit + 35 integration) covering serialization, parsing, asset registration, manifest building, DoP visual assignment logic, provider integrations, and end-to-end production workflows.

The key insight: both pipelines now share the same data layer. The original `produce` command (ScriptWriter → VideoGenerator → QA → Editor) and the `produce-video` command (Training → DoP → Audio/Visual Producer → Assembler) can read/write the same StructuredScript and ContentLibrary formats. This unblocks figure sync in video assembly and enables incremental regeneration.

### Feb 6, 2026 (late evening) - Scene-by-Scene Audio Generation

Another architectural fix: moved audio generation from training to production, with scene-by-scene chunking.

**Previous approach (broken)**:
- Training generated a full script and tried to send it all to ElevenLabs
- Hit character limits on long scripts (~5000 chars)
- Generated audio during training, which is wasteful for iteration

**New approach**:
- Training generates scripts only (no audio calls)
- `produce-video` generates audio during production
- Each scene gets its own `.mp3` file via `generate_scene_audio()`
- Natural chunking avoids ElevenLabs limits
- Asset manifest tracks both `image_path` and `audio_path` per scene

CLI options:
```bash
claude-studio produce-video -t trial_000 --budget medium --live --voice lily
claude-studio produce-video -t trial_000 --live --no-audio  # Skip audio if needed
```

Voice mapping is handled automatically (lily → pFZP5JQG7iQjIQuC4Bku). Cost is ~$0.08 for 5 scenes with ~263 total characters.

Output manifest now includes:
```json
{
  "scene_id": "scene_000",
  "image_path": "images/scene_000.png",
  "audio_path": "audio/scene_000.mp3"
}
```

### Feb 6, 2026 (evening) - Figure-Aware Script Generation

Fixed a fundamental design flaw in the training → video production pipeline. Previously:
- Training generated scripts without knowing what figures existed in the PDF
- `produce-video` tried to retrofit figures via keyword matching ("methodology" → Figure 3?)

Now:
- Training extracts figures from the KB/document graph
- Figures are passed to Claude in the script generation prompt
- Claude writes explicit figure references ("As shown in Figure 6...")
- `produce-video` does exact matching on "Figure 6" instead of guessing

Also discovered and documented the `kb inspect` command with quality reports:
```bash
claude-studio kb inspect my-project --quality
# Shows atom type distribution, topic/entity coverage, key themes
```

The output is beautifully formatted with bar charts showing distribution of equations (26%), paragraphs (23%), citations (20%), figures (16%), etc. Great for understanding what was extracted from a PDF.

### Feb 6, 2026

Big milestone: the podcast training pipeline and video production workflow are now fully integrated!

**Training Pipeline** (`claude-studio training run`):
- Transcribes reference podcasts using Whisper
- Classifies segments into types (INTRO, BACKGROUND, METHODOLOGY, KEY_FINDING, etc.)
- Extracts style profiles (vocabulary, pacing, conversation dynamics)
- Synthesizes learnings for improved script generation
- Runs iterative trials with checkpointing for expensive operations

**Video Production** (`claude-studio produce-video`):
- Takes training trial output and produces explainer videos
- Budget tier system controls image generation costs (micro=$0 to full=$15+)
- Scene importance scoring allocates limited images to high-impact moments
- Integrates KB figures - extracted PDF figures from knowledge base appear in videos
- Visual style presets (technical, educational, documentary)

The budget tier system is particularly useful - you can preview costs with `--show-tiers` before committing to generation. Scene importance scoring means even at low budgets, the KEY_FINDING and METHODOLOGY segments get proper visuals while TRANSITION segments just get text overlays.

Tested the full pipeline with a UAV positioning research paper: PDF → KB ingestion → training → video production. The charts and flowcharts from the paper now appear in the video synced to the narration. Ken Burns effects work well for static content, but we disabled zoompan for technical diagrams since they looked better static.

### Jan 30, 2026

Read some alarming posts about Clawdbot, so I did a quick security check to make sure I didn't overlook anything. So today's update is just adding `__repr__` to the Config classes, so they can't leak the API keys in debug outputs.

I also added a new feature to import keys from `.env` to your system keychain.

```
claude-studio secrets import .env
$ claude-studio secrets import .env
Importing keys from .env...
  + ANTHROPIC_API_KEY
  + OPENAI_API_KEY
  + RUNWAY_API_KEY
  + LUMA_API_KEY
  + ELEVENLABS_API_KEY

Imported: 5 keys

Tip: You can now delete .env - keys are stored securely in your OS keychain.
```
And you can check status:
```
claude-studio secrets list
$ claude-studio secrets list
                             API Key Status                             
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Key                  ┃ Description                        ┃ Status   ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ ANTHROPIC_API_KEY    │ Anthropic API key (required)       │ Keychain │
│ OPENAI_API_KEY       │ OpenAI API key (DALL-E, TTS)       │ Keychain │
│ LUMA_API_KEY         │ Luma AI API key (video)            │ Keychain │
│ RUNWAY_API_KEY       │ Runway ML API key (video)          │ Keychain │
│ ELEVENLABS_API_KEY   │ ElevenLabs API key (TTS)           │ Keychain │
│ GOOGLE_CLOUD_API_KEY │ Google Cloud API key (TTS)         │ Not set  │
│ PIKA_API_KEY         │ Pika Labs API key (video)          │ Not set  │
│ STABILITY_API_KEY    │ Stability AI API key (image/video) │ Not set  │
│ KLING_API_KEY        │ Kling AI API key (video)           │ Not set  │
│ MUBERT_API_KEY       │ Mubert API key (music)             │ Not set  │
│ SUNO_API_KEY         │ Suno API key (music)               │ Not set  │
└──────────────────────┴────────────────────────────────────┴──────────┘

Keychain = Stored securely in OS credential manager
Env var = Available via environment variable (less secure)
Not set = Not configured
```

### Jan 28, 2026

Today was an easy decision to get another provider dialed in. Over the weekend I got really excited about `remotion` and how I might be able to add data-driven graphics to a video and went down that rabbit hole. But as I started working on the specs I got a nagging feeling that I was getting seriously distracted and losing focus on the core part of this project which is a broad "studio" utility and while those graphics would be totally sick, and I'm going to do it... just not right now. 

Introducing DALL-E support!

```
cd "c:\Users\aaron\Documents\GitHub\claude-studio-producer" && claude-studio provider onboard -n dalle -t image --docs-url https://platform.openai.com/docs/guides/images
alle -t image --docs-url https://platform.openai.com/docs/guides/images                             ╭─ 🚀 Starting Onboarding ─╮
│ Provider Onboarding      │
│                          │
│ Name: dalle              │
│ Type: image              │
│ Docs: 1 URL(s)           │
│ Stub: None               │
╰──────────────────────────╯
🚀 Starting onboarding for dalle (image)
📖 Fetching documentation from https://platform.openai.com/docs/guides/images...
🔍 Analyzing documentation...
  💾 Checkpoint saved: docs
⠦ Analysis complete
╭────────────────────────────────────── 📊 Analysis Results ───────────────────────────────────────╮
│                                                                                                  │
│ ╭────────────────────────────────────────────────────────────────╮                               │
│ │  Provider Onboarding Summary:                          dalle │                                 │
│ ╰────────────────────────────────────────────────────────────────╯                               │
│                                                                                                  │
│ Status: in_progress                                                                              │
│ Started: 2026-01-28T17:03:20.933331                                                              │
│                                                                                                  │
│ SPECIFICATION:                                                                                   │
│   Name: OpenAI Images (DALL-E)                                                                   │
│   Type: image                                                                                    │
│   Base URL: https://api.openai.com                                                               │
│   Auth: bearer_token                                                                             │
│   Confidence: 90%                                                                                │
│                                                                                                  │
│ MODELS:                                                                                          │
│   • dall-e-3: Latest and most capable image generation model wit...                              │
│   • dall-e-2: Previous generation model, faster and cheaper, sup...                              │
│                                                                                                  │
│ ENDPOINTS: 3                                                                                     │
│   • POST /v1/images/generations - Generate images from text prompts...                           │
│   • POST /v1/images/edits - Edit an image using a mask and prompt (D...                          │
│   • POST /v1/images/variations - Create variations of an existing image (...                     │
│                                                                                                  │
│ LEARNINGS:                                                                                       │
│   Tips: 10                                                                                       │
│   Gotchas: 12                                                                                    │
│                                                                                                  │
│ QUESTIONS: 0 (0 answered)                                                                        │
│ TESTS: 0 run                                                                                     │
│                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
Completed steps: init, docs

                                📦 Available Models
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Model ID ┃ Description                                 ┃ Inputs      ┃ Outputs   ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ dall-e-3 │ Latest and most capable image generation... │ text        │ image/png │
│ dall-e-2 │ Previous generation model, faster and ch... │ text, image │ image/png │
└──────────┴─────────────────────────────────────────────┴─────────────┴───────────┘
                                    🔌 API Endpoints
┏━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Method ┃ Path                   ┃ Description                                 ┃ Async ┃
┡━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ POST   │ /v1/images/generations │ Generate images from text prompts           │ -     │
│ POST   │ /v1/images/edits       │ Edit an image using a mask and prompt (D... │ -     │
│ POST   │ /v1/images/variations  │ Create variations of an existing image (... │ -     │
└────────┴────────────────────────┴─────────────────────────────────────────────┴───────┘

💡 Tips:
  • DALL-E 3 automatically revises prompts for safety and quality - check revised_prompt in response
  • For DALL-E 3, use 'natural' style for more realistic images, 'vivid' for more dramatic/artistic 
  • Use 'hd' quality for DALL-E 3 when fine details are important (costs 2x)
  • For edits, mask should use transparency (alpha channel) to indicate areas to edit
  • Images for edits/variations must be square and PNG format
  • Use b64_json response format if you need to process images programmatically without downloading 
  • The 'user' parameter helps OpenAI detect and prevent abuse
  • DALL-E 3 prompts can be detailed and descriptive - the model handles complexity well
  • For multiple variations, DALL-E 2 is more cost-effective (supports n>1)
  • URLs returned expire after 1 hour - download or store images if needed long-term

⚠ Gotchas:
  • Content policy: No photorealistic faces of real people, violence, adult content, etc.
  • DALL-E 3 only supports n=1 (single image), unlike DALL-E 2
  • Image edits and variations are NOT supported with DALL-E 3, only DALL-E 2
  • Image URLs expire after 60 minutes
  • Input images for edits/variations must be exactly square (same width and height)
  • Maximum file size for uploads is 4MB
  • Requests may be rejected or prompts revised due to content policy
  • API returns 400 if prompt violates content policy
  • Different pricing: DALL-E 3 standard costs ~$0.040/image, HD costs ~$0.080/image; DALL-E 2      
1024x1024 costs ~$0.020/image
  • Generation time varies: DALL-E 3 typically 30-60 seconds, DALL-E 2 typically 10-20 seconds      
  • No batch processing - each request is synchronous
  • Cannot specify negative prompts or use advanced parameters like CFG scale, steps, etc.

Generate implementation? [y/n]: y
⚙️ Generating implementation...
💾 Saved implementation to core/providers/image/dalle.py
  💾 Checkpoint saved: implementation
⠸ Generating implementation...

✓ Implementation saved to core/providers/image/dalle.py

Generate and run tests? [y/n]: y
🧪 Generating test cases...
Generated 15 test cases
  💾 Checkpoint saved: testing
Record learnings to memory? [y/n]: y
  📝 Recorded 10 tips, 12 gotchas to memory
✓ Learnings recorded to memory

Export tests to pytest file? [y/n]: y
  Exported tests to tests\integration\test_dalle.py
✓ Tests exported to tests\integration\test_dalle.py
╭───────────────────────────────────── ✅ Onboarding Complete ─────────────────────────────────────╮
│                                                                                                  │
│ ╭────────────────────────────────────────────────────────────────╮                               │
│ │  Provider Onboarding Summary:                          dalle │                                 │
│ ╰────────────────────────────────────────────────────────────────╯                               │
│                                                                                                  │
│ Status: completed                                                                                │
│ Started: 2026-01-28T17:03:20.933331                                                              │
│                                                                                                  │
│ SPECIFICATION:                                                                                   │
│   Name: OpenAI Images (DALL-E)                                                                   │
│   Type: image                                                                                    │
│   Base URL: https://api.openai.com                                                               │
│   Auth: bearer_token                                                                             │
│   Confidence: 90%                                                                                │
│                                                                                                  │
│ MODELS:                                                                                          │
│   • dall-e-3: Latest and most capable image generation model wit...                              │
│   • dall-e-2: Previous generation model, faster and cheaper, sup...                              │
│                                                                                                  │
│ ENDPOINTS: 3                                                                                     │
│   • POST /v1/images/generations - Generate images from text prompts...                           │
│   • POST /v1/images/edits - Edit an image using a mask and prompt (D...                          │
│   • POST /v1/images/variations - Create variations of an existing image (...                     │
│                                                                                                  │
│ LEARNINGS:                                                                                       │
│   Tips: 10                                                                                       │
│   Gotchas: 12                                                                                    │
│                                                                                                  │
│ QUESTIONS: 0 (0 answered)                                                                        │
│ TESTS: 15 run                                                                                    │
│                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Jan 26, 2026

I realize the readme is getting too long and I should move the developer notes (ok two days later I did move it!). I will do that next time. Maybe. For now I just wanted to add a couple of notes about the addition of the knowledge base. It's worth checking out the [knowledge to video spec](docs/specs/KNOWLEDGE_TO_VIDEO.md) and its predecessor [docuemnt to video spec](docs/specs/DOCUMENT_TO_VIDEO.md). I was quickly refining how I wanted my next generation podcast creator to work. I'm partly reverse engineering NotebookLM's explainer video capability and adding my own spin to it since I love that feature but I want 100x more control and to be able to work with the intermediates. Rolling the dice and waiting 10 minutes for a new video isn't exactly my cup of tea. The main point here is to have the ability to reason over previous works and create new connections in derivative content. Plus the adversarial content is like doing your own Lincoln Douglas debate, reviewing the arguments, picking winners, and improving. My gut feeling on this is the intermediates will be entertaining and eye-opening, and I might never be satisfied, but that's ok. The journey is the point. 

What's neat is that we're getting some knowledge graphing on the source material, and for our knowledge base, and for our content! It should unlock some powerful features later.

I should also post some samples of the elevenlabs integration, because it worked and just with TTS and being able to script things has made this studio actually useful and kind of fun even if the videos and audio tracks I've made so far are just for comedy. At some point soon, I'll point this at some serious material and generate a serious video. Maybe. Comedy is good too.

### Jan 21, 2026

Just a couple of notes for now... with a little bit of metrics in play for the memory system, it was time to add a real memory system and I really wanted to get a production level option available using AgentCore. Everything still works local-mode for me, the single user, but when I'm ready to deploy I can leverage LTM on AgentCore and start trying out some multi-tenant memory options along with curated memory propagation. I wanted that in play before the other next thing which is to add an agentic flow for onboarding and testing new providers. This CLI option is so that you can point at any new provider's docs and have the agent set up your scaffolding and help you onboard. As I dog food this feature I should be able to rapidly onboard the rest of these providers. Here's a current snapshot of the providers (if this new feature works this list should go from mostly stubs to mostly ready in a couple of days):

```
$ claude-studio provider list
                        📦 Available Providers                        
┏━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Type    ┃ Name       ┃ Status ┃ File                               ┃
┡━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ video   │ kling      │ Stub   │ core\providers\video\kling.py      │
│ video   │ luma       │ Ready  │ core\providers\video\luma.py       │
│ video   │ pika       │ Stub   │ core\providers\video\pika.py       │
│ video   │ runway     │ Ready  │ core\providers\video\runway.py     │
│ video   │ stability  │ Stub   │ core\providers\video\stability.py  │
│ audio   │ elevenlabs │ Ready  │ core\providers\audio\elevenlabs.py │
│ audio   │ google_tts │ Stub   │ core\providers\audio\google_tts.py │
│ audio   │ inworld    │ Stub   │ core\providers\audio\inworld.py    │
│ audio   │ openai_tts │ Ready  │ core\providers\audio\openai_tts.py │
│ image   │ dalle      │ Stub   │ core\providers\image\dalle.py      │
│ music   │ mubert     │ Stub   │ core\providers\music\mubert.py     │
│ music   │ suno       │ Stub   │ core\providers\music\suno.py       │
│ storage │ local      │ Stub   │ core\providers\storage\local.py    │
│ storage │ s3         │ Stub   │ core\providers\storage\s3.py       │
└─────────┴────────────┴────────┴────────────────────────────────────┘
```

An example of how the new provider agent can profile a provider - it provides a rich analysis of what's possible with that provider and what might be missing:

```
$ claude-studio provider analyze core/providers/video/luma.py
⠸ Analyzing...
╭───────── 📄 Stub Analysis ─────────╮
│ Provider Analysis                  │
│                                    │
│ File: core/providers/video/luma.py │
│ Provider: Luma AI (Dream Machine)  │
│ Type: video                        │
│ Base Class: VideoProvider          │
╰────────────────────────────────────╯
                      Methods
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┓
┃ Method                      ┃ Status ┃ Signature ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━┩
│ No missing required methods │ N/A    │ N/A       │
└─────────────────────────────┴────────┴───────────┘

Notes:
  • This is NOT a stub - _is_stub is set to False and all methods are fully implemented 
  • Supports advanced features: text-to-video without seed image, keyframe support,     
generation chaining, character references
  • Two models available: ray-2 (default) and ray-3 (advanced features with character   
ref and HDR)
  • Supports 7 aspect ratios: 1:1, 16:9, 9:16, 4:3, 3:4, 21:9, 9:21
  • Three resolution tiers: 540p, 720p, 1080p with different pricing
  • Two duration options: 5s and 9s (mapped from requested duration)
  • Cost map includes all resolution/duration combinations
  • Includes async/await polling mechanism for generation completion
  • Supports both immediate generation (generate_video) and submit/wait pattern
  • Has specialized method for continuous scene generation (generate_continuous)        
  • Includes utility methods for listing generations and camera motions
  • Proper error handling with GenerationResult success/failure pattern
  • Uses synchronous LumaAI client calls within async methods (potential blocking issue)
  • Default timeout is 300s (5 min) from config, but _wait_for_completion defaults to   
600s (10 min)
  • Prompt is truncated to 2000 characters to respect Luma API limits
  • Supports continuation from previous generations via generation ID for scene chaining
  • Character reference feature is ray-3 model only
```

And here's my next provider to work on! I want some text to audio support for my podcost website (https://podcasts.spiritwriter.ai/), so I've done the scaffolding for elevenlabs, but not the full implementation.

```
$ claude-studio provider analyze core/providers/audio/elevenlabs.py
⠙ Analyzing...
╭──────────── 📄 Stub Analysis ────────────╮
│ Provider Analysis                        │
│                                          │
│ File: core/providers/audio/elevenlabs.py │
│ Provider: elevenlabs                     │
│ Type: tts                                │
│ Base Class: AudioProvider                │
╰──────────────────────────────────────────╯
                                       Methods                                          
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  
┃ Method               ┃ Status ┃ Signature                                          ┃  
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩  
│ generate_speech      │ ○ Stub │ async def generate_speech(self, text: str, voice_i │  
│ list_voices          │ ○ Stub │ async def list_voices(self) -> List[Dict           │  
│ validate_credentials │ ○ Stub │ async def validate_credentials(self) -> bool       │  
└──────────────────────┴────────┴────────────────────────────────────────────────────┘  

Notes:
  • Provider is explicitly marked as stub with _is_stub = True flag
  • Cost estimation is already implemented at ~$0.30 per 1K characters
  • Provider supports advanced features: voice cloning, emotion control, 29 languages   
  • Voice control parameters include: stability, similarity, style, speaker_boost       
  • API base URL likely https://api.elevenlabs.io/v1/
  • Main endpoint will be /text-to-speech/{voice_id}
  • Voices endpoint will be /voices
  • Requires proper error handling for API rate limits and quota
  • Should support streaming audio response (ElevenLabs returns audio/mpeg)
  • May need to handle voice_id defaults if none provided
  • The **kwargs in generate_speech likely for: stability, similarity_boost, style,     
use_speaker_boost parameters
```

Two hours later...

```
claude-studio provider test elevenlabs -t audio -p "Hello, this is a test of Claude Studio Producer onboarding a new provider in under two hours." --live
udio Producer onboarding a new provider in under two hours." --live                     
Testing ElevenLabsProvider...
Prompt/Text: Hello, this is a test of Claude Studio Producer onboarding a new provider 
in under two hours.

╭──────────── Test Result ────────────╮
│ ✓ Generation successful!            │
│                                     │
│ Audio saved to: test_elevenlabs.mp3 │
│ Size: 76948 bytes                   │
│ Format: mp3                         │
╰─────────────────────────────────────╯
⠇ Complete!
```

So the onboarding flow had a few things to work out. Namely: checkpointing. See, the first part of the agentic flow to fetch docs and create a spec worked great, but it was time consuming and each time we worked through some kink later in the pipeline, we were re-doing that step. Then we realized that there was some emojis breaking things in the implementation - Claude does love those emojis. And then instead of generating code, it was generating plans or summaries. Ah yes, always with the plans. So we improve the prompt, and the validation, and we make sure that the resume steps works well so what's done is done and we don't have to repeat it. 

What's really nice though is that my planning ahead about the memory was a good call. Check this out, so not only does the resume feature work, we've got the "auto" feature in there so Claude can iterate through the tests and fix them... and we also record the provider learnings to the long term memory. Even during onboarding we have learning opportunities and can record them for future sessions!

```
$ claude-studio provider onboard -n elevenlabs -t audio --resume --auto
╭───── 📂 Resume Session ──────╮
│ Resuming Provider Onboarding │
│                              │
│ Name: elevenlabs             │
╰──────────────────────────────╯
📂 Resumed session for elevenlabs
   Status: in_progress
   Current step: testing
   Stub path: core/providers/audio/elevenlabs.py
   Implementation: core/providers/audio/elevenlabs.py

Current step: testing
Spec loaded: ElevenLabs
Implementation: core/providers/audio/elevenlabs.py
╭──────────────────────────────── 📊 Analysis Results ─────────────────────────────────╮
│                                                                                      │
│ ╭────────────────────────────────────────────────────────────────╮                   │
│ │  Provider Onboarding Summary:                     elevenlabs │                     │
│ ╰────────────────────────────────────────────────────────────────╯                   │
│                                                                                      │
│ Status: in_progress                                                                  │
│ Started: 2026-01-22T04:55:02.530400                                                  │
│                                                                                      │
│ SPECIFICATION:                                                                       │
│   Name: ElevenLabs                                                                   │
│   Type: audio                                                                        │
│   Base URL: https://api.elevenlabs.io                                                │
│   Auth: api_key_header                                                               │
│   Confidence: 70%                                                                    │
│                                                                                      │
│ MODELS:                                                                              │
│   • eleven_monolingual_v1: English-only model with high quality and low laten...     │
│   • eleven_multilingual_v1: Supports multiple languages with good quality...         │
│   • eleven_multilingual_v2: Improved multilingual model with better quality an...    │
│   • eleven_turbo_v2: Fastest model optimized for low latency...                      │
│                                                                                      │
│ ENDPOINTS: 8                                                                         │
│   • POST /v1/text-to-speech/{voice_id} - Convert text to speech using a specified... │
│   • POST /v1/text-to-speech/{voice_id}/stream - Stream text to speech audio in       │
│ real-time...                                                                         │
│   • GET /v1/voices - Get list of available voices...                                 │
│   • GET /v1/voices/{voice_id} - Get details of a specific voice...                   │
│   • GET /v1/models - Get list of available models...                                 │
│                                                                                      │
│ LEARNINGS:                                                                           │
│   Tips: 9                                                                            │
│   Gotchas: 11                                                                        │
│                                                                                      │
│ QUESTIONS: 0 (0 answered)                                                            │
│ TESTS: 19 run                                                                        │
│                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────╯
Completed steps: init, docs, spec, questions, implementation, testing

                                  📦 Available Models
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ Model ID               ┃ Description                              ┃ Inputs ┃ Outputs ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ eleven_monolingual_v1  │ English-only model with high quality     │        │         │
│                        │ and...                                   │        │         │
│ eleven_multilingual_v1 │ Supports multiple languages with good    │        │         │
│                        │ qu...                                    │        │         │
│ eleven_multilingual_v2 │ Improved multilingual model with better  │        │         │
│                        │ ...                                      │        │         │
│ eleven_turbo_v2        │ Fastest model optimized for low latency  │        │         │
└────────────────────────┴──────────────────────────────────────────┴────────┴─────────┘
                                    🔌 API Endpoints
┏━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Method ┃ Path                             ┃ Description                      ┃ Async ┃
┡━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ POST   │ /v1/text-to-speech/{voice_id}    │ Convert text to speech using a   │ -     │
│        │                                  │ specified...                     │       │
│ POST   │ /v1/text-to-speech/{voice_id}/s… │ Stream text to speech audio in   │ -     │
│        │                                  │ real-time                        │       │
│ GET    │ /v1/voices                       │ Get list of available voices     │ -     │
│ GET    │ /v1/voices/{voice_id}            │ Get details of a specific voice  │ -     │
│ GET    │ /v1/models                       │ Get list of available models     │ -     │
│ GET    │ /v1/user/subscription            │ Get user subscription info and   │ -     │
│        │                                  │ usage lim...                     │       │
│ GET    │ /v1/history                      │ Get history of generated audio   │ -     │
│ POST   │ /v1/speech-to-speech/{voice_id}  │ Convert audio to speech in a     │ -     │
│        │                                  │ different v...                   │       │
└────────┴──────────────────────────────────┴──────────────────────────────────┴───────┘

💡 Tips:
  • Use voice_id parameter to specify which voice to use - get available voices from    
/v1/voices endpoint
  • For real-time applications, use the /stream endpoint for lower latency
  • Adjust voice_settings.stability (0-1) to control consistency vs expressiveness      
  • Adjust voice_settings.similarity_boost (0-1) to control how closely the voice       
matches the original
  • Use eleven_turbo_v2 model for fastest generation with acceptable quality
  • Character count is tracked per subscription tier - check /v1/user/subscription for  
limits
  • Streaming endpoint returns audio chunks as they're generated for lower perceived    
latency
  • Voice cloning and custom voice creation available through web interface or API      
(requires appropriate tier)
  • Use style parameter (0-1) to add more expressive variation to the voice

⚠ Gotchas:
  • API key must be passed in 'xi-api-key' header, not standard Authorization header    
  • Rate limits vary by subscription tier - free tier is heavily limited
  • Character limits are per month and depend on subscription tier
  • voice_id is required in the URL path, not in request body
  • Response is raw audio binary data, not JSON - set appropriate Accept headers        
  • Some premium voices may not be available on all subscription tiers
  • Text input has maximum length limits (typically 5000 characters, varies by tier)    
  • Streaming endpoint may not work well with all HTTP clients - ensure chunked transfer
encoding support
  • Voice settings are optional but can significantly impact output quality
  • History items may be automatically deleted after certain period depending on tier   
  • Speech-to-speech endpoint requires audio file in specific formats (check docs for   
supported formats)
```

So! We now have some video and audio support! And we have an agent that's good at onboarding new providers, so I should be able to get through several very quickly now!

### Jan 10, 2026

**Reflections about API drift**
Reflecting on some of the challenges that I had with the project: API drift is the most obvious one out of the gate. Claude was trained on these APIs a while back and with only one exception it had the signatures wrong. It created the script writer and scene analysis hooks with the Anthropic API without batting an eye. After some initial thrashing with the Runway API, I modified the dev pattern to first validate the API calls, create a test framework and start building the CLI, so I could more easily participate in testing in parallel while Claude Code was grinding away on some task. Onboarding the next API, Luma, had almost no thrashing. 

**Provider profiling and timeouts**
There was one point at 12AM sharp when my Luma calls started timing out. I had a default 300s timeout and most of my multi-scene runs were still getting done in 60-120 seconds, so this was both a frustration and worry. Thankfully, I'd created a `claude-studio test-provider luma` CLI call that bypasses the complex agent pipeline and does native API calls. It also timed out, so I was relieved I hadn't introduced a regression and given the timing I figured Luma probably has some batch job running in the middle of the night causing some queuing for customers like me burning the midnight oil. So advice to my future self or anyone else adding in new providers (like an image or audio service), always get the test rig dialed in before you start making calls that cost money. Why? Because I realized the next morning that while my side timed out, Luma queued me. Those runs finished eventually and so for every frustrated key press where I submitted another job that would time out, I was also ringing the register. So the next morning I implemented a `--timeout` parameter, so I not only doubled Luma's default timeout, but I could adjust it dynamically because some of my prompts were resulting in 8 scene runs which obviously will take longer.

**Parallelism**
This brings forward the question of parallelism in the runs. It seemed obvious in the design phase that I'd want to establish the scene plans from the script writer and execute those in parallel to whatever limit the provider would accept. So the provider model is evolving as you onboard each one - you learn a little about their queuing patterns, scheduled server loads (12 am not a great time), and how many parallel jobs you can run before you get rate limited. Note to self: add this... `test-provider scale` so I can verify when I get rate limited. This informs the job plan and expected timeout. At the end of the day though, at least for Luma, I figured out that parallelism wasn't as important as passing keyframes from one video to the next to maintain narrative consistency. Simply put in an example, you ask for 3 scenes about "a person working at a computer then celebrating", and you get 1st scene with a white male actor, a middle scene with an asian woman, and the last one with someone who might be similar to the first, but you can't tell. The narrative is ruined because even if you're super specific about the description of the actor, the LLM is going to be creative. So unless the provider is really good about using a seed input and keeping that "actor" in mind, you're going to need to produce linearly so you can sample then seed as you go.  

**Orphan harvesting**
Then there's orphan harvesting. This sounds terrible, I know. Help me find a better term, Claude!? I had several videos on Lumas' CDN that were from my midnight runs that timed out. While I had resuming sessions in the back of my mind I hadn't considered having to resume and fetch orphaned artifacts. I chalked this up to how many clips end up "on the cutting room floor". This is studio speak for the editing process in making a movie that leaves a lot of content, or in this archaic reference, cut pieces of film, left as trash on the floor. This old film would be recycled since it had silver in it. In our digital world though, each clip has metadata like provenance and critic comments. It has value and can likewise be recycled in testing and perhaps even get its day in another sequence that finds that clip more at home. Orphan harvesting with a silver lining?

**Learning loop analysis**
While I hope that my failures can somehow be useful later, I wasn't *entirely* sure that the feedback look that I incorporated was actually working. I was getting some better results run after run, but part of that was Claude having some context and curating some of my test incantations. The script writer agent is quite good at creating depth and detail in each envisioned scene and we could see Luma outright ignoring many of the details. Somewhere between my initial input, the screen writer's learnings from previous runs, and Luma's interpretations is some signal of improvement. Maybe. 

So I asked for an experiments module that I could use to analyze the data, help define experiments, and analyze the results. Then potentially tune how the memories are collected, learning extracted, and prompting/planning is influenced.

I wanted a high-level report.

```
============================================================
CLAUDE STUDIO PRODUCER - LEARNING LOOP ANALYSIS
============================================================

📊 OVERVIEW
   Total runs analyzed: 5
   Total scenes: 12
   Provider learnings recorded: 3

📈 QUALITY TREND
   Trend: IMPROVING
   First 3 runs avg: 65.2
   Last 3 runs avg: 78.4
   Overall avg: 71.8

⚠️  COMPLEXITY ANALYSIS (Racing to Bottom Check)
   Racing to bottom: NO ✓
   Achievability trend: +1.2/run
   Word count trend: -2.3/run

🧠 LEARNING STATISTICS
   luma:
      Learnings recorded: 3
      Avg adherence: 72.0
      Success rate: 67%
```

Also some intent analysis.
```
============================================================
INTENT PRESERVATION ANALYSIS
============================================================

📝 Original: A 15-second story of a developer having a breakthrough...
📝 Generated: Close-up of person at desk, neutral expression...

📊 SCORES
   Overall Preservation: 35%
   Overall Achievability: 85%
   Balance Score: 55

🔍 DIMENSIONS
   ⚠️ Semantic: 25%
      Lost: developer, breakthrough, story
   ⚠️ Emotional: 0%
      Lost: frustrated, triumphant
   ✓ Visual: 80%
   ⚠️ Narrative: 20%
      Lost: 15-second, journey

🚦 STATUS
   ⚠️  RACING TO BOTTOM - Prompt over-simplified!

💡 SUGGESTIONS
   ⚠️ RACING TO BOTTOM DETECTED
   The prompt has been over-simplified. Consider:
     - Restore semantic elements: developer, breakthrough, story
     - Restore emotional tone: frustrated, triumphant
     - Use more descriptive language while keeping visuals concrete
```

A chief concern is something like overfitting, or what I'm calling a race to the bottom. If I have to keep simplifying the prompt to get better alignment, how far way from the original intent am I?

The good news is that the feedback system works - to a degree. We'll just have to implement a smarter memory system and adjust how feedback is incorporated in subsequent runs.


### Jan 9, 2026

#### What is this even for?

I wanted to make a demo project that 1) shows off what you can do pretty quickly with Claude; 2) how to design and implement a working multi-agent workflow; 3) use learning/memory; 4) use rewards; and 5) have fun.

If you're curious about the design aspect, there are a bunch of [spec docs](docs/specs) and you can look at their timestamps to get a rough idea of the layering of the features. Well, I/we (me & the Claudes) did a lot in two days, let's just say that.

I used Claude.ai with Opus 4.5 from my mobile phone to start... using the microphone to dictate my pitch about the project from some [hastily scribbled notes on my notepad](examples/inputs/notebook-on-a-notebook.jpg). This got us our first specs. 

I'm actually on a new computer at home - Windows - because 1) I bought it to play some newer games with friends and 2) in theory it is fast enough to dev on, but I'm used to a Mac at work. Anyways, Claude on the web helped me get this laptop going with VS Code, Gitbash, Docker, Claude extension for VS Code, etc so I could actually dev on this machine. So now I have two Claudes. Claude Code (CC) in my IDE, and Claude "prime or planner?" (CP) that knows my project plan. I keep CP in the loop of the progress and he's the one that generates new specs or detailed prompts for CC. It's really about context management: IYKYK. CC chews through context and is constantly compressing, so it's not the best place to monitor your overall project progress. Also CC can chase its tail, so it is good to have CP around to help correct things.

**How is this fun?**
I've been interested in making "derivative content" for quite a while. Content that I would like to see that doesn't exist yet. I experimented and launched a little [news site](https://spiritwriter.ai) that uses an LLM to assess bias in news and rate it, then generate two variants: a hard left (0.2) and a hard right (0.8) where bias is 0 to 1, left to right. Then because I really love NotebookLM but didn't like waiting for their renders, I made a [podcasts site](https://podcasts.spiritwriter.ai) where I could define my interests and it would automatically download the latest scientific articles that matched and create a podcast talking about it, so every morning I'd have 3 new specially curated science-based podcasts on the hottest publications. Pretty cool, but also a bit expensive. I paused that one and now I have a journalclub subscription that sort of scratches that particular itch.

Now full circle. Why not create a virtual studio where you've got a producer who can take your budget and your pitch and craft pilots based on what he knows works and what you can afford? Then the producer hires a script writer agent and provides the guidelines for the kind of pilot to make. The script writer makes the various scenes know what it knows about the provider, like how long the clips can be and what they excel or fail at. The scenes get shot by a Video Generator agent (and the GenAI provider and be parallelized), then these come back to QA agents (this can be parallelized) for a technical review. The reports for each clip are provided to the Critic agent who looks at the original script and assesses the overall quality of the collection of clips and makes recommendations to the Editor agent who then creates an Edit Decision List (EDL) for the final candidate videos.

**Are we having fun yet?**
I thought putting a feedback loop in where the agents store learning in memory for the producer and script writer to leverage would be a great idea. And the budget aspect helps keep a lid on costs so you can do re-runs, but only on promising arcs, and only within your budget. Studio reinforcement learning. StudioRL. There, I made something up. Enjoy!

![make-it-rain-coffee](docs/screenshots/make-it-rain-coffee.gif)

**Prompt:**
*A 15-second story of a developer having a breakthrough: Scene 1 - Wide shot of developer at desk in cozy home office at night, hunched over laptop, frustrated expression, warm desk lamp lighting. Scene 2 - They lean back with a satisfied smile, stretch arms up in victory celebration, coffee cup visible nearby, cinematic triumph moment.* 

**Result:** make it rain coffee...!
