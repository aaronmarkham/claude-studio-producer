# Examples

Example scripts demonstrating the Claude Studio Producer system.

## End-to-End Production Pipeline

The `e2e_production.py` script runs the full video production pipeline from concept to final edit.

### Usage

**Mock Mode** (for testing, no API calls):
```bash
python examples/e2e_production.py --mock
```

**Live Mode** (real API calls to Runway + OpenAI TTS):
```bash
# Set API keys first
export OPENAI_API_KEY="your-key-here"
export RUNWAY_API_KEY="your-key-here"  # When Runway provider is configured

# Run with live providers
python examples/e2e_production.py --live --budget 15 --concept "Product demo for a todo app"
```

### Options

- `--mock` - Use mock providers (default)
- `--live` - Use live API providers
- `--budget <amount>` - Total budget in USD (default: 20.0)
- `--concept <text>` - Video concept description
- `--audio-tier <tier>` - Audio tier: none, music_only, simple_overlay, time_synced, full_production

### Examples

```bash
# Simple mock test
python examples/e2e_production.py --mock

# Custom concept with higher budget
python examples/e2e_production.py --mock --budget 50 --concept "Tutorial on using Git"

# Live production with voiceover only
python examples/e2e_production.py --live --audio-tier simple_overlay

# Full production with all audio layers
python examples/e2e_production.py --live --budget 100 --audio-tier full_production
```

### Output

The pipeline creates a timestamped run directory with all artifacts:

```
artifacts/runs/<run_id>/
├── metadata.json          # Run metadata, timing, costs
├── scenes/                # Scene specifications
│   ├── scene_001.json
│   └── scene_002.json
├── videos/                # Generated videos (or mock placeholders)
│   ├── scene_001_var0.mp4
│   └── scene_001_var1.mp4
├── audio/                 # Generated audio tracks
│   ├── scene_001_vo.mp3
│   └── scene_001_music.mp3
└── edl/                   # Edit Decision Lists
    ├── edit_candidates.json
    ├── safe_cut.json
    ├── creative_cut.json
    └── balanced_cut.json
```

### Pipeline Stages

The script orchestrates all agents through 7 stages:

1. **Producer** - Analyzes concept and creates pilot strategies
2. **Script Writer** - Breaks concept into detailed scenes
3. **Video Generator** - Generates video variations per scene
4. **Audio Generator** - Creates voiceover, music, and SFX
5. **QA Verifier** - Verifies video quality
6. **Critic** - Evaluates results and makes decisions
7. **Editor** - Creates multiple edit candidates

### Requirements

**For Mock Mode:**
- Python 3.11+
- Dependencies from `requirements.txt`
- ANTHROPIC_API_KEY (for Claude)

**For Live Mode:**
- All mock mode requirements
- OPENAI_API_KEY (for text-to-speech)
- RUNWAY_API_KEY (when Runway provider is configured)
