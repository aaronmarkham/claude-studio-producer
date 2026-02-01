"""Main training loop with convergence checking"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List

import numpy as np
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.claude_client import ClaudeClient
from core.memory.manager import MemoryManager

from .loss import calculate_all_metrics
from .models import (
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
) -> List[TrialResult]:
    """
    Main training loop.

    1. For each trial:
       a. Generate podcast script for each training pair
       b. Generate TTS audio
       c. Calculate loss metrics
       d. Store results
       e. Check convergence
       f. Refine prompts if not converged

    2. Return all trial results for analysis
    """
    results: List[TrialResult] = []

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
                # 1. Generate podcast script (mock for now - would use ScriptWriterAgent)
                script_text = generate_mock_script(pair, trial_num)
                script_path = output_dir / trial_id / f"{pair.pair_id}_script.txt"
                script_path.parent.mkdir(parents=True, exist_ok=True)
                script_path.write_text(script_text)

                # 2. Generate TTS audio (mock for now - would use AudioGeneratorAgent)
                audio_path = output_dir / trial_id / f"{pair.pair_id}_audio.mp3"
                # For mock: copy reference audio with slight variation
                import shutil
                shutil.copy(pair.audio_path, audio_path)
                generated_duration = await get_audio_duration(str(audio_path))

                # Add some variation based on trial number
                # In real training, the script would change and so would duration
                generated_duration *= (1.0 + (trial_num * 0.02))  # Slight increase each trial

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

        # 8. Note about refinement (simplified for mock training)
        if trial_num < config.max_trials - 1:
            console.print(f"\n[yellow]→ Would refine prompts for next trial (simplified in mock mode)[/yellow]")

    # Final report
    await generate_training_report(results, config, output_dir)

    return results


def generate_mock_script(pair: TrainingPair, trial_num: int) -> str:
    """
    Generate a mock script for testing.

    In production, this would call ScriptWriterAgent with refined prompts.
    For now, we use the reference transcription with slight variations.
    """
    if pair.transcription:
        # Use reference transcript as base
        base_text = pair.transcription.transcript_text

        # Add variation based on trial number
        variation_note = f"\n\n[Generated Script - Trial {trial_num}]\n"

        return base_text + variation_note
    else:
        return f"Mock script for {pair.pair_id} trial {trial_num}"


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
    results_file.write_text(json.dumps(results_data, indent=2))

    # Store in memory
    namespace = "/org/default/learnings/podcast_training/trials"
    await memory_manager.store(
        namespace=namespace,
        key=trial_result.trial_id,
        data=results_data,
    )


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
        "timestamp": datetime.now().isoformat(),
    }
    report_file.write_text(json.dumps(report_data, indent=2))

    console.print(f"\n[green]Report saved to: {report_file}[/green]")
