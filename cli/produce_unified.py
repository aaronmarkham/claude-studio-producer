"""Unified produce command — single entry point for all production workflows.

Subcommands:
    cs produce paper <kb_id>           Single source → video
    cs produce topic "French press"    Research → KB → video
    cs produce project --shards ...    Multi-source synthesis
    cs produce script <file>           Pre-written script → video
    cs produce status <run_id>         Check run progress
    cs produce resume <run_id>         Resume from checkpoint
    cs produce edit <run_id>           Edit specific scenes
"""

import json
import click
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models.run_manifest import (
    RunManifest, RunStage, SourceType, SceneStatus,
    SceneManifest, AudioManifest, BudgetManifest,
)

ARTIFACTS_DIR = Path("artifacts/runs")


def _common_options(f):
    """Shared options across produce subcommands."""
    f = click.option("--budget", "-b", type=float, default=10.0,
                     help="Total budget in USD")(f)
    f = click.option("--style", "-s", default="explainer",
                     help="Video style (explainer, documentary, tutorial)")(f)
    f = click.option("--language", "-l", default="en",
                     help="Script/TTS language (ISO 639-1: en, cs, es, fr, de, ja, etc.)")(f)
    f = click.option("--voice", default="nova",
                     help="TTS voice")(f)
    f = click.option("--duration", "-d", type=float, default=60.0,
                     help="Target duration in seconds")(f)
    f = click.option("--live/--mock", default=False,
                     help="Use real API providers vs dry run")(f)
    f = click.option("--interactive/--no-interactive", default=False,
                     help="Interactive pre-production (figure selection)")(f)
    f = click.option("--provider", "-p", default="auto",
                     help="Preferred video provider (luma, higgsfield, auto)")(f)
    return f


def _init_run(source_type: SourceType, prompt: str, budget: float,
              style: str, live: bool, **kwargs) -> RunManifest:
    """Create a new run manifest and directory."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ARTIFACTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(
        run_id=run_id,
        source_type=source_type,
        stage=RunStage.INIT,
        style=style,
        live=live,
        prompt=prompt,
        budget=BudgetManifest(total=budget),
        run_dir=str(run_dir),
        **{k: v for k, v in kwargs.items() if v is not None},
    )
    manifest.save()
    return manifest


@click.group("produce")
def produce_unified_cmd():
    """Video production pipeline.

    \b
    Quick start:
      cs produce paper <kb_id> --mock
      cs produce topic "How to make French press coffee" --live
      cs produce script myscript.txt --budget 15
      cs produce status <run_id>
      cs produce resume <run_id>
    """
    pass


# === Source subcommands ===

@produce_unified_cmd.command()
@click.argument("kb_id")
@click.option("--prompt", "-c", default=None, help="Production direction/focus")
@_common_options
def paper(kb_id, prompt, budget, style, language, voice, duration, live, interactive, provider):
    """Produce video from a knowledge base project.

    KB_ID is the project name or ID (e.g., kb_1c28d10264bd).
    """
    manifest = _init_run(
        source_type=SourceType.PAPER,
        prompt=prompt or f"Create an explainer video from this research",
        budget=budget, style=style, live=live,
        kb_project=kb_id,
        language=language,
    )
    manifest.audio.voice = voice
    manifest.save()

    click.echo(f"📦 Run {manifest.run_id} initialized (paper: {kb_id})")
    click.echo(f"   Budget: ${budget:.2f} | Style: {style} | {'LIVE' if live else 'MOCK'}")
    click.echo(f"   Dir: {manifest.run_dir}")
    click.echo()

    # TODO: Wire to stage_plan → stage_produce → stage_audio → stage_assemble
    # For now, delegate to existing produce pipeline
    _run_pipeline(manifest, provider, voice, duration, interactive)


@produce_unified_cmd.command()
@click.argument("topic_text")
@_common_options
def topic(topic_text, budget, style, language, voice, duration, live, interactive, provider):
    """Research a topic and produce a video.

    Automatically researches the topic, builds a KB, then produces.
    """
    manifest = _init_run(
        source_type=SourceType.TOPIC,
        prompt=topic_text,
        budget=budget, style=style, live=live,
        language=language,
    )
    manifest.audio.voice = voice
    manifest.save()

    click.echo(f"🔬 Run {manifest.run_id} initialized (topic: {topic_text[:50]}...)")
    click.echo(f"   Budget: ${budget:.2f} | Style: {style} | {'LIVE' if live else 'MOCK'}")
    click.echo(f"   Dir: {manifest.run_dir}")
    click.echo()

    _run_pipeline(manifest, provider, voice, duration, interactive)


@produce_unified_cmd.command()
@click.option("--shards", multiple=True, help="Shard refs to hydrate")
@click.option("--kb", multiple=True, help="KB project IDs to include")
@click.option("--assets", "asset_paths", multiple=True, help="Asset files/dirs to include")
@click.option("--prompt", "-c", required=True, help="Production prompt")
@_common_options
def project(shards, kb, asset_paths, prompt, budget, style, language, voice, duration, live, interactive, provider):
    """Multi-source production from shards + KB + assets.

    Combines knowledge from multiple sources into a single video.
    Interactive mode is default for project builds.
    """
    # Default to interactive for project mode
    if not interactive:
        interactive = True

    manifest = _init_run(
        source_type=SourceType.PROJECT,
        prompt=prompt,
        budget=budget, style=style, live=live,
        shard_refs=list(shards),
        language=language,
    )
    manifest.audio.voice = voice
    manifest.save()

    click.echo(f"🧩 Run {manifest.run_id} initialized (project)")
    if shards:
        click.echo(f"   Shards: {', '.join(shards)}")
    if kb:
        click.echo(f"   KBs: {', '.join(kb)}")
    if asset_paths:
        click.echo(f"   Assets: {', '.join(asset_paths)}")
    click.echo(f"   Budget: ${budget:.2f} | Style: {style} | {'LIVE' if live else 'MOCK'}")
    click.echo(f"   Dir: {manifest.run_dir}")
    click.echo()

    _run_pipeline(manifest, provider, voice, duration, interactive)


@produce_unified_cmd.command("script")
@click.argument("script_file", type=click.Path(exists=True))
@_common_options
def script_cmd(script_file, budget, style, language, voice, duration, live, interactive, provider):
    """Produce video from a pre-written script file."""
    manifest = _init_run(
        source_type=SourceType.SCRIPT,
        prompt=f"Produce from script: {script_file}",
        budget=budget, style=style, live=live,
        script_path=str(Path(script_file).resolve()),
        language=language,
    )
    manifest.audio.voice = voice
    manifest.save()

    click.echo(f"📝 Run {manifest.run_id} initialized (script: {script_file})")
    click.echo(f"   Budget: ${budget:.2f} | Style: {style} | {'LIVE' if live else 'MOCK'}")
    click.echo(f"   Dir: {manifest.run_dir}")
    click.echo()

    _run_pipeline(manifest, provider, voice, duration, interactive)


# === Run management subcommands ===

@produce_unified_cmd.command()
@click.argument("run_id")
def status(run_id):
    """Show status of a production run."""
    manifest = RunManifest.find_run(run_id)
    if not manifest:
        # Try partial match
        candidates = sorted(ARTIFACTS_DIR.glob(f"{run_id}*/manifest.json"))
        if candidates:
            manifest = RunManifest.load(candidates[0])
        else:
            click.echo(f"❌ Run '{run_id}' not found in {ARTIFACTS_DIR}")
            return

    click.echo(manifest.summary())
    click.echo()
    click.echo(manifest.timeline())


@produce_unified_cmd.command()
@click.argument("run_id")
@click.option("--from", "from_stage", default=None,
              type=click.Choice(["plan", "production", "audio", "assembly"]),
              help="Resume from specific stage")
def resume(run_id, from_stage):
    """Resume a production run from its last checkpoint."""
    manifest = RunManifest.find_run(run_id)
    if not manifest:
        candidates = sorted(ARTIFACTS_DIR.glob(f"{run_id}*/manifest.json"))
        if candidates:
            manifest = RunManifest.load(candidates[0])
        else:
            click.echo(f"❌ Run '{run_id}' not found")
            return

    click.echo(f"🔄 Resuming run {manifest.run_id}")
    click.echo(f"   Current stage: {manifest.stage.value}")
    click.echo(f"   Scenes: {manifest.scenes_ready}/{len(manifest.scenes)} ready")

    if from_stage:
        click.echo(f"   Overriding: restart from {from_stage}")
        manifest.stage = RunStage(from_stage)
        manifest.save()

    # TODO: Wire to stage functions based on manifest.stage
    click.echo("\n⚠️  Resume execution not yet wired — manifest loaded and ready")


@produce_unified_cmd.command()
@click.argument("run_id")
@click.option("--scene", type=str, help="Scene ID to edit")
@click.option("--provider", "-p", default=None, help="New provider for scene")
@click.option("--asset", type=click.Path(exists=True), help="Replace scene asset")
def edit(run_id, scene, provider, asset):
    """Edit a specific scene in a production run.

    Swap providers, replace assets, or redo individual scenes
    without affecting the rest of the production.
    """
    manifest = RunManifest.find_run(run_id)
    if not manifest:
        candidates = sorted(ARTIFACTS_DIR.glob(f"{run_id}*/manifest.json"))
        if candidates:
            manifest = RunManifest.load(candidates[0])
        else:
            click.echo(f"❌ Run '{run_id}' not found")
            return

    if not scene:
        # Show all scenes for selection
        click.echo(f"Scenes in run {manifest.run_id}:\n")
        for s in manifest.scenes:
            icon = "✅" if s.status == SceneStatus.READY else "❌" if s.status == SceneStatus.FAILED else "⏳"
            click.echo(f"  {icon} {s.scene_id}: {s.title} ({s.provider}, ${s.cost:.2f})")
        click.echo(f"\nUse --scene <id> to edit a specific scene")
        return

    scene_manifest = manifest.get_scene(scene)
    if not scene_manifest:
        click.echo(f"❌ Scene '{scene}' not found")
        return

    if asset:
        click.echo(f"🔁 Replacing {scene} asset with {asset}")
        scene_manifest.asset_path = str(Path(asset).resolve())
        scene_manifest.status = SceneStatus.REPLACED
        scene_manifest.provider = "manual"
        scene_manifest.cost = 0.0
        manifest.save()
        click.echo(f"✅ Scene {scene} updated. Run `cs produce resume {run_id} --from assembly` to re-assemble.")
    elif provider:
        click.echo(f"🔄 Setting {scene} provider to {provider}")
        scene_manifest.provider = provider
        scene_manifest.status = SceneStatus.PENDING
        scene_manifest.attempts = 0
        scene_manifest.error = None
        manifest.save()
        click.echo(f"✅ Scene {scene} queued for regeneration. Run `cs produce resume {run_id} --from production`")


@produce_unified_cmd.command("list")
def list_runs():
    """List all production runs."""
    if not ARTIFACTS_DIR.exists():
        click.echo("No runs found.")
        return

    runs = sorted(ARTIFACTS_DIR.glob("*/manifest.json"), reverse=True)
    if not runs:
        click.echo("No runs with manifests found.")
        return

    click.echo(f"{'Run ID':<20} {'Stage':<12} {'Scenes':<10} {'Budget':<15} {'Source'}")
    click.echo("-" * 70)
    for manifest_path in runs[:20]:
        try:
            m = RunManifest.load(manifest_path)
            scenes = f"{m.scenes_ready}/{len(m.scenes)}"
            budget = f"${m.budget.spent:.2f}/${m.budget.total:.2f}"
            click.echo(f"{m.run_id:<20} {m.stage.value:<12} {scenes:<10} {budget:<15} {m.source_type.value}")
        except Exception:
            click.echo(f"{manifest_path.parent.name:<20} {'error':<12}")


# === Legacy bridge ===

def _run_pipeline(manifest: RunManifest, provider: str, voice: str,
                  duration: float, interactive: bool):
    """Execute the production pipeline with manifest checkpointing."""
    import asyncio
    from core.pipeline.runner import run_pipeline

    asyncio.run(run_pipeline(
        manifest,
        provider=provider,
        voice=voice,
        duration=duration,
        interactive=interactive,
        language=manifest.language,
    ))
