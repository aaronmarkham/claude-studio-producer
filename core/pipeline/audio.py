"""Audio generation for video scenes.

Scene-level TTS generation with ElevenLabs/OpenAI providers.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from core.models.structured_script import StructuredScript
from core.models.content_library import ContentLibrary, AssetType, AssetStatus
from core.content_librarian import ContentLibrarian

console = Console()

def _get_theme():
    from cli.theme import get_theme
    return get_theme()

async def generate_scene_audio(
    scenes: list,
    output_dir: Path,
    console,
    voice_id: str = "pFZP5JQG7iQjIQuC4Bku",  # Lily voice
    live: bool = False,
    script_text: str = None,
    structured_script: "StructuredScript" = None,
    content_library: "ContentLibrary" = None,
    language: str = "en",
) -> dict:
    """
    Generate audio for each scene using ElevenLabs (scene-by-scene to avoid length limits).

    Contract (UNIFIED_PRODUCTION_ARCHITECTURE.md):
    - READS: StructuredScript.segments[].text
    - WRITES: Audio files + registers them in ContentLibrary
    - WRITES: actual_duration_sec back to each segment

    When structured_script is provided (Unified Production Architecture):
    - Iterates over segments[].text (not flat script split by \\n\\n)
    - Uses segment.idx as audio ID for proper alignment
    - Writes actual_duration_sec back to each segment
    - Registers assets in ContentLibrary immediately

    Legacy mode (script_text provided):
    - Splits text by \\n\\n to get paragraphs
    - Uses paragraph index as audio ID

    Returns dict mapping audio_id -> audio_path
    """
    from core.secrets import get_api_key

    t = _get_theme()
    audio_paths = {}

    if not live:
        console.print(f"[{t.dimmed}]Mock mode: Skipping audio generation[/]")
        return audio_paths

    # Try ElevenLabs first, fall back to OpenAI TTS
    # Set TTS_PROVIDER=openai to force OpenAI TTS (e.g., when ElevenLabs quota is exhausted)
    import os as _os
    audio_provider = None
    force_provider = _os.environ.get("TTS_PROVIDER", "").lower()

    is_multilingual = language and language != "en"

    if force_provider != "openai":
        api_key = get_api_key("ELEVENLABS_API_KEY")
        if api_key:
            try:
                from core.providers.audio.elevenlabs import ElevenLabsProvider
                # Use multilingual v2 for non-English languages
                el_model = "eleven_multilingual_v2" if is_multilingual else "eleven_monolingual_v1"
                audio_provider = ElevenLabsProvider(model=el_model)
                lang_note = f" ({language}, multilingual)" if is_multilingual else ""
                console.print(f"[{t.label}]Using ElevenLabs TTS{lang_note}[/]")
            except Exception as e:
                console.print(f"[{t.warning}]ElevenLabs unavailable: {e}[/]")

    if audio_provider is None:
        openai_key = get_api_key("OPENAI_API_KEY")
        if openai_key:
            try:
                from core.providers.audio.openai_tts import OpenAITTSProvider
                from core.providers.base import AudioProviderConfig
                config = AudioProviderConfig(api_key=openai_key)
                audio_provider = OpenAITTSProvider(config, model="tts-1-hd")
                console.print(f"[{t.label}]Using OpenAI TTS (HD)[/]")
            except Exception as e:
                console.print(f"[{t.warning}]OpenAI TTS unavailable: {e}[/]")

    if audio_provider is None:
        console.print(f"[{t.error}]No TTS provider available - set ELEVENLABS_API_KEY or OPENAI_API_KEY[/]")

    # Map ElevenLabs voice IDs to OpenAI voices when using OpenAI TTS
    from core.providers.audio.openai_tts import OpenAITTSProvider as _OpenAITTS
    if isinstance(audio_provider, _OpenAITTS):
        voice_id = "onyx"  # Deep, authoritative — good for narration

    # Create audio directory
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    # Prepare librarian for asset registration (Unified Production Architecture)
    librarian = None
    if content_library is not None:
        from core.content_librarian import ContentLibrarian
        librarian = ContentLibrarian(content_library)

    # Priority 1: Use StructuredScript segments (Unified Production Architecture)
    # Priority 2: Use script_text split by paragraphs (legacy)
    # Priority 3: Use scene transcript segments (original transcription)
    audio_items = []  # List of (audio_id, text, segment_idx_or_none)

    if structured_script is not None:
        console.print(f"\n[{t.label}]Generating audio from StructuredScript ({len(structured_script.segments)} segments)...[/]")
        for seg in structured_script.segments:
            if seg.text and len(seg.text.strip()) >= 5:
                audio_items.append((f"audio_{seg.idx:03d}", seg.text, seg.idx))
    elif script_text:
        # Legacy: Split script into paragraphs (double newlines are natural breaks)
        paragraphs = [p.strip() for p in script_text.split('\n\n') if p.strip()]
        console.print(f"\n[{t.label}]Generating audio from script text ({len(paragraphs)} paragraphs)...[/]")
        audio_items = [(f"audio_{i:03d}", para, i) for i, para in enumerate(paragraphs)]
    else:
        console.print(f"\n[{t.label}]Generating scene-by-scene audio...[/]")
        for scene in scenes:
            text = scene.transcript_segment if isinstance(scene.transcript_segment, str) else ""
            if hasattr(scene.transcript_segment, 'text'):
                text = scene.transcript_segment.text
            if text and len(text.strip()) >= 5:
                audio_items.append((scene.scene_id, text, None))

    # Build items list and segment map for post-processing
    from core.audio_utils import generate_audio_chunks
    items = [(audio_id, text) for audio_id, text, _ in audio_items]
    segment_map = {audio_id: seg_idx for audio_id, _, seg_idx in audio_items}

    # Progress callback wired to Rich Progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console
    ) as progress:
        prog_task = progress.add_task("Generating audio...", total=len(items))

        def _on_complete(idx, total, audio_id):
            progress.update(prog_task, description=f"Audio: {audio_id[:15]}...")
            progress.advance(prog_task)

        def _on_error(audio_id, exc):
            console.print(f"[{t.warning}]Audio failed for {audio_id}: {exc}[/]")

        chunks = await generate_audio_chunks(
            provider=audio_provider,
            items=items,
            output_dir=audio_dir,
            voice_id=voice_id,
            on_chunk_complete=_on_complete,
            on_chunk_error=_on_error,
        )

    # Post-process: populate audio_paths, write back to StructuredScript, register in ContentLibrary
    total_chars = sum(c.char_count for c in chunks)
    total_cost = sum(c.estimated_cost for c in chunks)

    for chunk in chunks:
        audio_paths[chunk.audio_id] = str(chunk.path)
        seg_idx = segment_map.get(chunk.audio_id)

        # Write actual_duration_sec back to StructuredScript segment
        if structured_script is not None and seg_idx is not None:
            seg = structured_script.get_segment(seg_idx)
            if seg:
                seg.actual_duration_sec = chunk.duration_sec
                seg.audio_file = str(chunk.path)

        # Register audio asset in ContentLibrary immediately
        if librarian is not None and seg_idx is not None:
            from core.models.content_library import AssetRecord, AssetType, AssetSource, AssetStatus
            asset = AssetRecord(
                asset_id=f"aud_{seg_idx:04d}",
                asset_type=AssetType.AUDIO,
                source=AssetSource.ELEVENLABS,
                status=AssetStatus.DRAFT,
                segment_idx=seg_idx,
                path=str(chunk.path),
                duration_sec=chunk.duration_sec,
            )
            librarian.library.register(asset)

    console.print(f"[{t.success}]Generated {len(audio_paths)} audio clips[/]")
    console.print(f"[{t.dimmed}]Total characters: {total_chars} | Est. cost: ${total_cost:.3f}[/]")

    return audio_paths
