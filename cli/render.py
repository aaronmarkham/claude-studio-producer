"""Render command - Re-render EDLs from existing runs and mix video with audio"""

import os
import json
import asyncio
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

from core.renderer import FFmpegRenderer
from core.models.edit_decision import EditDecisionList, EditCandidate, EditDecision
from core.models.render import RenderConfig, AudioTrack, TrackType

console = Console()


def load_edl_from_run(run_dir: Path) -> EditDecisionList:
    """Load EDL from a run directory"""
    edl_dir = run_dir / "edl"

    # Load main EDL metadata
    edl_meta_path = edl_dir / "edit_candidates.json"
    if not edl_meta_path.exists():
        raise FileNotFoundError(f"No EDL found at {edl_meta_path}")

    with open(edl_meta_path) as f:
        edl_meta = json.load(f)

    # Load each candidate
    candidates = []
    for cand_info in edl_meta["candidates"]:
        cand_path = edl_dir / f"{cand_info['candidate_id']}.json"
        if cand_path.exists():
            with open(cand_path) as f:
                cand_data = json.load(f)

            # Convert decisions to EditDecision objects
            decisions = []
            for d in cand_data.get("decisions", []):
                decisions.append(EditDecision(
                    scene_id=d["scene_id"],
                    selected_variation=d.get("selected_variation", 0),
                    video_url=d.get("video_url"),
                    audio_url=d.get("audio_url"),
                    in_point=d.get("in_point", 0.0),
                    out_point=d.get("out_point"),
                    transition_in=d.get("transition_in", "cut"),
                    transition_in_duration=d.get("transition_in_duration", 0.0),
                    transition_out=d.get("transition_out", "cut"),
                    transition_out_duration=d.get("transition_out_duration", 0.0),
                    start_time=d.get("start_time", 0.0),
                    duration=d.get("duration", 5.0),
                    # Text overlay fields
                    text_overlay=d.get("text_overlay"),
                    text_position=d.get("text_position", "center"),
                    text_style=d.get("text_style", "title"),
                    text_start_time=d.get("text_start_time"),
                    text_duration=d.get("text_duration"),
                    notes=d.get("notes")
                ))

            candidates.append(EditCandidate(
                candidate_id=cand_data["candidate_id"],
                name=cand_data["name"],
                style=cand_data["style"],
                decisions=decisions,
                total_duration=cand_data.get("total_duration", 0.0),
                estimated_quality=cand_data.get("estimated_quality", 0.0),
                description=cand_data.get("description", "")
            ))

    return EditDecisionList(
        edl_id=edl_meta["edl_id"],
        project_name=edl_meta["project_name"],
        candidates=candidates,
        recommended_candidate_id=edl_meta["recommended_candidate_id"],
        total_scenes=edl_meta["total_scenes"]
    )


@click.group()
def render_cmd():
    """
    Render commands - render EDLs or mix video with audio.

    \b
    Commands:
        render edl <RUN_ID>    Render a production run's EDL
        render mix <VIDEO>     Mix video with TTS or audio file

    Examples:

        # Render a production run
        claude-studio render edl 20260107_224324

        # Mix video with TTS audio
        claude-studio render mix video.mp4 --text "Hello world"
    """
    pass


@click.command("edl")
@click.argument("run_id")
@click.option("--candidate", "-c", help="Candidate ID to render (default: recommended)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--list-candidates", "-l", is_flag=True, help="List available candidates")
def edl_cmd(run_id: str, candidate: str, output: str, list_candidates: bool):
    """
    Render a final video from an existing production run.

    RUN_ID is the run directory name (e.g., 20260107_224324)

    Examples:

        # List available edit candidates
        claude-studio render edl 20260107_224324 --list-candidates

        # Render the recommended candidate
        claude-studio render edl 20260107_224324

        # Render a specific candidate
        claude-studio render edl 20260107_224324 -c creative_cut

        # Render to a specific output file
        claude-studio render edl 20260107_224324 -o my_video.mp4
    """
    # Find run directory
    run_dir = Path("artifacts/runs") / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found: {run_dir}[/red]")
        return

    # Load EDL
    try:
        edl = load_edl_from_run(run_dir)
    except Exception as e:
        console.print(f"[red]Failed to load EDL: {e}[/red]")
        return

    # List candidates mode
    if list_candidates:
        console.print(f"\n[bold]Edit Candidates for {run_id}[/bold]\n")
        table = Table(box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Style")
        table.add_column("Duration")
        table.add_column("Quality")
        table.add_column("Recommended")

        for c in edl.candidates:
            is_rec = "*" if c.candidate_id == edl.recommended_candidate_id else ""
            table.add_row(
                c.candidate_id,
                c.name,
                c.style,
                f"{c.total_duration:.1f}s",
                f"{c.estimated_quality:.0f}",
                is_rec
            )

        console.print(table)
        return

    # Select candidate
    candidate_id = candidate or edl.recommended_candidate_id
    console.print(f"[cyan]Rendering candidate: {candidate_id}[/cyan]")

    # Check videos exist
    selected = None
    for c in edl.candidates:
        if c.candidate_id == candidate_id:
            selected = c
            break

    if not selected:
        console.print(f"[red]Candidate '{candidate_id}' not found[/red]")
        console.print(f"Available: {[c.candidate_id for c in edl.candidates]}")
        return

    # Show what videos we'll use
    console.print(f"\n[bold]Videos in edit:[/bold]")
    all_exist = True
    for d in selected.decisions:
        video_path = d.video_url
        if video_path:
            # Make path absolute if relative
            if not os.path.isabs(video_path):
                video_path = os.path.abspath(video_path)

            exists = os.path.exists(video_path)
            status = "[green]OK[/green]" if exists else "[red]MISSING[/red]"
            console.print(f"  {status} {d.scene_id}: {video_path}")
            if not exists:
                all_exist = False
        else:
            console.print(f"  [yellow]?[/yellow] {d.scene_id}: No video URL")
            all_exist = False

    if not all_exist:
        console.print("\n[yellow]Warning: Some videos are missing[/yellow]")

    # Render
    console.print("\n[bold]Rendering...[/bold]")

    try:
        result = asyncio.run(_render_edl(
            edl=edl,
            candidate_id=candidate_id,
            run_dir=run_dir,
            output_path=output
        ))

        if result.success:
            console.print(f"\n[green]Render complete![/green]")
            console.print(f"  Output: {result.output_path}")
            if result.duration:
                console.print(f"  Duration: {result.duration:.1f}s")
            if result.file_size:
                size_mb = result.file_size / (1024 * 1024)
                console.print(f"  Size: {size_mb:.1f} MB")
            console.print(f"  Render time: {result.render_time:.1f}s")
        else:
            console.print(f"\n[red]Render failed: {result.error_message}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


async def _render_edl(
    edl: EditDecisionList,
    candidate_id: str,
    run_dir: Path,
    output_path: str = None
) -> 'RenderResult':
    """Render the EDL"""
    from core.models.render import RenderResult

    # Setup renderer
    render_dir = run_dir / "renders"
    render_dir.mkdir(exist_ok=True)

    renderer = FFmpegRenderer(output_dir=str(render_dir))

    # Check FFmpeg
    ffmpeg_check = await renderer.check_ffmpeg_installed()
    if not ffmpeg_check["installed"]:
        return RenderResult(
            success=False,
            error_message="FFmpeg not installed"
        )

    # Render
    result = await renderer.render(
        edl=edl,
        candidate_id=candidate_id,
        audio_tracks=[],
        run_id=run_dir.name
    )

    # Copy to custom output path if specified
    if output_path and result.success and result.output_path:
        import shutil
        shutil.copy(result.output_path, output_path)
        result.output_path = output_path

    return result


@click.command("mix")
@click.argument("video_file", type=click.Path(exists=True))
@click.option("--text", "-t", help="Text to convert to speech (TTS)")
@click.option("--audio", "-a", type=click.Path(exists=True), help="Audio file to mix with video")
@click.option("--voice", "-v", default="Rachel", help="Voice ID for TTS (default: Rachel)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--volume", default=0.0, help="Audio volume adjustment in dB (default: 0)")
def mix_cmd(video_file: str, text: str, audio: str, voice: str, output: str, volume: float):
    """
    Mix a video file with TTS-generated audio or an existing audio file.

    This command combines a video with audio, useful for testing the
    video+audio pipeline without running the full production workflow.

    Examples:

        # Generate TTS from text and mix with video
        claude-studio render mix video.mp4 --text "Hello world, this is a test."

        # Mix video with an existing audio file
        claude-studio render mix video.mp4 --audio narration.mp3

        # Specify voice and output file
        claude-studio render mix video.mp4 -t "Welcome to our demo" -v Adam -o final.mp4
    """
    if not text and not audio:
        console.print("[red]Error: Must provide either --text for TTS or --audio file[/red]")
        return

    if text and audio:
        console.print("[yellow]Warning: Both --text and --audio provided. Using --audio file.[/yellow]")

    asyncio.run(_mix_video_audio(
        video_file=video_file,
        text=text,
        audio_file=audio,
        voice_id=voice,
        output_path=output,
        volume_db=volume
    ))


async def _mix_video_audio(
    video_file: str,
    text: str = None,
    audio_file: str = None,
    voice_id: str = "Rachel",
    output_path: str = None,
    volume_db: float = 0.0
):
    """Mix video with audio (TTS or file)"""
    from core.models.audio import VoiceStyle

    video_path = Path(video_file).resolve()

    # Determine output path
    if output_path:
        out_path = Path(output_path)
    else:
        out_path = video_path.parent / f"{video_path.stem}_mixed.mp4"

    console.print(f"[cyan]Video:[/cyan] {video_path}")

    # Get or generate audio
    audio_path = None
    temp_audio_file = None

    if audio_file:
        # Use provided audio file
        audio_path = Path(audio_file).resolve()
        console.print(f"[cyan]Audio:[/cyan] {audio_path}")
    elif text:
        # Generate TTS
        console.print(f"[cyan]Generating TTS:[/cyan] \"{text[:50]}{'...' if len(text) > 50 else ''}\"")
        console.print(f"[cyan]Voice:[/cyan] {voice_id}")

        # Check for TTS provider
        import os as _os
        if not _os.getenv("ELEVENLABS_API_KEY") and not _os.getenv("OPENAI_API_KEY"):
            console.print("[red]Error: No TTS provider configured.[/red]")
            console.print("Set ELEVENLABS_API_KEY or OPENAI_API_KEY environment variable.")
            return

        # Use AudioGeneratorAgent for TTS
        from agents.audio_generator import AudioGeneratorAgent

        audio_agent = AudioGeneratorAgent()
        result = await audio_agent.generate_voiceover(
            text=text,
            voice_style=VoiceStyle.PROFESSIONAL,
            voice_id=voice_id
        )

        if result.audio.audio_data:
            # Save audio data to temp file
            temp_audio_file = tempfile.NamedTemporaryFile(
                suffix=f".{result.audio.format or 'mp3'}",
                delete=False
            )
            temp_audio_file.write(result.audio.audio_data)
            temp_audio_file.close()
            audio_path = Path(temp_audio_file.name)
            console.print(f"[green]TTS generated:[/green] {result.audio.duration:.1f}s")
        else:
            console.print("[red]Error: TTS generation failed - no audio data returned[/red]")
            return

    # Check FFmpeg
    renderer = FFmpegRenderer(output_dir=str(out_path.parent))
    ffmpeg_check = await renderer.check_ffmpeg_installed()
    if not ffmpeg_check["installed"]:
        console.print("[red]Error: FFmpeg not installed[/red]")
        if temp_audio_file:
            Path(temp_audio_file.name).unlink(missing_ok=True)
        return

    console.print("\n[bold]Mixing video and audio...[/bold]")

    # Use FFmpeg to mix video with audio
    try:
        result = await renderer.mix_audio(
            video_path=str(video_path),
            audio_tracks=[
                AudioTrack(
                    path=str(audio_path),
                    start_time=0.0,
                    volume_db=volume_db,
                    track_type=TrackType.VOICEOVER
                )
            ],
            output_path=str(out_path)
        )

        if result.success:
            console.print(f"\n[green]Mix complete![/green]")
            console.print(f"  Output: {result.output_path}")
            if result.duration:
                console.print(f"  Duration: {result.duration:.1f}s")
            if result.file_size:
                size_mb = result.file_size / (1024 * 1024)
                console.print(f"  Size: {size_mb:.1f} MB")
        else:
            console.print(f"\n[red]Mix failed: {result.error_message}[/red]")

    except Exception as e:
        console.print(f"[red]Error mixing: {e}[/red]")
        raise
    finally:
        # Clean up temp file
        if temp_audio_file:
            Path(temp_audio_file.name).unlink(missing_ok=True)


# Register subcommands
render_cmd.add_command(edl_cmd, name="edl")
render_cmd.add_command(mix_cmd, name="mix")
