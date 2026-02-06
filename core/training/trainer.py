"""Main training loop with convergence checking"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from agents.audio_generator import AudioGeneratorAgent, VoiceStyle
from core.claude_client import ClaudeClient, JSONExtractor
from core.memory.manager import MemoryManager

from .loss import calculate_all_metrics
from .models import (
    StyleProfile,
    TrainingConfig,
    TrainingPair,
    TrialResult,
)
from .transcription import get_audio_duration

console = Console()


async def run_training_loop(
    training_pairs: List[TrainingPair],
    config: TrainingConfig,
    memory_manager: MemoryManager,
    claude_client: ClaudeClient,
    output_dir: Path,
    style_profile,  # Can be StyleProfile or AggregatedProfile
    skip_audio: bool = False,
) -> tuple[List[TrialResult], Dict[str, int]]:
    """
    Main training loop.

    1. For each trial:
       a. Generate podcast script for each training pair
       b. Generate TTS audio
       c. Calculate loss metrics
       d. Store results
       e. Check convergence
       f. Refine prompts if not converged

    2. Return all trial results and total API usage
    """
    results: List[TrialResult] = []
    loop_usage: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # Extract StyleProfile from AggregatedProfile if needed
    from core.training.models import AggregatedProfile
    if isinstance(style_profile, AggregatedProfile):
        # Get the first StyleProfile from style_variants
        if style_profile.style_variants:
            style_profile_to_use = next(iter(style_profile.style_variants.values()))
        else:
            raise ValueError("AggregatedProfile has no style_variants")
    else:
        style_profile_to_use = style_profile

    console.print(f"\n[bold cyan]Starting Training Loop[/bold cyan]")
    console.print(f"Training pairs: {len(training_pairs)}")
    console.print(f"Max trials: {config.max_trials}")
    console.print(f"Convergence threshold: {config.convergence_threshold}")
    console.print()

    for trial_num in range(config.max_trials):
        trial_id = f"trial_{trial_num:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        console.print(f"\n{'='*60}")
        console.print(f"[bold]TRIAL {trial_num + 1}/{config.max_trials}[/bold] ({trial_id})")
        console.print(f"{'='*60}\n")

        pair_results = {}
        generated_scripts = {}
        generated_audio = {}

        for pair in training_pairs:
            console.print(f"\n--- Processing: [cyan]{pair.pair_id}[/cyan] ---")

            try:
                # 1. Generate podcast script using Claude with learned style profile
                console.print("  Generating podcast script...")
                script_text, script_usage = await generate_podcast_script(
                    pair=pair,
                    style_profile=style_profile_to_use,
                    claude_client=claude_client,
                    trial_num=trial_num,
                )
                # Track usage
                if script_usage:
                    loop_usage["input_tokens"] += script_usage.get("input_tokens", 0)
                    loop_usage["output_tokens"] += script_usage.get("output_tokens", 0)
                    loop_usage["total_tokens"] += script_usage.get("total_tokens", 0)
                script_path = output_dir / trial_id / f"{pair.pair_id}_script.txt"
                script_path.parent.mkdir(parents=True, exist_ok=True)
                script_path.write_text(script_text, encoding='utf-8')

                console.print(f"  [green]Script saved to: {script_path}[/green]")
                console.print(f"  [yellow]Script preview:[/yellow]")
                preview = script_text[:500] + "..." if len(script_text) > 500 else script_text
                console.print(f"  {preview}\n")
                console.print(f"  [cyan]Word count: {len(script_text.split())} words[/cyan]")

                # 2. Generate TTS audio using real audio provider
                if skip_audio:
                    console.print("  [yellow]Skipping audio generation (--skip-audio flag)[/yellow]")
                    console.print("  [yellow]Using reference audio for metrics calculation[/yellow]")
                    # Use reference audio for metrics
                    audio_path = output_dir / trial_id / f"{pair.pair_id}_audio.mp3"
                    import shutil
                    shutil.copy(pair.audio_path, audio_path)
                    generated_duration = await get_audio_duration(str(audio_path))
                else:
                    console.print("  Generating TTS audio...")
                    audio_path = output_dir / trial_id / f"{pair.pair_id}_audio.mp3"

                    audio_agent = AudioGeneratorAgent(claude_client=claude_client)

                    # Generate with conversational style (will use "Adam" voice via mapping)
                    try:
                        voiceover_result = await audio_agent.generate_voiceover(
                            text=script_text,
                            voice_style=VoiceStyle.CONVERSATIONAL,
                            voice_id=None,  # Use default mapping based on style
                        )

                        # Save audio to file
                        voiceover_result.audio_path.rename(audio_path)
                        generated_duration = voiceover_result.duration
                    except Exception as e:
                        console.print(f"  [yellow]Warning: TTS generation failed: {e}[/yellow]")
                        console.print(f"  [yellow]Falling back to copying reference audio[/yellow]")
                        # Fallback: copy reference audio
                        import shutil
                        shutil.copy(pair.audio_path, audio_path)
                        generated_duration = await get_audio_duration(str(audio_path))

                # 3. Calculate all loss metrics
                console.print("  Calculating loss metrics...")
                metrics = await calculate_all_metrics(
                    generated_script=script_text,
                    generated_duration=generated_duration,
                    reference_transcription=pair.transcription,
                    reference_aligned=pair.aligned_segments or [],
                    document_graph=pair.document_graph,
                    claude_client=claude_client,
                    trial_id=trial_id,
                    pair_id=pair.pair_id,
                    weights=config.loss_weights,
                )

                pair_results[pair.pair_id] = metrics
                generated_scripts[pair.pair_id] = str(script_path)
                generated_audio[pair.pair_id] = str(audio_path)

                # Log progress
                console.print(f"  Duration: {generated_duration:.1f}s (ref: {pair.transcription.total_duration:.1f}s)")
                console.print(f"  Duration Loss: {metrics.duration_loss:.3f}")
                console.print(f"  Coverage: {(1-metrics.coverage_loss)*100:.1f}% ({metrics.concepts_mentioned}/{metrics.concepts_total} concepts)")
                console.print(f"  Quality: Engagement={metrics.engagement_score:.0f}, Clarity={metrics.clarity_score:.0f}, Accuracy={metrics.accuracy_score:.0f}")
                console.print(f"  ROUGE-1: {metrics.rouge_1:.3f}, ROUGE-2: {metrics.rouge_2:.3f}, ROUGE-L: {metrics.rouge_l:.3f}")
                console.print(f"  [bold]Total Loss: {metrics.total_loss:.4f}[/bold]")

            except Exception as e:
                console.print(f"  [red]Error processing {pair.pair_id}: {e}[/red]")
                import traceback
                traceback.print_exc()
                continue

        if not pair_results:
            console.print("[red]No results for this trial, skipping...[/red]")
            continue

        # 4. Aggregate trial results
        trial_result = TrialResult(
            trial_id=trial_id,
            trial_number=trial_num,
            pair_results=pair_results,
            avg_total_loss=np.mean([m.total_loss for m in pair_results.values()]),
            avg_duration_loss=np.mean([m.duration_loss for m in pair_results.values()]),
            avg_coverage_loss=np.mean([m.coverage_loss for m in pair_results.values()]),
            avg_structure_loss=np.mean([m.structure_loss for m in pair_results.values()]),
            avg_quality_loss=np.mean([m.quality_loss for m in pair_results.values()]),
            avg_rouge_loss=np.mean([m.rouge_loss for m in pair_results.values()]),
            generated_scripts=generated_scripts,
            generated_audio=generated_audio,
            prompt_version=f"v{trial_num}",
            profile_version="v1",
            timestamp=datetime.now(),
        )

        results.append(trial_result)

        # 5. Store trial results
        await store_trial_results(trial_result, output_dir, memory_manager)

        # 6. Print trial summary
        print_trial_summary(trial_result)

        # 7. Check convergence
        if check_convergence(results, config):
            console.print(f"\n[green]✓ Converged after {trial_num + 1} trials![/green]")
            break

        # 8. Prompt refinement for next trial
        # TODO: Implement prompt refinement based on loss metrics
        # Could adjust style profile parameters, target duration, or emphasis areas
        if trial_num < config.max_trials - 1:
            console.print(f"\n[yellow]→ Prompt refinement for next trial (TODO: implement adaptive refinement)[/yellow]")

    # Final report (include usage from training loop)
    await generate_training_report(results, config, output_dir, usage=loop_usage)

    return results, loop_usage


async def generate_podcast_script(
    pair: TrainingPair,
    style_profile: StyleProfile,
    claude_client: ClaudeClient,
    trial_num: int,
) -> tuple[str, Optional[Dict[str, int]]]:
    """
    Generate a podcast script from the document using the learned style profile.

    Args:
        pair: Training pair with document and reference
        style_profile: Learned style profile to mimic
        claude_client: Claude client for generation
        trial_num: Current trial number (for prompt refinement)

    Returns:
        Tuple of (generated script text, token usage dict)
    """
    doc_graph = pair.document_graph

    # Extract key information from document
    title = getattr(doc_graph, 'project_id', 'Unknown Topic').replace('-', ' ').replace('_', ' ').title()
    summary = getattr(doc_graph, 'unified_summary', '')[:1000]
    themes = getattr(doc_graph, 'key_themes', [])[:5]

    # Get target duration and word count from reference
    target_duration_sec = pair.transcription.total_duration if pair.transcription else 660  # ~11 min default
    target_duration_min = target_duration_sec / 60
    target_word_count = int(target_duration_sec * 2.5)  # ~150 WPM avg

    # Build style guidance from profile
    style_guidance = f"""
STYLE PROFILE (adopt this conversational style, don't copy phrases verbatim):
- Average sentence length: {style_profile.avg_sentence_length:.1f} words
- Vocabulary complexity: {style_profile.vocabulary_complexity:.2f} (0=simple, 1=complex)
- Technical term density: {style_profile.jargon_density:.2f}
- Questions per minute: {style_profile.questions_per_minute:.2f}
- Analogies per segment: {style_profile.analogies_per_segment:.2f}

STYLE EXAMPLES (use similar patterns and tone, but adapt to your content):
Intro style examples: {', '.join(style_profile.intro_phrases[:3]) if style_profile.intro_phrases else 'N/A'}
Transition style examples: {', '.join(style_profile.transition_phrases[:3]) if style_profile.transition_phrases else 'N/A'}
Emphasis style examples: {', '.join(style_profile.emphasis_phrases[:3]) if style_profile.emphasis_phrases else 'N/A'}
Enthusiasm markers: {', '.join(style_profile.enthusiasm_markers[:5]) if style_profile.enthusiasm_markers else 'N/A'}
"""

    prompt = f"""You are creating a podcast-style audio script about a technical paper.

=== YOUR CONTENT SOURCE (use facts, figures, and citations from here) ===
PAPER TO EXPLAIN:
Title: {title}
Summary: {summary}
Key Themes: {', '.join(themes)}

IMPORTANT: All factual content, author names, figures, and findings must come from THIS paper above.

=== YOUR STYLE REFERENCE (adopt conversational style from here) ===
The style examples below come from a DIFFERENT podcast about a DIFFERENT paper.
Use them ONLY to understand the conversational tone, pacing, and explanation style.
DO NOT copy their content, show name, or specific phrases.

TARGET:
- Duration: ~{target_duration_min:.1f} minutes
- Word count: ~{target_word_count} words
- Conversational, engaging podcast style

{style_guidance}

CRITICAL INSTRUCTIONS:
1. CONTENT SOURCE: Explain the paper above (Title: {title})
   - Use the actual author names, findings, and data from THIS paper
   - Reference specific figures, tables, and results from THIS paper
   - All facts must come from the paper content, not the style examples

2. STYLE SOURCE: Match the conversational style shown in the examples
   - Adopt similar sentence length, complexity, and question frequency
   - Use analogies and explanations at a similar pace
   - Match the enthusiasm and engagement level
   - But create ORIGINAL phrases appropriate to YOUR paper's content

3. DO NOT:
   - Copy show names (like "Journal Club") from the style examples
   - Copy specific phrases verbatim from the style examples
   - Reference content from the style examples' paper
   - Use the style examples' host names or branding

4. DO:
   - Create your own intro appropriate to THIS paper's topic
   - Use the actual findings and data from THIS paper
   - Write in a conversational style similar to the examples
   - Aim for ~{target_word_count} words to match duration

Return ONLY the transcript text (no JSON, no scene markers, no meta-commentary).

Generate the complete podcast script now:"""

    response, usage = await claude_client.query(prompt, return_usage=True)

    # Log usage
    if usage:
        console.print(f"  Script generation API usage: {usage['input_tokens']} in + {usage['output_tokens']} out = {usage['total_tokens']} tokens")

    return response.strip(), usage


async def store_trial_results(
    trial_result: TrialResult,
    output_dir: Path,
    memory_manager: MemoryManager,
):
    """Store trial results to disk and memory."""
    trial_dir = output_dir / trial_result.trial_id
    trial_dir.mkdir(parents=True, exist_ok=True)

    # Save results as JSON
    results_file = trial_dir / "results.json"
    results_data = {
        "trial_id": trial_result.trial_id,
        "trial_number": trial_result.trial_number,
        "timestamp": trial_result.timestamp.isoformat(),
        "avg_total_loss": trial_result.avg_total_loss,
        "avg_duration_loss": trial_result.avg_duration_loss,
        "avg_coverage_loss": trial_result.avg_coverage_loss,
        "avg_structure_loss": trial_result.avg_structure_loss,
        "avg_quality_loss": trial_result.avg_quality_loss,
        "avg_rouge_loss": trial_result.avg_rouge_loss,
        "pair_results": {
            pair_id: {
                "duration_loss": m.duration_loss,
                "coverage_loss": m.coverage_loss,
                "structure_loss": m.structure_loss,
                "quality_loss": m.quality_loss,
                "rouge_loss": m.rouge_loss,
                "total_loss": m.total_loss,
                "engagement_score": m.engagement_score,
                "clarity_score": m.clarity_score,
                "accuracy_score": m.accuracy_score,
                "concepts_covered": m.concepts_mentioned,
                "concepts_total": m.concepts_total,
            }
            for pair_id, m in trial_result.pair_results.items()
        }
    }
    results_file.write_text(json.dumps(results_data, indent=2, ensure_ascii=False), encoding='utf-8')

    # Results are saved to file above; MemoryManager is for production run learnings only


def print_trial_summary(trial_result: TrialResult):
    """Print summary of trial results."""
    console.print(f"\n[bold cyan]Trial Summary[/bold cyan]")
    console.print(f"Average Total Loss: [bold]{trial_result.avg_total_loss:.4f}[/bold]")
    console.print(f"  Duration Loss:  {trial_result.avg_duration_loss:.4f}")
    console.print(f"  Coverage Loss:  {trial_result.avg_coverage_loss:.4f} ({(1-trial_result.avg_coverage_loss)*100:.1f}% coverage)")
    console.print(f"  Structure Loss: {trial_result.avg_structure_loss:.4f}")
    console.print(f"  Quality Loss:   {trial_result.avg_quality_loss:.4f}")
    console.print(f"  ROUGE Loss:     {trial_result.avg_rouge_loss:.4f}")


def check_convergence(
    results: List[TrialResult],
    config: TrainingConfig,
) -> bool:
    """Check if training has converged."""
    if len(results) < config.convergence_window + 1:
        return False

    recent = results[-config.convergence_window:]
    previous = results[-config.convergence_window - 1]

    # Check if improvement is below threshold
    avg_recent = np.mean([r.avg_total_loss for r in recent])
    improvement = (previous.avg_total_loss - avg_recent) / previous.avg_total_loss

    console.print(f"\nConvergence check: improvement = {improvement:.4f} (threshold = {config.convergence_threshold})")

    return improvement < config.convergence_threshold


async def generate_training_report(
    results: List[TrialResult],
    config: TrainingConfig,
    output_dir: Path,
    usage: Optional[Dict[str, int]] = None,
):
    """Generate final training report."""
    console.print(f"\n{'='*60}")
    console.print("[bold green]Training Complete![/bold green]")
    console.print(f"{'='*60}\n")

    console.print(f"Total trials: {len(results)}")

    if results:
        best_trial = min(results, key=lambda r: r.avg_total_loss)
        console.print(f"\n[bold]Best Trial:[/bold] {best_trial.trial_id}")
        console.print(f"  Total Loss: {best_trial.avg_total_loss:.4f}")
        console.print(f"  Duration Loss: {best_trial.avg_duration_loss:.4f}")
        console.print(f"  Coverage Loss: {best_trial.avg_coverage_loss:.4f}")
        console.print(f"  Quality Loss: {best_trial.avg_quality_loss:.4f}")

        # Loss progression
        console.print(f"\n[bold]Loss Progression:[/bold]")
        for i, result in enumerate(results):
            console.print(f"  Trial {i+1}: {result.avg_total_loss:.4f}")

    # Save report
    report_file = output_dir / "training_report.json"
    report_data = {
        "config": {
            "max_trials": config.max_trials,
            "convergence_threshold": config.convergence_threshold,
            "target_depth": config.target_depth.value,
        },
        "results": {
            "total_trials": len(results),
            "best_trial": best_trial.trial_id if results else None,
            "best_loss": best_trial.avg_total_loss if results else None,
            "loss_progression": [r.avg_total_loss for r in results],
        },
        "usage": usage or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "timestamp": datetime.now().isoformat(),
    }
    report_file.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding='utf-8')

    console.print(f"\n[green]Report saved to: {report_file}[/green]")
