# /produce - Run Production Pipeline

Generate a video with the production pipeline. `produce` is now a **command
group** — pick the subcommand that matches the input, or use `produce-legacy`
for the classic one-shot concept→video flow.

## Usage

```
# New verb-group (pick an input):
cs produce topic "<topic>"        # research a topic, build a KB, then produce
cs produce paper <kb_id>          # produce from an existing knowledge base
cs produce script <file>          # produce from a pre-written script
cs produce project -c "<prompt>"  # multi-source (shards + KB + assets)

# Classic one-shot concept->video:
cs produce-legacy -c "<concept>" [options]
```

## Options

### New group (`paper`/`topic`/`script`/`project`)
- `-p, --provider <name>` - Video provider (`luma`, `higgsfield`, `auto`)
- `-s, --style <style>` - Video style (`explainer`, `documentary`, `tutorial`)
- `-d, --duration <seconds>` - Target duration
- `-b, --budget <amount>` - Budget in USD
- `-l, --language <code>` - Script/TTS language (ISO 639-1)
- `--voice <name>` - TTS voice
- `--live / --mock` - Real providers vs. dry run (mock)

### Legacy (`produce-legacy`)
- `-c, --concept <text>` - Concept description (required)
- `--budget <amount>` - Budget in USD (determines tier)
- `--style <style>` - Narrative style (`visual_storyboard`, `podcast`, `educational`, `documentary`)
- `--provider <name>` - Video provider (`luma`, `runway`, `mock`)
- `--audio-tier <tier>` - `none`, `music_only`, `simple_overlay`, `time_synced`
- `--mode <mode>` - `video-led` or `audio-led`
- `--live` - Enable live API calls (default is mock mode)

## Examples

```bash
# Mock-mode test, research a topic end-to-end
cs produce topic "A day in the life of a bee" --budget 5

# Produce from a knowledge base, live
cs produce paper kb_1c28d10264bd --budget 20 --live -p luma

# Classic concept->video, podcast narration, live
cs produce-legacy -c "The science of coffee brewing" --budget 20 --style podcast --live
```

## What It Does

1. Producer agent analyzes concept/inputs and budget
2. ScriptWriter creates scene breakdown
3. VideoGenerator generates each scene
4. AudioGenerator creates narration
5. QAVerifier validates frames
6. Critic scores and extracts learnings
7. Editor creates edit decision list
8. Renderer combines into final output

## Output

- Video saved to `artifacts/runs/<run_id>/`
- Scene files in `artifacts/runs/<run_id>/scenes/`
- Learnings saved to memory

Check or resume a run with `cs produce status <run_id>` / `cs produce resume <run_id>`.

## Cost

Estimated cost shown before live execution. Mock mode has no API costs.

See `docs/cli/produce.md` and `docs/cli/produce-legacy.md` for the full reference.
