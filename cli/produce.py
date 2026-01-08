"""Produce command - Main entry point for video production"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich import box

from core.claude_client import ClaudeClient
from core.budget import ProductionTier, BudgetTracker
from core.models.audio import AudioTier
from core.models.edit_decision import EditDecisionList, ExportFormat
from core.providers import MockVideoProvider
from core.providers.base import VideoProviderConfig, AudioProviderConfig, ProviderType

console = Console()


def get_video_provider(provider_name: str, live: bool):
    """Get video provider instance based on name and mode"""
    if not live:
        console.print("[dim]Using MOCK video provider (--mock mode)[/dim]")
        return MockVideoProvider(), "mock"

    provider_name = provider_name.lower()

    if provider_name == "luma":
        api_key = os.getenv("LUMA_API_KEY")
        if not api_key:
            console.print("[yellow]LUMA_API_KEY not set - falling back to mock[/yellow]")
            return MockVideoProvider(), "mock"
        from core.providers.video.luma import LumaProvider
        console.print("[green]Using LIVE provider: Luma[/green]")
        return LumaProvider(), "luma"

    elif provider_name == "runway":
        api_key = os.getenv("RUNWAY_API_KEY")
        if not api_key:
            console.print("[yellow]RUNWAY_API_KEY not set - falling back to mock[/yellow]")
            return MockVideoProvider(), "mock"
        from core.providers.video.runway import RunwayProvider
        config = VideoProviderConfig(
            provider_type=ProviderType.RUNWAY,
            api_key=api_key,
            timeout=300
        )
        console.print("[green]Using LIVE provider: Runway[/green]")
        return RunwayProvider(config=config), "runway"

    elif provider_name == "mock":
        console.print("[dim]Using MOCK video provider[/dim]")
        return MockVideoProvider(), "mock"

    else:
        console.print(f"[yellow]Unknown provider '{provider_name}' - using mock[/yellow]")
        return MockVideoProvider(), "mock"


def get_audio_provider(live: bool):
    """Get audio provider instance"""
    if not live:
        return None, "mock"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[yellow]OPENAI_API_KEY not set - using mock audio[/yellow]")
        return None, "mock"

    from core.providers.audio.openai_tts import OpenAITTSProvider
    config = AudioProviderConfig(api_key=api_key, timeout=60)
    console.print("[green]Using LIVE audio: OpenAI TTS[/green]")
    return OpenAITTSProvider(config=config, model="tts-1"), "openai_tts"


@click.command()
@click.option("--concept", "-c", required=True, help="Video concept description")
@click.option("--budget", "-b", type=float, default=10.0, help="Total budget in USD")
@click.option("--duration", "-d", type=float, default=30.0, help="Target video duration in seconds")
@click.option("--audio-tier", type=click.Choice(["none", "music_only", "simple_overlay", "time_synced"]),
              default="none", help="Audio production tier")
@click.option("--provider", "-p", type=click.Choice(["luma", "runway", "mock"]),
              default="luma", help="Video provider to use")
@click.option("--live", is_flag=True, help="Use live API providers (costs real money!)")
@click.option("--mock", "use_mock", is_flag=True, help="Use mock providers (default)")
@click.option("--variations", "-v", type=int, default=1, help="Number of video variations per scene")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory (default: artifacts/runs/<run_id>)")
@click.option("--run-id", help="Custom run ID (default: auto-generated timestamp)")
@click.option("--debug", is_flag=True, help="Enable debug output")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def produce_cmd(
    concept: str,
    budget: float,
    duration: float,
    audio_tier: str,
    provider: str,
    live: bool,
    use_mock: bool,
    variations: int,
    output_dir: Optional[str],
    run_id: Optional[str],
    debug: bool,
    as_json: bool
):
    """
    Run the full video production pipeline.

    Examples:

        # Quick 5-second test with mock providers
        claude-studio produce -c "Logo reveal for TechCorp" -d 5 --mock

        # Live production with Luma
        claude-studio produce -c "Product demo for mobile app" -b 15 -d 30 --live -p luma

        # Full production with audio
        claude-studio produce -c "Tutorial video" -b 50 -d 60 --audio-tier simple_overlay --live
    """
    # Determine mode - mock is default unless --live is specified
    use_live = live and not use_mock

    # Generate run ID
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    # Setup output directory
    if output_dir:
        run_dir = Path(output_dir)
    else:
        run_dir = Path("artifacts/runs") / run_id

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "scenes").mkdir(exist_ok=True)
    (run_dir / "videos").mkdir(exist_ok=True)
    (run_dir / "audio").mkdir(exist_ok=True)
    (run_dir / "edl").mkdir(exist_ok=True)
    (run_dir / "renders").mkdir(exist_ok=True)

    # Parse audio tier
    audio_tier_map = {
        "none": AudioTier.NONE,
        "music_only": AudioTier.MUSIC_ONLY,
        "simple_overlay": AudioTier.SIMPLE_OVERLAY,
        "time_synced": AudioTier.TIME_SYNCED,
    }
    audio_tier_enum = audio_tier_map[audio_tier]

    # Show production header
    if not as_json:
        console.print(Panel.fit(
            f"[bold blue]Claude Studio Producer[/bold blue]\n"
            f"Run ID: {run_id}",
            border_style="blue"
        ))
        console.print()

        # Production parameters table
        params_table = Table(box=box.SIMPLE, show_header=False)
        params_table.add_column("Param", style="cyan")
        params_table.add_column("Value")
        params_table.add_row("Concept", concept[:60] + "..." if len(concept) > 60 else concept)
        params_table.add_row("Budget", f"${budget:.2f}")
        params_table.add_row("Duration", f"{duration}s")
        params_table.add_row("Audio Tier", audio_tier)
        params_table.add_row("Provider", provider)
        params_table.add_row("Mode", "[green]LIVE[/green]" if use_live else "[dim]MOCK[/dim]")
        params_table.add_row("Variations", str(variations))
        params_table.add_row("Output", str(run_dir))
        console.print(params_table)
        console.print()

    # Run the production pipeline
    try:
        result = asyncio.run(_run_production(
            concept=concept,
            budget=budget,
            duration=duration,
            audio_tier=audio_tier_enum,
            provider_name=provider,
            use_live=use_live,
            variations=variations,
            run_dir=run_dir,
            run_id=run_id,
            debug=debug,
            as_json=as_json
        ))

        if as_json:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            _print_summary(result, run_dir)

        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        if debug:
            import traceback
            traceback.print_exc()
        console.print(f"[red]Production failed: {e}[/red]")
        sys.exit(1)


async def _run_production(
    concept: str,
    budget: float,
    duration: float,
    audio_tier: AudioTier,
    provider_name: str,
    use_live: bool,
    variations: int,
    run_dir: Path,
    run_id: str,
    debug: bool,
    as_json: bool
) -> dict:
    """Run the production pipeline"""

    from agents.producer import ProducerAgent
    from agents.script_writer import ScriptWriterAgent
    from agents.video_generator import VideoGeneratorAgent
    from agents.audio_generator import AudioGeneratorAgent
    from agents.qa_verifier import QAVerifierAgent
    from agents.critic import CriticAgent, SceneResult
    from agents.editor import EditorAgent

    # Initialize tracking
    metadata = {
        "run_id": run_id,
        "concept": concept,
        "budget": budget,
        "duration": duration,
        "audio_tier": audio_tier.value,
        "provider": provider_name,
        "live_mode": use_live,
        "start_time": datetime.now().isoformat(),
        "stages": {},
        "costs": {"video": 0.0, "audio": 0.0, "total": 0.0}
    }

    # Get providers
    video_provider, actual_video_provider = get_video_provider(provider_name, use_live)
    audio_provider, actual_audio_provider = get_audio_provider(use_live)
    metadata["actual_video_provider"] = actual_video_provider
    metadata["actual_audio_provider"] = actual_audio_provider

    # Initialize agents
    claude = ClaudeClient()
    producer = ProducerAgent(claude_client=claude)
    script_writer = ScriptWriterAgent(claude_client=claude)
    video_generator = VideoGeneratorAgent(provider=video_provider, num_variations=variations)
    audio_generator = AudioGeneratorAgent(claude_client=claude, audio_provider=audio_provider)
    qa_verifier = QAVerifierAgent(claude_client=claude)
    critic = CriticAgent(claude_client=claude)
    editor = EditorAgent(claude_client=claude)

    # Calculate appropriate scene count based on duration
    # Typical scene is 5-10 seconds
    scene_duration_avg = 7.0
    num_scenes = max(1, min(6, int(duration / scene_duration_avg)))

    if not as_json:
        console.print(f"[cyan]Target: {num_scenes} scenes for {duration}s video[/cyan]\n")

    results = {
        "success": False,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "scenes": [],
        "videos": {},
        "costs": metadata["costs"],
        "metadata": metadata
    }

    # Stage 1: Producer - Create pilot strategy
    if not as_json:
        console.print("[bold]Stage 1:[/bold] Producer - Planning production...")

    pilots = await producer.analyze_and_plan(concept, budget)
    if not pilots:
        raise RuntimeError("No pilot strategies generated")

    pilot = pilots[0]  # Use first pilot
    metadata["stages"]["producer"] = {
        "pilot_tier": pilot.tier.value,
        "allocated_budget": pilot.allocated_budget
    }

    if not as_json:
        console.print(f"  Selected: {pilot.tier.value} tier, ${pilot.allocated_budget:.2f} budget")

    # Stage 2: Script Writer - Generate scenes
    if not as_json:
        console.print("\n[bold]Stage 2:[/bold] Script Writer - Creating scenes...")

    scenes = await script_writer.create_script(
        video_concept=concept,
        production_tier=pilot.tier,
        target_duration=duration,
        num_scenes=num_scenes
    )

    if not scenes:
        raise RuntimeError("No scenes generated")

    results["scenes"] = [s.scene_id for s in scenes]
    metadata["stages"]["script_writer"] = {
        "num_scenes": len(scenes),
        "total_duration": sum(s.duration for s in scenes)
    }

    # Save scenes
    for scene in scenes:
        scene_path = run_dir / "scenes" / f"{scene.scene_id}.json"
        with open(scene_path, 'w') as f:
            json.dump({
                "scene_id": scene.scene_id,
                "title": scene.title,
                "description": scene.description,
                "duration": scene.duration,
                "visual_elements": scene.visual_elements,
                "voiceover_text": scene.voiceover_text
            }, f, indent=2)

    if not as_json:
        console.print(f"  Created {len(scenes)} scenes ({sum(s.duration for s in scenes):.1f}s total)")

    # Stage 3: Video Generator
    if not as_json:
        console.print("\n[bold]Stage 3:[/bold] Video Generator - Creating videos...")

    video_candidates = {}
    total_video_cost = 0.0

    for scene in scenes:
        if not as_json:
            console.print(f"  Generating {scene.scene_id}...", end=" ")

        videos = await video_generator.generate_scene(
            scene=scene,
            production_tier=pilot.tier,
            budget_limit=pilot.allocated_budget / len(scenes),
            num_variations=variations
        )

        video_candidates[scene.scene_id] = videos
        scene_cost = sum(v.generation_cost for v in videos)
        total_video_cost += scene_cost

        # Download videos if they have URLs
        for i, video in enumerate(videos):
            if video.video_url and video.video_url.startswith("http"):
                local_path = run_dir / "videos" / f"{scene.scene_id}_v{i}.mp4"
                success = await video_provider.download_video(video.video_url, str(local_path))
                if success:
                    video.video_url = str(local_path)

        if not as_json:
            console.print(f"[green]{len(videos)} variations (${scene_cost:.2f})[/green]")

    results["videos"] = {k: len(v) for k, v in video_candidates.items()}
    metadata["costs"]["video"] = total_video_cost
    metadata["costs"]["total"] += total_video_cost
    metadata["stages"]["video_generator"] = {
        "num_videos": sum(len(v) for v in video_candidates.values()),
        "cost": total_video_cost
    }

    # Stage 4: Audio Generator (if enabled)
    scene_audio = []
    if audio_tier != AudioTier.NONE:
        if not as_json:
            console.print("\n[bold]Stage 4:[/bold] Audio Generator - Creating audio...")

        scene_audio = await audio_generator.run(
            scenes=scenes,
            audio_tier=audio_tier,
            budget_limit=budget * 0.2
        )

        audio_cost = len(scene_audio) * 0.05  # Estimate
        metadata["costs"]["audio"] = audio_cost
        metadata["costs"]["total"] += audio_cost
    else:
        if not as_json:
            console.print("\n[bold]Stage 4:[/bold] Audio Generator - [dim]Skipped (tier=none)[/dim]")

    # Stage 5: QA Verifier
    if not as_json:
        console.print("\n[bold]Stage 5:[/bold] QA Verifier - Checking quality...")

    qa_results = {}
    passed_count = 0
    total_count = 0

    for scene in scenes:
        videos = video_candidates.get(scene.scene_id, [])
        scene_qa = []
        for video in videos:
            qa = await qa_verifier.verify_video(
                scene=scene,
                generated_video=video,
                original_request=concept,
                production_tier=pilot.tier
            )
            video.quality_score = qa.overall_score
            scene_qa.append(qa)
            total_count += 1
            if qa.passed:
                passed_count += 1
        qa_results[scene.scene_id] = scene_qa

    metadata["stages"]["qa_verifier"] = {
        "total": total_count,
        "passed": passed_count,
        "pass_rate": passed_count / total_count if total_count > 0 else 0
    }

    if not as_json:
        console.print(f"  Pass rate: {passed_count}/{total_count} ({100*passed_count/total_count:.0f}%)")

    # Stage 6: Critic evaluation
    if not as_json:
        console.print("\n[bold]Stage 6:[/bold] Critic - Evaluating results...")

    scene_results = []
    for scene in scenes:
        videos = video_candidates.get(scene.scene_id, [])
        if videos:
            video = videos[0]
            scene_results.append(SceneResult(
                scene_id=scene.scene_id,
                description=scene.description,
                video_url=video.video_url,
                qa_score=video.quality_score or 0.0,
                generation_cost=video.generation_cost
            ))

    evaluation = await critic.evaluate_pilot(
        original_request=concept,
        pilot=pilot,
        scene_results=scene_results,
        budget_spent=metadata["costs"]["total"],
        budget_allocated=pilot.allocated_budget
    )

    metadata["stages"]["critic"] = {
        "approved": evaluation.approved,
        "score": evaluation.critic_score
    }

    if not as_json:
        status = "[green]APPROVED[/green]" if evaluation.approved else "[red]REJECTED[/red]"
        console.print(f"  Status: {status} (score: {evaluation.critic_score}/100)")

    # Stage 7: Editor
    if not as_json:
        console.print("\n[bold]Stage 7:[/bold] Editor - Creating edit decision list...")

    edl = await editor.run(
        scenes=scenes,
        video_candidates=video_candidates,
        qa_results=qa_results,
        original_request=concept,
        num_candidates=1  # Just one for now
    )

    # Save EDL
    edl_path = run_dir / "edl" / "edit_decision.json"
    with open(edl_path, 'w') as f:
        json.dump({
            "edl_id": edl.edl_id,
            "project_name": edl.project_name,
            "recommended": edl.recommended_candidate_id,
            "candidates": len(edl.candidates)
        }, f, indent=2)

    metadata["stages"]["editor"] = {
        "edl_id": edl.edl_id,
        "candidates": len(edl.candidates)
    }

    if not as_json:
        console.print(f"  Created EDL with {len(edl.candidates)} candidate(s)")

    # Stage 8: Renderer (check if FFmpeg available)
    if not as_json:
        console.print("\n[bold]Stage 8:[/bold] Renderer - Creating final video...")

    from core.renderer import FFmpegRenderer
    renderer = FFmpegRenderer(output_dir=str(run_dir / "renders"))
    ffmpeg_check = await renderer.check_ffmpeg_installed()

    if ffmpeg_check["installed"]:
        render_result = await renderer.render(edl=edl, audio_tracks=[], run_id=run_id)
        if render_result.success:
            results["output_video"] = render_result.output_path
            if not as_json:
                console.print(f"  [green]Output: {render_result.output_path}[/green]")
        else:
            if not as_json:
                console.print(f"  [yellow]{render_result.error_message}[/yellow]")
    else:
        if not as_json:
            console.print("  [dim]FFmpeg not installed - skipping render[/dim]")

    # Finalize
    metadata["end_time"] = datetime.now().isoformat()
    metadata["status"] = "completed"

    # Save metadata
    with open(run_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

    results["success"] = True
    results["metadata"] = metadata

    return results


def _print_summary(result: dict, run_dir: Path):
    """Print production summary"""
    console.print()
    console.print("=" * 60)
    console.print("[bold green]PRODUCTION COMPLETE[/bold green]")
    console.print("=" * 60)

    metadata = result.get("metadata", {})

    # Providers used
    video_prov = metadata.get("actual_video_provider", "unknown")
    audio_prov = metadata.get("actual_audio_provider", "unknown")
    console.print(f"\nProviders: Video={video_prov.upper()}, Audio={audio_prov.upper()}")

    # Costs
    costs = metadata.get("costs", {})
    video_cost = costs.get("video", 0)
    audio_cost = costs.get("audio", 0)
    total_cost = costs.get("total", 0)

    if video_prov == "mock":
        console.print(f"Costs: ${total_cost:.2f} [dim](SIMULATED - no actual charges)[/dim]")
    else:
        console.print(f"Costs: ${total_cost:.2f} (Video: ${video_cost:.2f}, Audio: ${audio_cost:.2f})")

    # Stats
    stages = metadata.get("stages", {})
    console.print(f"\nScenes: {stages.get('script_writer', {}).get('num_scenes', 0)}")
    console.print(f"Videos: {stages.get('video_generator', {}).get('num_videos', 0)}")

    qa = stages.get("qa_verifier", {})
    if qa:
        console.print(f"QA Pass Rate: {qa.get('passed', 0)}/{qa.get('total', 0)}")

    console.print(f"\nOutput: {run_dir}")
    console.print("=" * 60)
