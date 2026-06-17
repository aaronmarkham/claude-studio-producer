# produce - Video Production Pipeline

`produce` is a **command group**. Instead of one monolithic command, you pick the subcommand that matches your **input** — a knowledge base, a topic, a script file, or multiple sources — and the pipeline plans, generates, evaluates, and renders from there.

```bash
cs produce <subcommand> [ARGS] [OPTIONS]
```

> Looking for the old one-shot `produce -c "concept"` command? It still exists as
> [`produce-legacy`](produce-legacy.md). The same multi-agent engine
> (Producer → ScriptWriter → Video/Audio → QA → Critic → Editor → Render)
> powers both — these subcommands are input-specific front doors to it.

## Subcommands

| Subcommand | Input | Purpose |
|------------|-------|---------|
| [`paper`](#produce-paper) | a KB project | Produce a video from an existing knowledge base |
| [`topic`](#produce-topic) | a topic string | Research the topic, build a KB, then produce |
| [`script`](#produce-script) | a script file | Produce from a pre-written script |
| [`project`](#produce-project) | shards + KB + assets | Multi-source production |
| [`status`](#produce-status) | a run ID | Show status of a run |
| [`resume`](#produce-resume) | a run ID | Resume a run from its last checkpoint |
| [`list`](#produce-list) | — | List all production runs |
| [`edit`](#produce-edit) | a run ID | Edit a single scene in a run |

## Quick Start

```bash
# Research a topic end-to-end (mock, no cost)
cs produce topic "How to make French press coffee" --mock

# Produce from a knowledge base you've already built
cs produce paper kb_1c28d10264bd --live -p luma

# Produce from a script file with a budget cap
cs produce script myscript.txt --budget 15 --live

# Check on / resume a run
cs produce status 20260617_101500
cs produce resume 20260617_101500
```

## Common Production Options

`paper`, `topic`, `script`, and `project` share a common set of production options:

| Option | Description |
|--------|-------------|
| `-p, --provider TEXT` | Preferred video provider: `luma`, `higgsfield`, or `auto` |
| `--interactive / --no-interactive` | Interactive pre-production (figure selection) |
| `--live / --mock` | Use real API providers vs. a dry run (mock) |
| `-d, --duration FLOAT` | Target duration in seconds |
| `--voice TEXT` | TTS voice |
| `-l, --language TEXT` | Script/TTS language (ISO 639-1: `en`, `cs`, `es`, `fr`, `de`, `ja`, …) |
| `-s, --style TEXT` | Video style: `explainer`, `documentary`, `tutorial` |
| `-b, --budget FLOAT` | Total budget in USD |

> Note: `--provider` choices (`luma`, `higgsfield`, `auto`) and `--style`
> values (`explainer`, `documentary`, `tutorial`) differ from the
> [`produce-legacy`](produce-legacy.md) command's older option set.

---

## produce paper

Produce a video from a knowledge base project.

```bash
cs produce paper KB_ID [OPTIONS]
```

- **`KB_ID`** — the project name or ID (e.g. `kb_1c28d10264bd`). Build one first with [`kb`](kb.md) / [`document`](document.md).
- **`-c, --prompt TEXT`** — production direction/focus (here `-c` is the *prompt*, not a concept).
- Plus the [common production options](#common-production-options).

```bash
cs produce paper kb_1c28d10264bd --mock
cs produce paper kb_1c28d10264bd -c "focus on the methods section" --live -p luma -d 90
```

## produce topic

Research a topic and produce a video. Automatically researches the topic, builds a KB, then produces.

```bash
cs produce topic TOPIC_TEXT [OPTIONS]
```

- **`TOPIC_TEXT`** — the topic to research (positional).
- Plus the [common production options](#common-production-options).

```bash
cs produce topic "How to make French press coffee" --mock
cs produce topic "The history of jazz" --live -d 120 -s documentary
```

## produce script

Produce a video from a pre-written script file.

```bash
cs produce script SCRIPT_FILE [OPTIONS]
```

- **`SCRIPT_FILE`** — path to the script.
- Plus the [common production options](#common-production-options).

```bash
cs produce script myscript.txt --mock
cs produce script myscript.txt --budget 15 --live --voice nova
```

## produce project

Multi-source production from shards + KB + assets. Combines knowledge from multiple sources into a single video. **Interactive mode is the default** for project builds.

```bash
cs produce project -c PROMPT [OPTIONS]
```

- **`-c, --prompt TEXT`** — production prompt (**required**).
- **`--shards TEXT`** — shard refs to hydrate.
- **`--kb TEXT`** — KB project IDs to include.
- **`--assets TEXT`** — asset files/dirs to include.
- Plus the [common production options](#common-production-options).

```bash
cs produce project -c "Quarterly research roundup" \
  --kb kb_1c28d10264bd --kb kb_99fe... \
  --assets ./brand_assets/ --live
```

## produce status

Show the status of a production run.

```bash
cs produce status RUN_ID
```

## produce resume

Resume a production run from its last checkpoint.

```bash
cs produce resume RUN_ID [--from {plan|production|audio|assembly}]
```

- **`--from`** — optionally resume from a specific stage rather than the last checkpoint.

```bash
cs produce resume 20260617_101500
cs produce resume 20260617_101500 --from audio
```

## produce list

List all production runs.

```bash
cs produce list
```

## produce edit

Edit a specific scene in a production run — swap providers, replace assets, or redo individual scenes without affecting the rest of the production.

```bash
cs produce edit RUN_ID [OPTIONS]
```

- **`--scene TEXT`** — scene ID to edit.
- **`-p, --provider TEXT`** — new provider for the scene.
- **`--asset PATH`** — replace the scene's asset.

```bash
cs produce edit 20260617_101500 --scene scene_003 -p higgsfield
cs produce edit 20260617_101500 --scene scene_003 --asset ./new_clip.mp4
```

---

## Pipeline Stages

All `produce` subcommands feed the same multi-agent pipeline. For the full stage-by-stage breakdown (Planning → Asset Generation → Evaluation → Rendering), production tiers, output directory structure, and cost tracking, see [produce-legacy.md](produce-legacy.md#pipeline-stages) — the engine is shared.

## Integration with Other Commands

```bash
# Build the knowledge base first
cs kb create "Coffee Research"
cs kb add coffee-research --paper brewing.pdf
cs produce paper coffee-research --live

# After a run: inspect, assemble, render, upload
cs produce status <run_id>
cs figures list artifacts/runs/<run_id>
cs assemble <run_id>
cs upload youtube artifacts/runs/<run_id>/final_output.mp4 -t "My Video"
```

## See Also

- [produce-legacy.md](produce-legacy.md) — the classic one-shot `produce-legacy -c "concept"` pipeline, with the detailed stage/budget/output reference.
- [kb.md](kb.md), [document.md](document.md) — build the knowledge bases that `produce paper` / `produce project` consume.
- [resume.md](resume.md), [assemble.md](assemble.md), [render.md](render.md), [upload.md](upload.md) — post-production.
