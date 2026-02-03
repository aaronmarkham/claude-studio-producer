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


def serialize_aligned_segment(seg: 'AlignedSegment') -> dict:
    """Serialize an AlignedSegment to JSON-compatible dict"""
    from core.training.models import TranscriptSegment

    return {
        "segment_id": seg.segment_id,
        "transcript_segment": {
            "segment_id": seg.transcript_segment.segment_id,
            "text": seg.transcript_segment.text,
            "start_time": seg.transcript_segment.start_time,
            "end_time": seg.transcript_segment.end_time,
            "duration": seg.transcript_segment.duration,
            "segment_type": seg.transcript_segment.segment_type.value if seg.transcript_segment.segment_type else None,
            "linked_atoms": seg.transcript_segment.linked_atoms,
        },
        "primary_atoms": seg.primary_atoms,
        "referenced_figures": seg.referenced_figures,
        "segment_type": seg.segment_type.value,
        "key_concepts": seg.key_concepts,
        "technical_terms": seg.technical_terms,
        "analogies_used": seg.analogies_used,
        "questions_asked": seg.questions_asked,
        "words_per_minute": seg.words_per_minute,
        "density_score": seg.density_score,
    }


def deserialize_aligned_segment(data: dict) -> 'AlignedSegment':
    """Reconstruct an AlignedSegment from JSON dict"""
    from core.training.models import AlignedSegment, TranscriptSegment, SegmentType

    # Reconstruct TranscriptSegment
    ts_data = data["transcript_segment"]
    transcript_segment = TranscriptSegment(
        segment_id=ts_data["segment_id"],
        text=ts_data["text"],
        start_time=ts_data["start_time"],
        end_time=ts_data["end_time"],
        duration=ts_data["duration"],
        segment_type=SegmentType(ts_data["segment_type"]) if ts_data["segment_type"] else None,
        linked_atoms=ts_data["linked_atoms"],
    )

    # Reconstruct AlignedSegment
    return AlignedSegment(
        segment_id=data["segment_id"],
        transcript_segment=transcript_segment,
        primary_atoms=data["primary_atoms"],
        referenced_figures=data["referenced_figures"],
        segment_type=SegmentType(data["segment_type"]),
        key_concepts=data["key_concepts"],
        technical_terms=data["technical_terms"],
        analogies_used=data["analogies_used"],
        questions_asked=data["questions_asked"],
        words_per_minute=data["words_per_minute"],
        density_score=data["density_score"],
    )


def serialize_structure_profile(profile: 'StructureProfile') -> dict:
    """Serialize a StructureProfile to JSON-compatible dict"""
    return {
        "segment_sequence": [s.value for s in profile.segment_sequence],
        "segment_counts": profile.segment_counts,
        "total_duration": profile.total_duration,
        "segment_durations": profile.segment_durations,
        "avg_segment_duration": profile.avg_segment_duration,
        "words_per_minute": profile.words_per_minute,
        "concepts_per_minute": profile.concepts_per_minute,
        "figures_discussed": profile.figures_discussed,
        "figure_discussion_duration": profile.figure_discussion_duration,
        "intro_percentage": profile.intro_percentage,
        "methodology_percentage": profile.methodology_percentage,
        "findings_percentage": profile.findings_percentage,
        "conclusion_percentage": profile.conclusion_percentage,
        "transition_phrases": profile.transition_phrases,
    }


def deserialize_structure_profile(data: dict) -> 'StructureProfile':
    """Reconstruct a StructureProfile from JSON dict"""
    from core.training.models import StructureProfile, SegmentType

    return StructureProfile(
        segment_sequence=[SegmentType(s) for s in data["segment_sequence"]],
        segment_counts=data["segment_counts"],
        total_duration=data["total_duration"],
        segment_durations=data["segment_durations"],
        avg_segment_duration=data["avg_segment_duration"],
        words_per_minute=data["words_per_minute"],
        concepts_per_minute=data["concepts_per_minute"],
        figures_discussed=data["figures_discussed"],
        figure_discussion_duration=data["figure_discussion_duration"],
        intro_percentage=data["intro_percentage"],
        methodology_percentage=data["methodology_percentage"],
        findings_percentage=data["findings_percentage"],
        conclusion_percentage=data["conclusion_percentage"],
        transition_phrases=data["transition_phrases"],
    )


def serialize_style_profile(profile: 'StyleProfile') -> dict:
    """Serialize a StyleProfile to JSON-compatible dict"""
    return {
        "speaker_id": profile.speaker_id,
        "speaker_gender": profile.speaker_gender,
        "avg_sentence_length": profile.avg_sentence_length,
        "vocabulary_complexity": profile.vocabulary_complexity,
        "jargon_density": profile.jargon_density,
        "questions_per_minute": profile.questions_per_minute,
        "analogies_per_segment": profile.analogies_per_segment,
        "enthusiasm_markers": profile.enthusiasm_markers,
        "definition_style": profile.definition_style,
        "example_frequency": profile.example_frequency,
        "intro_phrases": profile.intro_phrases,
        "transition_phrases": profile.transition_phrases,
        "emphasis_phrases": profile.emphasis_phrases,
        "conclusion_phrases": profile.conclusion_phrases,
        "figure_intro_pattern": profile.figure_intro_pattern,
        "figure_explanation_depth": profile.figure_explanation_depth,
    }


def deserialize_style_profile(data: dict) -> 'StyleProfile':
    """Reconstruct a StyleProfile from JSON dict"""
    from core.training.models import StyleProfile

    return StyleProfile(
        speaker_id=data["speaker_id"],
        speaker_gender=data["speaker_gender"],
        avg_sentence_length=data["avg_sentence_length"],
        vocabulary_complexity=data["vocabulary_complexity"],
        jargon_density=data["jargon_density"],
        questions_per_minute=data["questions_per_minute"],
        analogies_per_segment=data["analogies_per_segment"],
        enthusiasm_markers=data["enthusiasm_markers"],
        definition_style=data["definition_style"],
        example_frequency=data["example_frequency"],
        intro_phrases=data["intro_phrases"],
        transition_phrases=data["transition_phrases"],
        emphasis_phrases=data["emphasis_phrases"],
        conclusion_phrases=data["conclusion_phrases"],
        figure_intro_pattern=data["figure_intro_pattern"],
        figure_explanation_depth=data["figure_explanation_depth"],
    )


def deserialize_aggregated_profile(data: dict) -> 'AggregatedProfile':
    """Reconstruct an AggregatedProfile from JSON dict"""
    from core.training.models import AggregatedProfile
    from datetime import datetime

    # The file structure has nested "profile" key
    profile_data = data.get("profile", data)

    # Deserialize style_variants
    style_variants = {}
    for key, style_data in profile_data.get("style_variants", {}).items():
        style_variants[key] = deserialize_style_profile(style_data)

    return AggregatedProfile(
        canonical_segment_sequence=profile_data["canonical_segment_sequence"],
        segment_duration_targets=profile_data["segment_duration_targets"],
        depth_targets=profile_data["depth_targets"],
        style_variants=style_variants,
        universal_intro_patterns=profile_data["universal_intro_patterns"],
        universal_transition_patterns=profile_data["universal_transition_patterns"],
        universal_figure_patterns=profile_data["universal_figure_patterns"],
        min_coverage=profile_data["min_coverage"],
        target_words_per_minute=tuple(profile_data["target_words_per_minute"]),
        target_concepts_per_minute=tuple(profile_data["target_concepts_per_minute"]),
        version=profile_data["version"],
        training_pairs_used=profile_data["training_pairs_used"],
        created_at=datetime.fromisoformat(profile_data["created_at"]),
    )


@click.group()
def training():
    """Training pipeline commands"""
    pass


@training.command()
@click.option('--pairs-dir', default='artifacts/training_data', help='Directory containing training pairs')
@click.option('--output-dir', default='artifacts/training_output', help='Output directory for results')
@click.option('--max-trials', default=5, help='Maximum number of training trials')
@click.option('--skip-audio', is_flag=True, help='Skip TTS audio generation (use reference audio for metrics)')
def run(pairs_dir, output_dir, max_trials, skip_audio):
    """Run the complete training pipeline"""
    asyncio.run(run_training_pipeline(pairs_dir, output_dir, max_trials, skip_audio))


async def run_training_pipeline(pairs_dir: str, output_dir: str, max_trials: int, skip_audio: bool):
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

        # Create document graph with PDF ingestion (or load from checkpoint)
        if not pair.document_graph:
            # Check for existing checkpoint
            kg_checkpoint = load_checkpoint(checkpoint_dir, pair.pair_id, "knowledge_graph")
            if kg_checkpoint:
                logger.info(f"  Loading knowledge graph from checkpoint for {pair.pair_id}")
                console.print("  [yellow]Loading knowledge graph from checkpoint...[/yellow]")
                try:
                    pair.document_graph = DocumentGraph.from_dict(kg_checkpoint)
                    logger.info(f"  Loaded: {len(pair.document_graph.atoms)} atoms, {len(pair.document_graph.key_themes)} themes")
                    console.print(f"  Atoms: {len(pair.document_graph.atoms)}, Themes: {len(pair.document_graph.key_themes)}")
                except Exception as e:
                    logger.warning(f"  Failed to load checkpoint, will re-ingest: {e}")
                    console.print(f"  [yellow]Checkpoint load failed, re-ingesting PDF...[/yellow]")
                    kg_checkpoint = None

            if not kg_checkpoint:
                logger.info(f"  Ingesting PDF for {pair.pair_id}")
                console.print("  Ingesting PDF (this will take a few minutes)...")
                try:
                    from agents.document_ingestor import DocumentIngestorAgent

                    # Use document ingestor to parse PDF
                    doc_agent = DocumentIngestorAgent(claude_client=claude_client, mock_mode=False)
                    doc_graph = await doc_agent.ingest(pair.pdf_path)

                    # Convert to KnowledgeGraph format
                    pair.document_graph = document_graph_to_knowledge_graph(doc_graph, pair.pair_id)

                    logger.info(f"  Ingested: {len(pair.document_graph.atoms)} atoms, {len(pair.document_graph.key_themes)} themes")
                    console.print(f"  Atoms: {len(pair.document_graph.atoms)}")
                    console.print(f"  Topics: {len(pair.document_graph.topic_index)}")
                    console.print(f"  Entities: {len(pair.document_graph.entity_index)}")

                    # Save checkpoint
                    save_checkpoint(checkpoint_dir, pair.pair_id, "knowledge_graph", pair.document_graph.to_dict())
                    logger.info(f"  Saved knowledge graph checkpoint for {pair.pair_id}")
                except Exception as e:
                    logger.error(f"  PDF ingestion failed for {pair.pair_id}: {e}")
                    console.print(f"  [red]Error: PDF ingestion failed: {e}[/red]")
                    import traceback
                    traceback.print_exc()

                    # Fallback to minimal graph
                    logger.warning(f"  Using minimal fallback graph for {pair.pair_id}")
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

                    # Log quality metrics if available in checkpoint
                    if "word_count" in checkpoint and "words_per_minute" in checkpoint:
                        logger.info(
                            f"  Loaded: {pair.duration_minutes:.1f} minutes, {len(pair.transcription.segments)} segments, "
                            f"{checkpoint['word_count']} words, {checkpoint['words_per_minute']:.1f} WPM"
                        )
                    else:
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

                    # Calculate quality metrics for checkpoint
                    word_count = len(pair.transcription.transcript_text.split())
                    words_per_minute = (word_count / pair.transcription.total_duration * 60) if pair.transcription.total_duration > 0 else 0
                    timestamp_count = len(pair.transcription.word_timestamps)
                    segment_coverage_percentage = (
                        (pair.transcription.segments[-1].end_time / pair.transcription.total_duration * 100)
                        if pair.transcription.segments and pair.transcription.total_duration > 0
                        else 0
                    )

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
                        # Quality metrics for analysis
                        "word_count": word_count,
                        "words_per_minute": words_per_minute,
                        "timestamp_count": timestamp_count,
                        "segment_coverage_percentage": segment_coverage_percentage,
                        "num_segments": len(pair.transcription.segments),
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
                try:
                    # Reconstruct AlignedSegments
                    pair.aligned_segments = [
                        deserialize_aligned_segment(seg_data)
                        for seg_data in analysis_checkpoint['aligned_segments']
                    ]

                    # Reconstruct StructureProfile
                    pair.structure_profile = deserialize_structure_profile(
                        analysis_checkpoint['structure_profile']
                    )

                    # Reconstruct StyleProfile
                    pair.style_profile = deserialize_style_profile(
                        analysis_checkpoint['style_profile']
                    )

                    logger.info(f"  Loaded {len(pair.aligned_segments)} segments from checkpoint")
                    console.print(f"  Loaded {len(pair.aligned_segments)} segments from checkpoint")

                except Exception as e:
                    logger.warning(f"  Failed to load analysis checkpoint, will re-analyze: {e}")
                    console.print(f"  [yellow]Checkpoint load failed, re-analyzing...[/yellow]")
                    analysis_checkpoint = None

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

                # Save analysis checkpoint with full data
                save_checkpoint(checkpoint_dir, pair.pair_id, "analysis", {
                    "aligned_segments": [serialize_aligned_segment(s) for s in pair.aligned_segments],
                    "structure_profile": serialize_structure_profile(pair.structure_profile),
                    "style_profile": serialize_style_profile(pair.style_profile),
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
            # Reconstruct AggregatedProfile object from data
            aggregated_profile = deserialize_aggregated_profile(profile_data)
        except Exception as e:
            logger.warning(f"Failed to load profile checkpoint: {e}")
            console.print(f"  [yellow]Checkpoint load failed, re-synthesizing...[/yellow]")
            aggregated_profile = None

    if not aggregated_profile:
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
            style_profile=aggregated_profile,
            skip_audio=skip_audio,
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


def document_graph_to_knowledge_graph(doc_graph, pair_id: str):
    """Convert DocumentGraph to KnowledgeGraph format"""
    from core.models.knowledge import KnowledgeGraph

    # Build topic and entity indices
    topic_index = {}
    entity_index = {}
    atom_sources = {}

    for atom_id, atom in doc_graph.atoms.items():
        # Map atoms to source
        atom_sources[atom_id] = pair_id

        # Index topics
        for topic in atom.topics:
            if topic not in topic_index:
                topic_index[topic] = []
            topic_index[topic].append(atom_id)

        # Index entities
        for entity in atom.entities:
            if entity not in entity_index:
                entity_index[entity] = []
            entity_index[entity].append(atom_id)

    # Extract key themes from most common topics
    topic_counts = [(topic, len(aids)) for topic, aids in topic_index.items()]
    topic_counts.sort(key=lambda x: x[1], reverse=True)
    key_themes = [topic for topic, _ in topic_counts[:10]]

    return KnowledgeGraph(
        project_id=pair_id,
        atoms=doc_graph.atoms,
        atom_sources=atom_sources,
        cross_links=[],
        topic_index=topic_index,
        entity_index=entity_index,
        unified_summary=doc_graph.full_summary or doc_graph.one_paragraph or "",
        key_themes=key_themes,
    )


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
