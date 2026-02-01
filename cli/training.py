"""CLI commands for podcast training pipeline"""

import asyncio
import click
from pathlib import Path
from rich.console import Console

from core.claude_client import ClaudeClient
from core.memory.manager import MemoryManager
from core.models.knowledge import KnowledgeGraph as DocumentGraph

from core.training import (
    TranscriptionResult,
    TrainingPair,
    TrainingConfig,
    PodcastDepth,
    transcribe_podcast,
    classify_segments,
    extract_structure_profile,
    extract_style_profile,
    synthesize_profiles,
    store_profile_in_memory,
    run_training_loop,
)

console = Console()


@click.group()
def training():
    """Training pipeline commands"""
    pass


@training.command()
@click.option('--pairs-dir', default='artifacts/training_data', help='Directory containing training pairs')
@click.option('--output-dir', default='artifacts/training_output', help='Output directory for results')
@click.option('--max-trials', default=5, help='Maximum number of training trials')
@click.option('--mock', is_flag=True, help='Use mock mode for testing')
def run(pairs_dir, output_dir, max_trials, mock):
    """Run the complete training pipeline"""
    asyncio.run(run_training_pipeline(pairs_dir, output_dir, max_trials, mock))


async def run_training_pipeline(pairs_dir: str, output_dir: str, max_trials: int, mock: bool):
    """Main training pipeline execution"""
    console.print("[bold cyan]Claude Studio Producer - Training Pipeline[/bold cyan]\n")

    pairs_path = Path(pairs_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize clients
    claude_client = ClaudeClient()
    memory_manager = MemoryManager()

    # 1. Discover training pairs
    console.print("[bold]Phase 1: Discovering Training Pairs[/bold]")
    training_pairs = await discover_training_pairs(pairs_path)
    console.print(f"Found {len(training_pairs)} training pairs\n")

    if not training_pairs:
        console.print("[red]No training pairs found![/red]")
        return

    # 2. Ingest and transcribe
    console.print("[bold]Phase 2: Ingestion & Transcription[/bold]")
    for pair in training_pairs:
        console.print(f"\nProcessing {pair.pair_id}...")

        # Create minimal document graph (PDF ingestion would go here in production)
        if not pair.document_graph:
            console.print("  Creating document graph...")
            try:
                # Extract title from PDF filename
                title = pair.pair_id.replace("-", " ").replace("_", " ").title()

                pair.document_graph = DocumentGraph(
                    project_id=pair.pair_id,
                    atoms={},
                    atom_sources={},
                    cross_links=[],
                    topic_index={},
                    entity_index={},
                    unified_summary="",
                    key_themes=[],
                )
            except Exception as e:
                console.print(f"  [yellow]Warning: Document graph creation failed: {e}[/yellow]")
                # Create minimal fallback
                pair.document_graph = DocumentGraph(
                    project_id=pair.pair_id,
                    atoms={},
                    atom_sources={},
                    cross_links=[],
                    topic_index={},
                    entity_index={},
                    unified_summary="",
                    key_themes=[],
                )

        # Transcribe audio
        if not pair.transcription:
            console.print("  Transcribing audio...")
            try:
                pair.transcription = await transcribe_podcast(
                    pair.audio_path,
                    speaker_id=pair.pair_id,
                )
                pair.duration_minutes = pair.transcription.total_duration / 60.0
                console.print(f"  Duration: {pair.duration_minutes:.1f} minutes")
                console.print(f"  Segments: {len(pair.transcription.segments)}")
            except Exception as e:
                console.print(f"  [red]Error: Transcription failed: {e}[/red]")
                import traceback
                traceback.print_exc()
                continue

    # 3. Analyze segments
    console.print("\n[bold]Phase 3: Segment Analysis[/bold]")
    for pair in training_pairs:
        if not pair.transcription or not pair.document_graph:
            continue

        console.print(f"\nAnalyzing {pair.pair_id}...")

        try:
            # Classify segments
            console.print("  Classifying segments...")
            pair.aligned_segments = await classify_segments(
                pair.transcription,
                pair.document_graph,
                claude_client,
            )
            console.print(f"  Classified {len(pair.aligned_segments)} segments")

            # Extract structure profile
            console.print("  Extracting structure profile...")
            pair.structure_profile = await extract_structure_profile(
                pair.aligned_segments,
                pair.transcription,
            )

            # Extract style profile
            console.print("  Extracting style profile...")
            pair.style_profile = await extract_style_profile(
                pair.aligned_segments,
                pair.transcription,
                pair.speaker_gender,
                claude_client,
            )
        except Exception as e:
            console.print(f"  [red]Error: Analysis failed: {e}[/red]")
            import traceback
            traceback.print_exc()

    # 4. Synthesize profiles
    console.print("\n[bold]Phase 4: Profile Synthesis[/bold]")
    try:
        aggregated_profile = await synthesize_profiles(training_pairs)
        console.print(f"Created aggregated profile v{aggregated_profile.version}")

        # Store in memory
        await store_profile_in_memory(aggregated_profile, memory_manager)
        console.print("Stored profile in memory")
    except Exception as e:
        console.print(f"[red]Error: Profile synthesis failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return

    # 5. Run training loop
    console.print("\n[bold]Phase 5: Training Loop[/bold]")
    config = TrainingConfig(
        max_trials=max_trials,
        convergence_threshold=0.05,
        convergence_window=2,
        target_depth=PodcastDepth.STANDARD,
    )

    try:
        results = await run_training_loop(
            training_pairs=training_pairs,
            config=config,
            memory_manager=memory_manager,
            claude_client=claude_client,
            output_dir=output_path,
        )

        console.print(f"\n[bold green]Training complete! Generated {len(results)} trials[/bold green]")
        console.print(f"Results saved to: {output_path}")

    except Exception as e:
        console.print(f"[red]Error: Training loop failed: {e}[/red]")
        import traceback
        traceback.print_exc()


async def discover_training_pairs(pairs_dir: Path) -> list:
    """Discover PDF+MP3 pairs in directory"""
    training_pairs = []

    # Find all PDF files
    pdf_files = list(pairs_dir.glob("*.pdf"))

    for pdf_file in pdf_files:
        # Look for matching MP3
        base_name = pdf_file.stem
        mp3_file = pairs_dir / f"{base_name}.mp3"

        if mp3_file.exists():
            pair = TrainingPair(
                pair_id=base_name,
                pdf_path=str(pdf_file),
                audio_path=str(mp3_file),
                speaker_gender="unknown",  # Would detect from filename or metadata
                source="journalclub",
            )
            training_pairs.append(pair)
            console.print(f"  Found pair: {base_name}")

    return training_pairs


@training.command()
@click.argument('pairs_dir', default='artifacts/training_data')
def list_pairs(pairs_dir):
    """List available training pairs"""
    asyncio.run(list_training_pairs(pairs_dir))


async def list_training_pairs(pairs_dir: str):
    """List training pairs"""
    console.print("[bold]Training Pairs:[/bold]\n")

    pairs_path = Path(pairs_dir)
    training_pairs = await discover_training_pairs(pairs_path)

    if not training_pairs:
        console.print("[yellow]No training pairs found[/yellow]")
        return

    for pair in training_pairs:
        console.print(f"  • {pair.pair_id}")
        console.print(f"    PDF:   {pair.pdf_path}")
        console.print(f"    Audio: {pair.audio_path}")
        console.print()


if __name__ == '__main__':
    training()
