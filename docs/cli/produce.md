# produce - Full Video Production Pipeline

The `produce` command runs the complete AI video production pipeline with multi-agent orchestration. This is the main entry point for creating videos from concept descriptions.

## Synopsis

```bash
claude-studio produce -c CONCEPT [OPTIONS]
```

## Description

The produce command demonstrates sophisticated agent patterns including:
- Sequential planning stages (Producer → ScriptWriter)
- Parallel asset generation (Video + Audio via Strands)
- Quality evaluation pipeline (QA → Critic → Editor)

## Required Arguments

### `--concept, -c TEXT`
Video concept description (required).

**Examples:**
- `"Logo reveal for TechCorp"`
- `"Product demo for mobile app"`
- `"Tutorial on machine learning basics"`

## Options

### Core Options

#### `--budget, -b FLOAT`
Total budget in USD (default: 10.0).

Controls production scale and provider usage. Higher budgets enable more variations and premium providers.

#### `--duration, -d FLOAT` 
Target video duration in seconds (default: 30.0).

Influences scene count and pacing. Typical ranges:
- 5-15s: Logo/brand videos
- 30-60s: Product demos
- 60-300s: Tutorials/explanations

#### `--provider, -p CHOICE`
Video provider to use.

**Choices:**
- `luma` - Luma AI (recommended, text/image to video)
- `runway` - Runway ML (image to video)  
- `mock` - Mock provider (development/testing)

**Default:** `luma`

### Execution Mode

#### `--live`
Use live API providers (costs real money!).

When specified, uses actual API providers. **Warning:** Generates real costs.

#### `--mock` 
Use mock providers (default).

Safe development mode with simulated responses and no API costs.

### Production Options

#### `--audio-tier CHOICE`
Audio production tier.

**Choices:**
- `none` - No audio generation (default)
- `music_only` - Background music only
- `simple_overlay` - Basic voiceover + music
- `time_synced` - Synchronized audio with video timing

#### `--variations, -v INTEGER`
Number of video variations per scene (default: 1).

Higher values provide more options but increase cost and generation time.

#### `--timeout INTEGER`
Video generation timeout in seconds (default: 600).

Increase for busy provider queues or complex generations.

### Advanced Options

#### `--seed-assets, -s PATH`
Directory containing seed images/assets (PNG/JPG).

Provides reference images for video generation, improving consistency and relevance.

#### `--execution-strategy, -e CHOICE`
Scene execution strategy for continuity.

**Choices:**
- `auto` - Automatically detect from script (default)
- `all_parallel` - Generate all scenes in parallel (fastest)
- `all_sequential` - Generate scenes sequentially (best continuity)
- `manual` - Use manual groups from script

#### `--style CHOICE`
Narrative style.

**Choices:**
- `visual_storyboard` - Visual-focused narrative (default)
- `podcast` - Rich NotebookLM-style narration
- `educational` - Educational lecture format
- `documentary` - Documentary style

#### `--mode CHOICE`
Production mode.

**Choices:**
- `video-led` - Video determines timing (default)
- `audio-led` - Audio determines timing

### Output Options

#### `--output-dir, -o PATH`
Output directory.

**Default:** `artifacts/runs/<run_id>`

#### `--run-id TEXT`
Custom run ID.

**Default:** Auto-generated timestamp (`YYYYMMDD_HHMMSS`)

### Display Options

#### `--verbose, -V`
Show full artifacts without truncation.

Displays complete scene descriptions, prompts, and evaluation details.

#### `--theme, -t TEXT`
Color theme.

**Choices:** `default`, `ocean`, `sunset`, `matrix`, `pro`, `neon`, `mono`

#### `--json`
Output results as JSON.

Suppresses rich formatting and returns structured data.

#### `--debug`
Enable debug output.

Shows detailed error traces and internal processing information.

## Examples

### Basic Usage

```bash
# Quick 5-second demo with mock providers
claude-studio produce -c "Logo reveal for TechCorp" -d 5 --mock

# Live production with Luma (costs money)
claude-studio produce -c "Product demo for mobile app" -b 15 -d 30 --live -p luma

# Full production with audio
claude-studio produce -c "Tutorial video" -b 50 -d 60 --audio-tier simple_overlay --live
```

### Advanced Usage

```bash
# Use seed images for consistent branding
claude-studio produce -c "Product showcase" --live -s ./brand_assets/

# Generate multiple variations
claude-studio produce -c "Marketing video" -b 30 -v 3 --live

# Extended timeout for complex scenes
claude-studio produce -c "Complex animation" --live --timeout 900

# Podcast-style narration
claude-studio produce -c "Explain quantum computing" --style podcast --audio-tier time_synced

# Audio-led production (audio timing drives video)
claude-studio produce -c "Music video concept" --mode audio-led --audio-tier time_synced
```

### Output Control

```bash
# Custom output directory
claude-studio produce -c "test" --mock -o ./my_production/

# Custom run ID
claude-studio produce -c "test" --mock --run-id my_custom_run

# JSON output for scripting
claude-studio produce -c "test" --mock --json > result.json

# Different color theme
claude-studio produce -c "test" --mock --theme matrix

# Verbose output with full details
claude-studio produce -c "test" --mock --verbose
```

## Pipeline Stages

### Stage 1: Planning (Sequential)

1. **ProducerAgent** analyzes concept and creates pilot strategies
   - Budget allocation across production tiers
   - Provider knowledge from long-term memory
   - Risk assessment and feasibility analysis

2. **ScriptWriterAgent** generates scene breakdown
   - Optimal scene count based on duration
   - Visual elements and transitions
   - Prompt optimization for selected provider

**Output:** Scene specifications and production plan

### Stage 2: Asset Generation (Parallel via Strands)

1. **VideoGeneratorAgent** creates video content
   - Uses execution strategy for continuity
   - Parallel or sequential generation based on dependencies
   - Seed asset integration when provided

2. **AudioGeneratorAgent** generates voiceover and music (if enabled)
   - Text-to-speech with selected voice
   - Background music matching video tone
   - Timing synchronization with video duration

**Output:** Video clips and audio tracks

### Stage 3: Evaluation (Sequential)

1. **QAVerifierAgent** analyzes video quality
   - Visual accuracy and coherence
   - Style consistency across scenes
   - Technical quality assessment
   - Narrative fit with original concept

2. **CriticAgent** scores production quality
   - Overall production evaluation
   - Budget efficiency analysis
   - Approval/rejection recommendation
   - Provider performance learning

3. **EditorAgent** creates Edit Decision Lists (EDLs)
   - Multiple edit candidate generation
   - Transition selection and timing
   - Text overlay positioning
   - Final assembly instructions

**Output:** Quality scores, approval status, and EDL

### Stage 4: Rendering

1. **AudioMixer** combines video and audio
   - Fit mode based on production mode
   - Volume balancing and normalization
   - Scene concatenation

2. **FFmpegRenderer** creates final video
   - Transition effects application
   - Text overlay rendering
   - Format optimization

**Output:** Final rendered video

## Output Structure

Production runs create organized directory structures:

```
artifacts/runs/<run_id>/
├── metadata.json           # Run metadata and costs
├── scenes/                 # Scene specifications
│   ├── scene_001.json
│   ├── scene_002.json
│   └── ...
├── videos/                 # Generated video clips
│   ├── scene_001_v0.mp4
│   ├── scene_002_v0.mp4
│   └── ...
├── audio/                  # Audio files (if enabled)
│   ├── scene_001_voice.mp3
│   └── background_music.mp3
├── edl/                    # Edit Decision Lists
│   ├── edit_candidates.json
│   ├── recommended_cut.json
│   └── ...
├── renders/                # Final rendered videos
│   └── final_video.mp4
├── mixed/                  # Video+audio combinations
│   └── scene_001_mixed.mp4
└── final_output.mp4        # Complete final video
```

## Budget and Cost Management

The produce command includes sophisticated budget management:

### Production Tiers

Based on budget allocation:

- **Micro** ($0-5): Single scenes, basic quality
- **Low** ($5-15): Multiple scenes, standard quality
- **Medium** ($15-50): Enhanced quality, multiple variations
- **High** ($50-100): Premium quality, extensive variations
- **Full** ($100+): Maximum quality, comprehensive production

### Cost Tracking

Costs are tracked throughout production:

```json
{
  "costs": {
    "video": 2.50,
    "audio": 0.15,
    "total": 2.65
  },
  "budget_allocated": 10.00,
  "budget_spent": 2.65
}
```

## Memory and Learning

The produce command leverages long-term memory for optimization:

### Provider Learning
- Successful prompt patterns
- Quality score trends  
- Cost optimization strategies
- Common failure modes

### Pattern Recognition
- Scene types that work well
- Optimal duration ranges
- Effective transitions
- Audio-video synchronization

## Error Handling

Common issues and solutions:

### API Configuration
```bash
# Missing API keys
Error: LUMA_API_KEY not set (check keychain or env)

# Solution
claude-studio secrets set LUMA_API_KEY your_key
```

### Budget Constraints
```bash
# Insufficient budget
Warning: Concept complexity requires $15+ budget, got $5

# Solution
claude-studio produce -c "concept" -b 20 --live
```

### Generation Failures
```bash
# Provider timeout
Error: Video generation timeout after 600s

# Solution  
claude-studio produce -c "concept" --timeout 900 --live
```

### FFmpeg Issues
```bash
# Missing FFmpeg
Warning: FFmpeg not installed - skipping render

# Solution
brew install ffmpeg  # macOS
sudo apt install ffmpeg  # Ubuntu
```

## Integration with Other Commands

### Resume Failed Productions
```bash
# If production fails, resume from checkpoint
claude-studio resume <run_id> --live
```

### Re-render with Different Settings
```bash
# Use existing assets with new edit
claude-studio render edl <run_id> -c creative_cut
```

### Upload Results
```bash
# Upload final video to YouTube
claude-studio upload youtube artifacts/runs/<run_id>/final_output.mp4 \
  -t "My Video Title"
```

### Asset Management
```bash
# Review and approve individual assets
claude-studio assets list artifacts/runs/<run_id>
claude-studio assets approve artifacts/runs/<run_id> --image all
```

## Performance Tips

### Development
- Use `--mock` flag during development
- Start with short durations (5-10s)
- Test concepts with single variations

### Production
- Set appropriate timeouts for complex scenes
- Use seed assets for consistency
- Monitor costs with budget limits
- Utilize multiple variations for better results

### Optimization
- Reuse approved assets across runs
- Leverage provider learning from memory
- Batch similar productions for efficiency

## Version History

- **0.6.0**: Current version with unified production architecture
- **0.5.x**: Multi-agent orchestration with Strands patterns  
- **0.4.x**: Basic video generation pipeline