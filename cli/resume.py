#!/usr/bin/env python3
"""
Resume CLI - Continue a production from a specific run directory
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List

import click
from rich.console import Console
from rich.panel import Panel

from core.claude_client import ClaudeClient
from core.budget import ProductionTier
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from agents.qa_verifier import QAVerifierAgent, QAResult
from agents.critic import CriticAgent, SceneResult, PilotResults
from agents.producer import PilotStrategy
from agents.editor import EditorAgent

console = Console()


@click.command()
@click.argument("run_id")
@click.option("--live", is_flag=True, help="Use live QA with Claude Vision (vs mock mode)")
@click.option("--skip-qa", is_flag=True, help="Skip QA verification (use if already completed)")
@click.option("--skip-critic", is_flag=True, help="Skip critic analysis")
@click.option("--skip-editor", is_flag=True, help="Skip EDL creation")
def resume_cmd(run_id: str, live: bool, skip_qa: bool, skip_critic: bool, skip_editor: bool):
    """
    Resume a production from where it stopped.

    \b
    Examples:
      claude-studio resume 20260131_162250
      claude-studio resume 20260131_162250 --live
      claude-studio resume latest --skip-qa

    \b
    This picks up from where the pipeline stopped and continues:
      - QA verification (with frame extraction)
      - Critic analysis
      - EDL creation

    The run directory must contain:
      - scenes/*.json (scene specifications)
      - videos/*.mp4 (generated videos)
      - memory.json (run metadata)
    """
    asyncio.run(_resume(run_id, live, skip_qa, skip_critic, skip_editor))


async def _resume(run_id: str, use_live: bool, skip_qa: bool, skip_critic: bool, skip_editor: bool):
    """Resume production implementation"""

    # Convert run_id to path
    if run_id == "latest":
        # Find most recent run
        runs_dir = Path("artifacts/runs")
        if not runs_dir.exists():
            console.print("[red]No runs directory found[/red]")
            sys.exit(1)

        run_dirs = sorted([d for d in runs_dir.iterdir() if d.is_dir()], reverse=True)
        if not run_dirs:
            console.print("[red]No runs found[/red]")
            sys.exit(1)

        run_path = run_dirs[0]
        console.print(f"[dim]Using latest run: {run_path.name}[/dim]")
    else:
        run_path = Path(run_id)
        if not run_path.exists():
            # Try as run ID in artifacts/runs
            run_path = Path("artifacts/runs") / run_id

    if not run_path.exists():
        console.print(f"[red]Run directory not found: {run_path}[/red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold cyan]Resuming Production: {run_path.name}[/bold cyan]",
        border_style="cyan"
    ))

    # Load run metadata
    memory_path = run_path / "memory.json"
    if not memory_path.exists():
        console.print("[red]memory.json not found in run directory[/red]")
        sys.exit(1)

    with open(memory_path, 'r') as f:
        memory = json.load(f)

    concept = memory['concept']
    budget_total = memory['budget_total']
    current_stage = memory.get('current_stage', 'unknown')

    # Calculate actual budget spent from timeline (budget_spent field may be stale)
    budget_spent = 0.0
    for stage_entry in memory.get('timeline', []):
        if 'details' in stage_entry and 'cost' in stage_entry['details']:
            budget_spent += stage_entry['details']['cost']

    console.print(f"Concept: {concept}")
    console.print(f"Budget: ${budget_spent:.2f} / ${budget_total:.2f} spent")
    console.print(f"Current stage: {current_stage}")
    console.print()

    # Load scenes
    scenes_dir = run_path / "scenes"
    if not scenes_dir.exists():
        console.print("[red]scenes directory not found[/red]")
        sys.exit(1)

    scenes: List[Scene] = []
    for scene_file in sorted(scenes_dir.glob("scene_*.json")):
        with open(scene_file, 'r') as f:
            scene_data = json.load(f)
            scene = Scene(
                scene_id=scene_data['scene_id'],
                title=scene_data['title'],
                description=scene_data['description'],
                duration=scene_data['duration'],
                visual_elements=scene_data.get('visual_elements', []),
                audio_notes=scene_data.get('audio_notes', ''),
                transition_in=scene_data.get('transition_in', 'cut'),
                transition_out=scene_data.get('transition_out', 'cut'),
                prompt_hints=scene_data.get('prompt_hints', []),
                voiceover_text=scene_data.get('voiceover_text', None)
            )
            scenes.append(scene)

    console.print(f"[green]✓[/green] Loaded {len(scenes)} scenes")

    # Load videos
    videos_dir = run_path / "videos"
    if not videos_dir.exists():
        console.print("[red]videos directory not found[/red]")
        sys.exit(1)

    video_candidates: Dict[str, List[GeneratedVideo]] = {}

    for video_file in sorted(videos_dir.glob("scene_*_v*.mp4")):
        # Parse filename: scene_1_v0.mp4
        parts = video_file.stem.split('_')
        scene_id = f"{parts[0]}_{parts[1]}"  # scene_1
        variation_id = int(parts[2][1:])  # 0 from v0

        # Get actual video duration using ffprobe
        import subprocess
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(video_file)],
            capture_output=True,
            text=True
        )
        actual_duration = float(result.stdout.strip()) if result.returncode == 0 else 5.0

        # Create GeneratedVideo with CORRECT metadata (no incorrect chain metadata)
        video = GeneratedVideo(
            scene_id=scene_id,
            variation_id=variation_id,
            video_url=str(video_file),  # Local path
            thumbnail_url="",
            duration=actual_duration,
            generation_cost=0.0,  # Already spent
            provider="luma",
            metadata={},
            # Chain metadata - leave as defaults (None/0) to force QA verifier to probe actual file
            total_video_duration=None,
            new_content_start=0.0,
            is_chained=False,
            contains_previous=False,
            chain_group=None
        )

        if scene_id not in video_candidates:
            video_candidates[scene_id] = []
        video_candidates[scene_id].append(video)

    total_videos = sum(len(vids) for vids in video_candidates.values())
    console.print(f"[green]✓[/green] Loaded {total_videos} videos")
    console.print()

    # Get production tier
    pilot_tier_str = memory['timeline'][0]['details'].get('pilot_tier', 'photorealistic')
    pilot_tier = ProductionTier(pilot_tier_str)

    # Initialize agents
    claude = ClaudeClient()
    qa_verifier = QAVerifierAgent(claude_client=claude, mock_mode=not use_live)
    critic = CriticAgent(claude_client=claude)
    editor = EditorAgent(claude_client=claude)

    # --- QA Verification ---
    qa_results = {}
    qa_dir = run_path / "qa"
    qa_dir.mkdir(exist_ok=True)

    # Check if QA results already exist
    existing_qa_files = list(qa_dir.glob("scene_*_v*_qa.json"))
    if existing_qa_files and not skip_qa:
        console.print(f"[yellow]Found {len(existing_qa_files)} existing QA results[/yellow]")
        console.print("Loading existing QA data...")

        # Load existing QA results
        for qa_file in existing_qa_files:
            with open(qa_file, 'r') as f:
                qa_data = json.load(f)
                scene_id = qa_data['scene_id']

                # Reconstruct QAResult
                qa = QAResult(
                    scene_id=scene_id,
                    video_url=qa_data['video_url'],
                    overall_score=qa_data['overall_score'],
                    visual_accuracy=qa_data['visual_accuracy'],
                    style_consistency=qa_data['style_consistency'],
                    technical_quality=qa_data['technical_quality'],
                    narrative_fit=qa_data['narrative_fit'],
                    issues=qa_data['issues'],
                    suggestions=qa_data['suggestions'],
                    passed=qa_data['passed'],
                    threshold=qa_data['threshold']
                )

                if scene_id not in qa_results:
                    qa_results[scene_id] = []
                qa_results[scene_id].append(qa)

                # Update video quality scores
                videos = video_candidates.get(scene_id, [])
                for video in videos:
                    if video.video_url == qa_data['video_url']:
                        video.quality_score = qa_data['overall_score']

        console.print(f"[green]✓[/green] Loaded QA results for {len(qa_results)} scenes")
        console.print()
        skip_qa = True  # Don't re-run QA

    if not skip_qa:
        console.print(Panel.fit(
            "[bold]QA Verification[/bold]",
            border_style="blue"
        ))

        if use_live:
            console.print("[yellow]Using Claude Vision for real analysis[/yellow]")
        else:
            console.print("[dim]Using mock mode (simulated scores)[/dim]")
        console.print()

        passed_count = 0
        total_count = 0

        for scene in scenes:
            videos = video_candidates.get(scene.scene_id, [])
            scene_qa = []

            console.print(f"Analyzing {scene.scene_id}: [dim]{scene.title}[/dim]")

            for video in videos:
                qa = await qa_verifier.verify_video(
                    scene=scene,
                    generated_video=video,
                    original_request=concept,
                    production_tier=pilot_tier
                )
                video.quality_score = qa.overall_score
                scene_qa.append(qa)
                total_count += 1

                if qa.passed:
                    passed_count += 1
                    console.print(f"  v{video.variation_id}: [green]{qa.overall_score:.1f}/100[/green] ✓")
                else:
                    console.print(f"  v{video.variation_id}: [yellow]{qa.overall_score:.1f}/100[/yellow] ⚠")

                # Save QA result immediately (checkpoint)
                qa_file = qa_dir / f"{scene.scene_id}_v{video.variation_id}_qa.json"
                with open(qa_file, 'w') as f:
                    json.dump({
                        'scene_id': qa.scene_id,
                        'video_url': qa.video_url,
                        'overall_score': qa.overall_score,
                        'visual_accuracy': qa.visual_accuracy,
                        'style_consistency': qa.style_consistency,
                        'technical_quality': qa.technical_quality,
                        'narrative_fit': qa.narrative_fit,
                        'issues': qa.issues,
                        'suggestions': qa.suggestions,
                        'passed': qa.passed,
                        'threshold': qa.threshold
                    }, f, indent=2)

            qa_results[scene.scene_id] = scene_qa
            console.print()

        pass_rate = int(100 * passed_count / total_count) if total_count > 0 else 0
        console.print(f"[green]✓[/green] QA complete: {passed_count}/{total_count} passed ({pass_rate}%)")
        console.print()
    else:
        console.print("[dim]Skipping QA verification[/dim]\n")

    # --- Critic Analysis ---
    # Check if critic results already exist
    critic_file = run_path / "critic_results.json"
    if critic_file.exists() and not skip_critic:
        console.print("[yellow]Found existing critic results[/yellow]")
        console.print("Skipping critic analysis (use fresh run to re-analyze)")
        console.print()
        skip_critic = True

    if not skip_critic:
        console.print(Panel.fit(
            "[bold]Critic Analysis[/bold]",
            border_style="blue"
        ))

        scene_results = []
        for scene in scenes:
            videos = video_candidates.get(scene.scene_id, [])
            qa_list = qa_results.get(scene.scene_id, [])

            # Find best video for this scene (highest QA score, or first if no scores)
            best_idx = 0
            best_score = 0.0
            for i, video in enumerate(videos):
                score = video.quality_score if video.quality_score else 0.0
                if score > best_score:
                    best_score = score
                    best_idx = i

            best_video = videos[best_idx] if videos else None
            best_qa = qa_list[best_idx] if best_idx < len(qa_list) else None

            # Construct SceneResult with the fields it expects
            scene_result = SceneResult(
                scene_id=scene.scene_id,
                description=scene.description,
                video_url=best_video.video_url if best_video else "",
                qa_score=best_qa.overall_score if best_qa else 0.0,
                generation_cost=best_video.generation_cost if best_video else 0.0,
                qa_passed=best_qa.passed if best_qa else False,
                qa_threshold=best_qa.threshold if best_qa else 70.0,
                qa_issues=best_qa.issues if best_qa else [],
                qa_suggestions=best_qa.suggestions if best_qa else []
            )
            scene_results.append(scene_result)

        # Create a minimal pilot object for the critic
        pilot = PilotStrategy(
            pilot_id="resume_pilot_1",
            tier=pilot_tier,
            allocated_budget=budget_total,
            test_scene_count=len(scenes),
            full_scene_count=len(scenes),
            rationale="Resumed production from saved state"
        )

        # Evaluate with critic (returns PilotResults with evaluation)
        pilot_results = await critic.evaluate_pilot(
            original_request=concept,
            pilot=pilot,
            scene_results=scene_results,
            budget_spent=budget_spent,
            budget_allocated=budget_total
        )

        console.print(f"Overall score: [cyan]{pilot_results.critic_score:.1f}/100[/cyan]")
        console.print(f"Approved: [bold]{pilot_results.approved}[/bold]")
        console.print(f"Reasoning: {pilot_results.critic_reasoning}")

        # Save critic results (checkpoint)
        with open(critic_file, 'w') as f:
            json.dump({
                'critic_score': pilot_results.critic_score,
                'approved': pilot_results.approved,
                'avg_qa_score': pilot_results.avg_qa_score,
                'reasoning': pilot_results.critic_reasoning,
                'adjustments_needed': pilot_results.adjustments_needed or [],
                'qa_failures_count': pilot_results.qa_failures_count
            }, f, indent=2)

        console.print()
    else:
        console.print("[dim]Skipping critic analysis[/dim]\n")
        # Still need scene_results for editor
        scene_results = []
        for scene in scenes:
            videos = video_candidates.get(scene.scene_id, [])
            best_video = videos[0] if videos else None
            scene_result = SceneResult(
                scene_id=scene.scene_id,
                description=scene.description,
                video_url=best_video.video_url if best_video else "",
                qa_score=0.0,
                generation_cost=best_video.generation_cost if best_video else 0.0,
                qa_passed=False,
                qa_threshold=70.0,
                qa_issues=[],
                qa_suggestions=[]
            )
            scene_results.append(scene_result)

    # --- Load Audio Files ---
    # Check if audio files exist for scenes
    scene_audio_map = {}
    audio_dir = run_path / "audio"
    if audio_dir.exists():
        for scene in scenes:
            # Look for audio file for this scene
            audio_files = list(audio_dir.glob(f"{scene.scene_id}*"))
            if audio_files:
                scene_audio_map[scene.scene_id] = str(audio_files[0])

    # --- Editor ---
    if not skip_editor:
        console.print(Panel.fit(
            "[bold]Edit Decision List[/bold]",
            border_style="blue"
        ))

        # Editor expects video_candidates and qa_results dicts
        edl = await editor.create_edl(
            scenes=scenes,
            video_candidates=video_candidates,
            qa_results=qa_results,
            scene_audio=scene_audio_map if scene_audio_map else None,
            original_request=concept,
            num_candidates=1  # Just create one EDL
        )

        # Get the recommended candidate (or first one)
        if edl.recommended_candidate_id:
            candidate = next((c for c in edl.candidates if c.candidate_id == edl.recommended_candidate_id), edl.candidates[0])
        else:
            candidate = edl.candidates[0] if edl.candidates else None

        if candidate:
            console.print(f"Candidate: {candidate.name} ({candidate.style})")
            console.print(f"Edit decisions: {len(candidate.decisions)}")
            console.print(f"Total duration: [cyan]{candidate.total_duration:.1f}s[/cyan]")
            console.print(f"Quality: {candidate.estimated_quality:.1f}/100")

            # Save EDL
            edl_dir = run_path / "edl"
            edl_dir.mkdir(exist_ok=True)
            edl_path = edl_dir / "final.json"

            with open(edl_path, 'w') as f:
                json.dump({
                    'edl_id': edl.edl_id,
                    'project_name': edl.project_name,
                    'original_request': edl.original_request,
                    'total_scenes': edl.total_scenes,
                    'recommended_candidate_id': edl.recommended_candidate_id,
                    'candidates': [
                        {
                            'candidate_id': c.candidate_id,
                            'name': c.name,
                            'style': c.style,
                            'total_duration': c.total_duration,
                            'estimated_quality': c.estimated_quality,
                            'description': c.description,
                            'reasoning': c.reasoning,
                            'decisions': [
                                {
                                    'scene_id': d.scene_id,
                                    'selected_variation': d.selected_variation,
                                    'video_url': d.video_url,
                                    'audio_url': d.audio_url,
                                    'in_point': d.in_point,
                                    'out_point': d.out_point,
                                    'transition_in': d.transition_in,
                                    'transition_in_duration': d.transition_in_duration,
                                    'transition_out': d.transition_out,
                                    'transition_out_duration': d.transition_out_duration,
                                    'start_time': d.start_time,
                                    'duration': d.duration,
                                    'notes': d.notes
                                }
                                for d in c.decisions
                            ]
                        }
                        for c in edl.candidates
                    ]
                }, f, indent=2)

            console.print(f"[green]✓[/green] EDL saved: {edl_path}")

            # === AUDIO-VIDEO MIXING ===
            # Mix audio with video if we have audio files
            if scene_audio_map:
                from core.rendering.mixer import mix_single_scene, concatenate_videos

                console.print("\n[cyan]Mixing video + audio...[/cyan]")

                mixed_dir = run_path / "mixed"
                mixed_dir.mkdir(exist_ok=True)
                mixed_scenes_paths = []

                for decision in candidate.decisions:
                    video_path = decision.video_url
                    audio_path = scene_audio_map.get(decision.scene_id)

                    if video_path and audio_path and Path(video_path).exists() and Path(audio_path).exists():
                        output_path = mixed_dir / f"{decision.scene_id}_mixed.mp4"

                        try:
                            await mix_single_scene(
                                video_path=str(video_path),
                                audio_path=str(audio_path),
                                output_path=str(output_path),
                                fit_mode="truncate",  # Default to video-led for resume
                            )
                            mixed_scenes_paths.append(output_path)
                            console.print(f"  ✓ Mixed {decision.scene_id}")
                        except Exception as e:
                            console.print(f"  ⚠ Failed to mix {decision.scene_id}: {e}")
                            # Fall back to video-only
                            if Path(video_path).exists():
                                mixed_scenes_paths.append(Path(video_path))
                    elif video_path and Path(video_path).exists():
                        # No audio, use video as-is
                        mixed_scenes_paths.append(Path(video_path))

                # Concatenate all mixed scenes into final output
                if mixed_scenes_paths:
                    final_output = run_path / "final_output.mp4"
                    try:
                        await concatenate_videos(mixed_scenes_paths, final_output)
                        console.print(f"[green]✓[/green] Final output: {final_output}")
                    except Exception as e:
                        console.print(f"[red]✗[/red] Failed to concatenate: {e}")

        else:
            console.print("[yellow]⚠[/yellow]  No edit candidates created")
        console.print()
    else:
        console.print("[dim]Skipping EDL creation[/dim]\n")

    # Summary
    console.print(Panel.fit(
        "[bold green]Resume Complete![/bold green]",
        border_style="green"
    ))

    console.print("\n[bold]Next steps:[/bold]")

    # Check if scenes have voiceover text
    has_voiceover = any(scene.voiceover_text for scene in scenes)
    if has_voiceover:
        console.print("  1. Generate audio from voiceover text")
        console.print("     [dim]Use AudioGenerator or test-provider elevenlabs[/dim]")
        console.print("  2. Mix audio with videos using FFmpeg")
        console.print("     [dim]claude-studio render mix video.mp4 --audio audio.mp3 -o final.mp4[/dim]")
    else:
        console.print("  1. Render final video from EDL")
        console.print("     [dim]Use the EDL to concatenate scenes[/dim]")

    console.print()
