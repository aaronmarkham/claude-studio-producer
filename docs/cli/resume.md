# resume - Resume Interrupted Productions

The `resume` command continues a production from where it stopped, picking up from existing assets and completing the remaining pipeline stages. This is essential for handling interrupted productions due to API limits, network issues, or system interruptions.

## Synopsis

```bash
claude-studio resume RUN_ID [OPTIONS]
```

## Description

The resume command intelligently continues production by:

- Loading existing scenes, videos, and run metadata
- Detecting which pipeline stages have been completed
- Resuming from the appropriate stage (QA verification, critic analysis, or EDL creation)
- Preserving all existing work and budget tracking
- Handling mixed video + audio assembly if audio files exist

## Required Arguments

### `RUN_ID`
Run directory name or path to resume.

**Special Values:**
- `latest` - Resume the most recent production run
- `<timestamp>` - Resume specific run (e.g., `20260131_162250`)
- `<path>` - Resume from custom directory path

**Examples:**
- `claude-studio resume latest`
- `claude-studio resume 20260131_162250`
- `claude-studio resume ./my_custom_run`

## Options

### Execution Control

#### `--live`
Use live QA with Claude Vision.

When enabled, performs real video quality analysis using Claude's vision capabilities. Without this flag, uses mock QA scores.

#### `--skip-qa`
Skip QA verification stage.

Use when QA verification has already been completed or when you want to proceed without quality analysis.

#### `--skip-critic`
Skip critic analysis stage.

Bypasses the production quality scoring and approval process.

#### `--skip-editor`
Skip EDL creation stage.

Prevents generation of Edit Decision Lists, useful when only wanting QA/critic analysis.

## Examples

### Basic Usage

```bash
# Resume latest production run
claude-studio resume latest

# Resume specific run with live QA
claude-studio resume 20260131_162250 --live

# Resume with all stages
claude-studio resume my_run_id --live
```

### Selective Stage Execution

```bash
# Skip QA if already completed
claude-studio resume latest --skip-qa --live

# Only run QA and critic, skip EDL
claude-studio resume latest --live --skip-editor

# Fast resume with mock QA
claude-studio resume latest --skip-critic --skip-editor
```

### Development Workflows

```bash
# Quick QA check without full pipeline
claude-studio resume latest --live --skip-critic --skip-editor

# Generate EDL from existing QA results
claude-studio resume latest --skip-qa --skip-critic

# Complete production with real analysis
claude-studio resume latest --live
```

## Resume Detection Logic

### Run Directory Requirements

The resume command requires these artifacts in the run directory:

**Required:**
- `memory.json` - Run metadata and stage tracking
- `scenes/` - Scene specification files
- `videos/` - Generated video files

**Optional:**
- `qa/` - QA analysis results (if QA completed)
- `critic_results.json` - Critic evaluation (if critic completed)
- `audio/` - Audio files for mixed output

### Stage Detection

The command automatically detects completion status:

1. **Memory Analysis**: Checks `memory.json` for completed stages
2. **Asset Discovery**: Scans for QA files, critic results, EDLs
3. **Smart Resume**: Starts from first incomplete stage

**Example Detection:**
```bash
# Run status detection
Concept: Product demo for mobile app
Budget: $2.50 / $15.00 spent  
Current stage: video_generation

# Detected completion:
✓ Scenes loaded (5 scenes)
✓ Videos loaded (5 videos)  
○ QA verification needed
○ Critic analysis needed
○ EDL creation needed
```

## Resume Pipeline Stages

### Stage 1: Asset Loading

1. **Memory Loading**
   - Reads `memory.json` for run metadata
   - Extracts concept, budget, and progress information
   - Calculates actual budget spent from timeline

2. **Scene Loading**
   - Reconstructs Scene objects from `scenes/*.json`
   - Preserves all scene metadata and specifications
   - Validates scene integrity and completeness

3. **Video Loading**
   - Discovers all `videos/scene_*_v*.mp4` files
   - Creates GeneratedVideo objects with correct metadata
   - Measures actual video durations using ffprobe
   - Maps videos to scenes and variations

### Stage 2: QA Verification (if not skipped)

1. **QA Results Discovery**
   - Checks for existing `qa/scene_*_v*_qa.json` files
   - Loads previous QA results if available
   - Only runs QA on videos without existing analysis

2. **Quality Analysis**
   - Uses QAVerifierAgent with Claude Vision (if `--live`)
   - Analyzes video quality across multiple dimensions:
     - Visual accuracy against scene description
     - Style consistency across the production
     - Technical quality (resolution, artifacts)
     - Narrative fit with original concept

3. **Checkpoint Saving**
   - Saves QA results immediately after each video
   - Enables resumption even if QA is interrupted
   - Updates video quality scores in memory

**QA Output Example:**
```bash
Analyzing scene_001: Logo reveal animation
  v0: 85.5/100 ✓ (passed)
  
Analyzing scene_002: Product demonstration  
  v0: 72.1/100 ✓ (passed)
  
QA complete: 4/5 passed (80%)
```

### Stage 3: Critic Analysis (if not skipped)

1. **Scene Results Compilation**
   - Builds SceneResult objects from videos and QA data
   - Selects best video variation per scene (highest QA score)
   - Combines generation costs and quality metrics

2. **Production Evaluation**
   - Uses CriticAgent for holistic production assessment
   - Evaluates budget efficiency and concept realization
   - Provides approval recommendation and feedback

3. **Results Storage**
   - Saves critic results to `critic_results.json`
   - Prevents re-analysis on subsequent resumes
   - Includes quality scores and approval reasoning

**Critic Output Example:**
```bash
Overall score: 78.5/100
Approved: true
Reasoning: Strong visual coherence and effective concept realization. 
Minor audio-visual sync improvements possible.
```

### Stage 4: Edit Decision List Creation (if not skipped)

1. **Asset Compilation**
   - Combines video assets, QA results, and audio files
   - Maps audio files to scenes if available
   - Prepares complete asset inventory for editing

2. **EDL Generation**
   - Uses EditorAgent to create multiple edit candidates
   - Recommends optimal edit based on quality and flow
   - Specifies transitions, timing, and effects

3. **Audio-Video Mixing** (if audio available)
   - Detects audio files in `audio/` directory
   - Mixes video with audio using appropriate fit mode
   - Creates final concatenated output video
   - Saves mixed scenes and final result

**EDL Output Example:**
```bash
Candidate: Standard Cut (recommended)
Edit decisions: 5 scenes
Total duration: 32.5s
Quality: 81.2/100

✓ Mixed scene_001 (video + audio)
✓ Mixed scene_002 (video + audio)
...
✓ Final output: final_output.mp4
```

## Audio-Video Integration

### Audio Detection

Resume automatically detects audio assets:

```bash
# Audio files detected
Found audio files:
  scene_001.mp3 (12.5s)
  scene_002.mp3 (8.2s)
  scene_003.mp3 (11.8s)
```

### Mixing Process

When audio is available, resume performs audio-video mixing:

1. **Individual Scene Mixing**
   - Combines each video with corresponding audio
   - Uses appropriate fit mode (truncate for video-led)
   - Saves mixed results to `mixed/` directory

2. **Final Concatenation**
   - Concatenates all mixed scenes
   - Creates seamless final video with audio
   - Saves as `final_output.mp4`

### Fit Modes

- **Video-led** (default): Audio is truncated to match video duration
- **Audio-led**: Video is stretched/held to match audio duration

## Memory and Budget Tracking

### Budget Calculation

Resume accurately tracks spent budget:

```json
{
  "budget_total": 15.00,
  "timeline": [
    {
      "stage": "video_generation", 
      "details": {"cost": 2.50}
    },
    {
      "stage": "qa_verification",
      "details": {"cost": 0.00}
    }
  ]
}
```

Budget spent is calculated from timeline entries, not stale `budget_spent` field.

### Progress Tracking

Resume maintains detailed progress information:

- **Completed Stages**: Which pipeline stages finished successfully
- **Asset Inventory**: Count and status of generated assets
- **Quality Metrics**: QA scores and critic evaluations
- **Timing Information**: Duration of each production stage

## Error Recovery

### Partial Completion Handling

Resume gracefully handles various interruption scenarios:

**Video Generation Interrupted:**
```bash
# Some videos missing
Warning: scene_003 has no videos - will be skipped in QA
```

**QA Partially Complete:**
```bash
# QA results exist for some videos
Found 3 existing QA results
Loading existing QA data...
✓ Loaded QA results for 3 scenes
```

**Audio-Video Mismatch:**
```bash
# Audio duration doesn't match video
Warning: Audio duration mismatch for scene_002: expected 10s, got 8s
Using video duration for mixing
```

### Corrupted Data Recovery

Resume validates data integrity:

```bash
# Invalid scene data
Error loading scene_003.json: Invalid JSON format
Skipping corrupted scene file

# Missing video files
Warning: scene_002_v0.mp4 not found
Removing from candidate list
```

## Integration with Other Commands

### Production Pipeline Integration

Resume fits into the complete production workflow:

```bash
# 1. Start production
claude-studio produce -c "Product demo" -b 20 --live -p luma

# 2. Production interrupted (API limit, network, etc.)
# ... interruption occurs ...

# 3. Resume from where it stopped  
claude-studio resume latest --live

# 4. Use results with other commands
claude-studio render edl <run_id>
claude-studio upload youtube <run_id>/final_output.mp4
```

### Asset Management Integration

Resume works with asset management commands:

```bash
# Resume to complete QA
claude-studio resume latest --live --skip-critic --skip-editor

# Review assets based on QA results
claude-studio assets list <run_id> --status draft

# Approve/reject based on QA scores
claude-studio assets approve <run_id> --image 1,3,5  # High QA scores
claude-studio assets reject <run_id> --image 2,4 --reason "low QA scores"
```

## Debugging and Troubleshooting

### Common Issues

#### Missing Run Directory
```bash
Error: Run directory not found: 20260131_999999
```
**Solution:** Check run ID spelling or use `latest`

#### Corrupted Memory File
```bash
Error: memory.json not found in run directory
```
**Solution:** Run directory may not be from `produce` command

#### FFmpeg Issues
```bash
Error getting video duration: ffprobe not found
```
**Solution:** Install FFmpeg for video duration detection

#### API Configuration
```bash
Warning: Claude API key not set, using mock QA mode
```
**Solution:** Set `ANTHROPIC_API_KEY` for live QA analysis

### Debug Information

Resume provides detailed progress information:

```bash
# Run information
Concept: Product demo for mobile app
Budget: $2.50 / $15.00 spent
Current stage: video_generation

# Asset inventory
✓ Loaded 5 scenes
✓ Loaded 8 videos  
✓ Found 3 audio files

# Stage status
✓ Scenes generated
✓ Videos generated  
○ QA verification needed
○ Critic analysis needed
○ EDL creation needed
```

### Manual Inspection

For troubleshooting, manually inspect run directories:

```bash
# Check run structure
ls -la artifacts/runs/<run_id>/

# Verify video files exist
ls -la artifacts/runs/<run_id>/videos/

# Check existing QA results  
ls -la artifacts/runs/<run_id>/qa/

# Review memory file
cat artifacts/runs/<run_id>/memory.json | jq .
```

## Performance Considerations

### Incremental Processing

Resume only processes what's needed:

- **QA**: Only analyzes videos without existing results
- **Critic**: Reuses existing analysis if available
- **EDL**: Creates new EDLs based on current assets

### Network Optimization

For live QA analysis:
- Processes videos sequentially to avoid rate limits
- Saves results immediately as checkpoints
- Enables resumption if network interruption occurs

### Storage Efficiency

Resume preserves existing work:
- Doesn't regenerate existing assets
- Reuses QA analysis and critic evaluations  
- Only creates new files for missing stages

## Advanced Usage

### Selective Resume Strategies

```bash
# QA-only resume (for quality assessment)
claude-studio resume latest --live --skip-critic --skip-editor

# Full pipeline resume (complete all stages)
claude-studio resume latest --live

# Fast completion (skip expensive QA)
claude-studio resume latest --skip-qa
```

### Batch Resume Processing

```bash
# Resume multiple interrupted runs
for run_id in $(ls artifacts/runs/); do
  if [ ! -f "artifacts/runs/$run_id/final_output.mp4" ]; then
    echo "Resuming $run_id..."
    claude-studio resume "$run_id" --live
  fi
done
```

### Development Iteration

```bash
# Fast iteration for EDL testing
claude-studio resume latest --skip-qa --skip-critic

# QA testing without full pipeline
claude-studio resume latest --live --skip-critic --skip-editor
```

## Output Structure After Resume

Successful resume creates complete output structure:

```
artifacts/runs/<run_id>/
├── scenes/                     # Original scene specs
├── videos/                     # Generated video files
├── qa/                        # QA analysis results  
│   ├── scene_001_v0_qa.json
│   └── ...
├── critic_results.json        # Critic evaluation
├── edl/                       # Edit Decision Lists
│   └── final.json
├── mixed/                     # Audio-video mixed scenes
│   ├── scene_001_mixed.mp4
│   └── ...
├── final_output.mp4           # Complete final video
└── memory.json                # Updated run metadata
```

## Version History

- **0.6.0**: Audio-video mixing integration and improved error recovery
- **0.5.x**: Multi-stage resume with QA checkpointing
- **0.4.x**: Basic production resume functionality