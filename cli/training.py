"""CLI commands for podcast training pipeline"""

import asyncio
import click
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler

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


def save_checkpoint(checkpoint_dir: Path, pair_id: str, checkpoint_type: str, data: dict):
    """Save a checkpoint to disk"""
    checkpoint_file = checkpoint_dir / f"{pair_id}_{checkpoint_type}.json"
    checkpoint_file.write_text(json.dumps(data, indent=2, default=str))


def load_checkpoint(checkpoint_dir: Path, pair_id: str, checkpoint_type: str) -> dict | None:
    """Load a checkpoint from disk if it exists"""
    checkpoint_file = checkpoint_dir / f"{pair_id}_{checkpoint_type}.json"
    if checkpoint_file.exists():
        return json.loads(checkpoint_file.read_text())
    return None


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
    pairs_path = Path(pairs_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Set up checkpointing directory
    checkpoint_dir = output_path / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Set up logging
    log_file = output_path / f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            RichHandler(console=console, show_time=False, show_path=False)
        ]
    )
    logger = logging.getLogger("training")

    logger.info("Starting training pipeline")
    logger.info(f"Output directory: {output_path}")
    logger.info(f"Checkpoint directory: {checkpoint_dir}")
    logger.info(f"Log file: {log_file}")

    console.print("[bold cyan]Claude Studio Producer - Training Pipeline[/bold cyan]\n")

    # Initialize clients and usage tracking
    claude_client = ClaudeClient()
    memory_manager = MemoryManager()
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # 1. Discover training pairs
    logger.info("Phase 1: Discovering Training Pairs")
    console.print("[bold]Phase 1: Discovering Training Pairs[/bold]")
    training_pairs = await discover_training_pairs(pairs_path)
    logger.info(f"Found {len(training_pairs)} training pairs")
    console.print(f"Found {len(training_pairs)} training pairs\n")

    if not training_pairs:
        logger.error("No training pairs found!")
        console.print("[red]No training pairs found![/red]")
        return

    # 2. Ingest and transcribe
    logger.info("Phase 2: Ingestion & Transcription")
    console.print("[bold]Phase 2: Ingestion & Transcription[/bold]")
    for pair in training_pairs:
        logger.info(f"Processing {pair.pair_id}")
        console.print(f"\nProcessing {pair.pair_id}...")

        # Create minimal document graph (PDF ingestion would go here in production)
        if not pair.document_graph:
            logger.info(f"  Creating document graph for {pair.pair_id}")
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

        # Transcribe audio (or load from checkpoint)
        if not pair.transcription:
            # Check for existing checkpoint
            checkpoint = load_checkpoint(checkpoint_dir, pair.pair_id, "transcription")
            if checkpoint:
                logger.info(f"  Loading transcription from checkpoint for {pair.pair_id}")
                console.print("  [yellow]Loading transcription from checkpoint...[/yellow]")
                try:
                    # Reconstruct TranscriptionResult from checkpoint
                    from core.training.models import WordTimestamp, TranscriptSegment
                    pair.transcription = TranscriptionResult(
                        source_path=checkpoint["source_path"],
                        transcript_text=checkpoint["transcript_text"],
                        word_timestamps=[WordTimestamp(**w) for w in checkpoint["word_timestamps"]],
                        segments=[TranscriptSegment(**s) for s in checkpoint["segments"]],
                        total_duration=checkpoint["total_duration"],
                        speaker_id=checkpoint["speaker_id"],
                        confidence=checkpoint["confidence"],
                        language=checkpoint["language"],
                    )
                    pair.duration_minutes = pair.transcription.total_duration / 60.0
                    logger.info(f"  Loaded: {pair.duration_minutes:.1f} minutes, {len(pair.transcription.segments)} segments")
                    console.print(f"  Duration: {pair.duration_minutes:.1f} minutes")
                    console.print(f"  Segments: {len(pair.transcription.segments)}")
                except Exception as e:
                    logger.warning(f"  Failed to load checkpoint, will re-transcribe: {e}")
                    console.print(f"  [yellow]Checkpoint load failed, re-transcribing...[/yellow]")
                    checkpoint = None

            if not checkpoint:
                logger.info(f"  Transcribing audio for {pair.pair_id}")
                console.print("  Transcribing audio...")
                try:
                    pair.transcription = await transcribe_podcast(
                        pair.audio_path,
                        speaker_id=pair.pair_id,
                    )
                    pair.duration_minutes = pair.transcription.total_duration / 60.0
                    logger.info(f"  Duration: {pair.duration_minutes:.1f} minutes, Segments: {len(pair.transcription.segments)}")
                    console.print(f"  Duration: {pair.duration_minutes:.1f} minutes")
                    console.print(f"  Segments: {len(pair.transcription.segments)}")

                    # Save checkpoint
                    save_checkpoint(checkpoint_dir, pair.pair_id, "transcription", {
                        "source_path": pair.transcription.source_path,
                        "transcript_text": pair.transcription.transcript_text,
                        "word_timestamps": [{"word": w.word, "start_time": w.start_time, "end_time": w.end_time, "confidence": w.confidence} for w in pair.transcription.word_timestamps],
                        "segments": [{"segment_id": s.segment_id, "text": s.text, "start_time": s.start_time, "end_time": s.end_time, "duration": s.duration} for s in pair.transcription.segments],
                        "total_duration": pair.transcription.total_duration,
                        "speaker_id": pair.transcription.speaker_id,
                        "confidence": pair.transcription.confidence,
                        "language": pair.transcription.language,
                    })
                    logger.info(f"  Saved transcription checkpoint for {pair.pair_id}")
                except Exception as e:
                    logger.error(f"  Transcription failed for {pair.pair_id}: {e}")
                    console.print(f"  [red]Error: Transcription failed: {e}[/red]")
                    import traceback
                    traceback.print_exc()
                    continue

    # 3. Analyze segments
    logger.info("Phase 3: Segment Analysis")
    console.print("\n[bold]Phase 3: Segment Analysis[/bold]")
    for pair in training_pairs:
        if not pair.transcription or not pair.document_graph:
            continue

        logger.info(f"Analyzing {pair.pair_id}")
        console.print(f"\nAnalyzing {pair.pair_id}...")

        try:
            # Classify segments (or load from checkpoint)
            analysis_checkpoint = load_checkpoint(checkpoint_dir, pair.pair_id, "analysis")
            if analysis_checkpoint and 'aligned_segments' in analysis_checkpoint:
                logger.info(f"  Loading analysis from checkpoint for {pair.pair_id}")
                console.print("  [yellow]Loading analysis from checkpoint...[/yellow]")
                # Note: Full reconstruction would need all dataclasses, simplified for now
                logger.info(f"  Loaded {len(analysis_checkpoint['aligned_segments'])} segments")
                console.print(f"  Loaded {len(analysis_checkpoint['aligned_segments'])} segments from checkpoint")
                # Still need to run analysis since we can't easily reconstruct complex objects
                analysis_checkpoint = None  # Force re-analysis for now

            if not analysis_checkpoint:
                logger.info(f"  Classifying segments for {pair.pair_id}")
                console.print("  Classifying segments...")
                pair.aligned_segments, usage = await classify_segments(
                    pair.transcription,
                    pair.document_graph,
                    claude_client,
                )
                if usage:
                    total_usage["input_tokens"] += usage["input_tokens"]
                    total_usage["output_tokens"] += usage["output_tokens"]
                    total_usage["total_tokens"] += usage["total_tokens"]
                    logger.info(f"  API usage: {usage['input_tokens']} in + {usage['output_tokens']} out = {usage['total_tokens']} tokens")
                logger.info(f"  Classified {len(pair.aligned_segments)} segments")
                console.print(f"  Classified {len(pair.aligned_segments)} segments")

                # Extract structure profile
                logger.info(f"  Extracting structure profile for {pair.pair_id}")
                console.print("  Extracting structure profile...")
                pair.structure_profile = await extract_structure_profile(
                    pair.aligned_segments,
                    pair.transcription,
                )

                # Extract style profile
                logger.info(f"  Extracting style profile for {pair.pair_id}")
                console.print("  Extracting style profile...")
                pair.style_profile, usage = await extract_style_profile(
                    pair.aligned_segments,
                    pair.transcription,
                    pair.speaker_gender,
                    claude_client,
                )
                if usage:
                    total_usage["input_tokens"] += usage["input_tokens"]
                    total_usage["output_tokens"] += usage["output_tokens"]
                    total_usage["total_tokens"] += usage["total_tokens"]
                    logger.info(f"  API usage: {usage['input_tokens']} in + {usage['output_tokens']} out = {usage['total_tokens']} tokens")
                logger.info(f"  Profiles extracted for {pair.pair_id}")

                # Save analysis checkpoint
                save_checkpoint(checkpoint_dir, pair.pair_id, "analysis", {
                    "aligned_segments": [{"segment_id": s.segment_id if hasattr(s, 'segment_id') else str(i)} for i, s in enumerate(pair.aligned_segments)],
                    "num_segments": len(pair.aligned_segments),
                    "timestamp": datetime.now().isoformat(),
                })
                logger.info(f"  Saved analysis checkpoint for {pair.pair_id}")
        except Exception as e:
            logger.error(f"  Analysis failed for {pair.pair_id}: {e}", exc_info=True)
            console.print(f"  [red]Error: Analysis failed: {e}[/red]")
            import traceback
            traceback.print_exc()

    # 4. Synthesize profiles
    logger.info("Phase 4: Profile Synthesis")
    console.print("\n[bold]Phase 4: Profile Synthesis[/bold]")

    # Check for existing profile
    profile_file = output_path / "aggregated_profile.json"
    aggregated_profile = None

    if profile_file.exists():
        logger.info("Loading existing aggregated profile from checkpoint")
        console.print("  [yellow]Loading existing profile from checkpoint...[/yellow]")
        try:
            profile_data = json.loads(profile_file.read_text())
            logger.info(f"Loaded profile version {profile_data.get('version', 'unknown')}")
            console.print(f"  Loaded profile version {profile_data.get('version', 'unknown')}")
            # Profile already exists, skip synthesis
            # Note: We're not reconstructing the full AggregatedProfile object here,
            # but the file exists which is what Phase 5 needs
        except Exception as e:
            logger.warning(f"Failed to load profile checkpoint: {e}")
            console.print(f"  [yellow]Checkpoint load failed, re-synthesizing...[/yellow]")
            profile_file = None  # Force re-synthesis

    if not profile_file or not profile_file.exists():
        try:
            aggregated_profile = await synthesize_profiles(training_pairs)
            logger.info(f"Created aggregated profile v{aggregated_profile.version}")
            console.print(f"Created aggregated profile v{aggregated_profile.version}")

            # Store profile to file
            await store_profile_in_memory(aggregated_profile, memory_manager, output_path)
            logger.info("Stored profile to aggregated_profile.json")
            console.print("Stored profile to aggregated_profile.json")
        except Exception as e:
            logger.error(f"Profile synthesis failed: {e}", exc_info=True)
            console.print(f"[red]Error: Profile synthesis failed: {e}[/red]")
            import traceback
            traceback.print_exc()
            return

    # 5. Run training loop
    logger.info(f"Phase 5: Training Loop (max_trials={max_trials})")
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

        logger.info(f"Training complete! Generated {len(results)} trials")
        logger.info(f"Results saved to: {output_path}")
        console.print(f"\n[bold green]Training complete! Generated {len(results)} trials[/bold green]")
        console.print(f"Results saved to: {output_path}")

        # Log total API usage
        logger.info(f"Total API usage: {total_usage['input_tokens']} input + {total_usage['output_tokens']} output = {total_usage['total_tokens']} tokens")
        console.print(f"\n[bold cyan]Total API Usage:[/bold cyan]")
        console.print(f"  Input tokens:  {total_usage['input_tokens']:,}")
        console.print(f"  Output tokens: {total_usage['output_tokens']:,}")
        console.print(f"  Total tokens:  {total_usage['total_tokens']:,}")

        # Estimate cost (Claude Sonnet 4 pricing: $3/MTok input, $15/MTok output)
        cost_input = total_usage['input_tokens'] / 1_000_000 * 3.0
        cost_output = total_usage['output_tokens'] / 1_000_000 * 15.0
        total_cost = cost_input + cost_output
        logger.info(f"Estimated cost: ${total_cost:.2f} (${cost_input:.2f} input + ${cost_output:.2f} output)")
        console.print(f"  Estimated cost: [bold]${total_cost:.2f}[/bold] (${cost_input:.2f} input + ${cost_output:.2f} output)")

    except Exception as e:
        logger.error(f"Training loop failed: {e}", exc_info=True)
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
