# /produce - Run Production Pipeline

Execute the video production pipeline to generate content from a concept.

## Usage

```
/produce "<concept>" [options]
```

## Options

- `--budget <amount>` - Budget in USD (determines tier)
- `--style <style>` - Narrative style (podcast, educational, documentary, visual_storyboard)
- `--provider <name>` - Video provider (luma, runway, pika)
- `--live` - Enable live API calls (default is mock mode)
- `--scenes <n>` - Override number of scenes

## Examples

```bash
# Mock mode test
/produce "A day in the life of a bee" --budget 5

# Live production with podcast style
/produce "The science of coffee brewing" --budget 20 --style podcast --live

# Using specific provider
/produce "Abstract art in motion" --budget 10 --provider runway --live
```

## What It Does

1. Producer agent analyzes concept and budget
2. ScriptWriter creates scene breakdown
3. VideoGenerator generates each scene
4. AudioGenerator creates narration
5. QAVerifier validates frames
6. Critic scores and extracts learnings
7. Editor creates edit decision list
8. Renderer combines into final output

## Production Tiers

| Budget | Tier | Resolution | Duration |
|--------|------|------------|----------|
| $1-5 | Micro | 720p | 15-30s |
| $5-20 | Standard | 1080p | 30-90s |
| $20-50 | Premium | 1080p | 90-180s |
| $50+ | Pro | 4K | 180s+ |

## Output

- Video saved to `artifacts/runs/<run_id>/output.mp4`
- Scene files in `artifacts/runs/<run_id>/scenes/`
- Script in `artifacts/runs/<run_id>/script.json`
- Learnings saved to memory

## Skills Used

This command activates:
- `video-production` skill for rendering patterns
- `provider-integration` skill for API calls
- `podcast-profile` skill (if --style podcast)

## Cost

Estimated cost shown before live execution. Mock mode has no API costs.
