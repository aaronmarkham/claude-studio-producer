"""Pipeline runner — executes stages with manifest checkpointing.

Bridges the unified produce CLI to the actual production pipeline.
Each stage updates the manifest so runs can be resumed.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models.run_manifest import (
    RunManifest, RunStage, SourceType, SceneStatus,
    SceneManifest, AudioManifest, BudgetManifest,
)


async def run_pipeline(manifest: RunManifest, provider: str = "auto",
                       voice: str = "nova", duration: float = 60.0,
                       interactive: bool = False, language: str = None):
    """Execute the production pipeline from the manifest's current stage.

    Calls into existing pipeline functions, wrapping each stage
    with manifest save/load for checkpointing.
    """
    if manifest.stage in (RunStage.COMPLETE, RunStage.FAILED):
        print(f"Run {manifest.run_id} is already {manifest.stage.value}")
        return

    try:
        # Stage: INIT → PLAN
        if manifest.stage in (RunStage.INIT, RunStage.PLAN):
            await stage_plan(manifest, duration, interactive)

        # Stage: PLAN → PRODUCTION
        if manifest.stage == RunStage.PLAN:
            manifest.stage = RunStage.PRODUCTION
            manifest.save()

        # Stage: PRODUCTION (generate assets)
        if manifest.stage == RunStage.PRODUCTION:
            await stage_produce(manifest, provider)

        # Stage: AUDIO
        if manifest.stage == RunStage.AUDIO:
            await stage_audio(manifest, voice, language=language or manifest.language)

        # Stage: ASSEMBLY
        if manifest.stage == RunStage.ASSEMBLY:
            await stage_assemble(manifest)

    except Exception as e:
        manifest.stage = RunStage.FAILED
        manifest.save()
        raise


async def stage_plan(manifest: RunManifest, duration: float = 60.0,
                     interactive: bool = False):
    """Plan stage: load sources, generate script outline, select figures.

    For PAPER/SCRIPT sources: delegates to existing pipeline for script parsing.
    For TOPIC: would do research first (not yet wired).
    For PROJECT: would hydrate shards + gather multi-source (not yet wired).
    """
    from core.pipeline.video_stages import load_training_trial, script_segments_to_aligned

    run_dir = Path(manifest.run_dir)

    if manifest.source_type == SourceType.SCRIPT and manifest.script_path:
        # Parse script file into scenes
        from core.models.structured_script import StructuredScript

        script_file = Path(manifest.script_path)
        script_text = script_file.read_text(encoding="utf-8")
        manifest.script_text = script_text

        structured_script = StructuredScript.from_script_text(
            script_text=script_text,
            trial_id=manifest.run_id,
        )

        # Convert segments to scene manifests
        for i, segment in enumerate(structured_script.segments):
            scene_id = f"scene_{i+1:03d}"
            scene_duration = duration / len(structured_script.segments)
            manifest.scenes.append(SceneManifest(
                scene_id=scene_id,
                title=getattr(segment, 'title', '') or f"Scene {i+1}",
                status=SceneStatus.PENDING,
                duration=scene_duration,
                provider="auto",
            ))

        # Save script to run directory
        script_out = run_dir / "script.txt"
        script_out.write_text(script_text, encoding="utf-8")

    elif manifest.source_type == SourceType.PAPER and manifest.kb_project:
        # Load KB and generate real script via ScriptWriterAgent
        from core.pipeline.script_gen import generate_script_from_kb, present_figure_options

        try:
            scene_manifests = await generate_script_from_kb(
                manifest,
                prompt=manifest.prompt,
                duration=duration,
                style=manifest.style,
            )
            manifest.scenes = scene_manifests

            # Interactive figure selection
            if interactive:
                present_figure_options(manifest)
        except Exception as e:
            print(f"⚠️  Script generation failed ({e}), falling back to placeholder plan")
            _run_kb_produce(manifest)

    elif manifest.source_type == SourceType.TOPIC:
        # Research → KB → script (future)
        print(f"⚠️  Topic mode not yet fully wired — creating placeholder plan")
        for i in range(6):  # Default 6 scenes
            manifest.scenes.append(SceneManifest(
                scene_id=f"scene_{i+1:03d}",
                title=f"Scene {i+1}",
                status=SceneStatus.PENDING,
                duration=duration / 6,
            ))

    elif manifest.source_type == SourceType.PROJECT:
        # Multi-source synthesis (future)
        print(f"⚠️  Project mode not yet fully wired — creating placeholder plan")
        for i in range(6):
            manifest.scenes.append(SceneManifest(
                scene_id=f"scene_{i+1:03d}",
                title=f"Scene {i+1}",
                status=SceneStatus.PENDING,
                duration=duration / 6,
            ))

    manifest.stage = RunStage.PLAN
    manifest.save()
    print(f"📋 Plan complete: {len(manifest.scenes)} scenes")


async def stage_produce(manifest: RunManifest, provider: str = "auto"):
    """Production stage: generate video/image assets for each scene."""
    run_dir = Path(manifest.run_dir)
    output_dir = run_dir / "production"
    output_dir.mkdir(parents=True, exist_ok=True)

    pending = [s for s in manifest.scenes if s.status == SceneStatus.PENDING]
    print(f"🎬 Producing {len(pending)} scenes...")

    for scene in pending:
        scene_provider = scene.provider if scene.provider != "auto" else provider

        if scene_provider == "local_asset" and scene.asset_path:
            # Use LocalAssetProvider
            from core.providers.local_asset import LocalAssetProvider
            lap = LocalAssetProvider()
            output_path = output_dir / f"{scene.scene_id}.mp4"
            result = await lap.generate_video(
                prompt=scene.title,
                duration=scene.duration,
                asset_path=scene.asset_path,
                output_path=str(output_path),
            )
            if result.success:
                scene.status = SceneStatus.READY
                scene.asset_path = result.video_path
                scene.cost = result.cost or 0.0
            else:
                scene.status = SceneStatus.FAILED
                scene.error = result.error_message
                scene.attempts += 1

        elif scene_provider in ("luma", "auto") and manifest.live:
            # Use Luma provider
            try:
                from cli.produce_video import _produce_video_async
                # For now, mark as pending — full Luma integration
                # requires the visual plan + prompt pipeline
                scene.status = SceneStatus.PENDING
                print(f"  ⏳ {scene.scene_id}: Luma generation requires full pipeline (use cs produce-video for now)")
            except Exception as e:
                scene.status = SceneStatus.FAILED
                scene.error = str(e)
                scene.attempts += 1

        elif scene_provider in ("mock", "auto"):
            # Mock mode — create placeholder
            output_path = output_dir / f"{scene.scene_id}.mp4"
            # Create a tiny placeholder file
            output_path.write_bytes(b"MOCK_VIDEO")
            scene.status = SceneStatus.READY
            scene.asset_path = str(output_path)
            scene.cost = 0.0
            print(f"  ✅ {scene.scene_id}: {scene.title} (mock)")

        manifest.budget.record_spend(scene.scene_id, scene.cost)
        manifest.save()  # Checkpoint after each scene

    if manifest.all_scenes_done:
        manifest.stage = RunStage.AUDIO
        manifest.save()
        print(f"✅ All {len(manifest.scenes)} scenes ready")
    else:
        failed = manifest.scenes_failed
        print(f"⚠️  {failed} scene(s) failed — use `cs produce edit` to retry")


async def stage_audio(manifest: RunManifest, voice: str = "nova",
                      language: str = "en"):
    """Audio stage: generate TTS narration."""
    run_dir = Path(manifest.run_dir)
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    manifest.audio.voice = voice

    is_multilingual = language and language != "en"

    if manifest.script_text and manifest.live:
        # Generate real TTS
        try:
            from core.providers.audio.openai_tts import OpenAITTSProvider
            from core.providers.base import AudioProviderConfig
            from core.secrets import get_api_key

            # Try ElevenLabs first for multilingual support
            tts = None
            if is_multilingual:
                el_key = get_api_key("ELEVENLABS_API_KEY")
                if el_key:
                    try:
                        from core.providers.audio.elevenlabs import ElevenLabsProvider
                        tts = ElevenLabsProvider(model="eleven_multilingual_v2")
                        print(f"🌐 Using ElevenLabs multilingual v2 ({language})")
                    except Exception:
                        pass

            if tts is None:
                config = AudioProviderConfig(api_key=get_api_key("OPENAI_API_KEY"))
                tts = OpenAITTSProvider(config)
                if is_multilingual:
                    print(f"🌐 Using OpenAI TTS ({language} — auto-detected from text)")

            narration_path = audio_dir / "narration.mp3"
            result = await tts.generate_speech(
                text=manifest.script_text,
                voice_id=voice,
            )
            if result.success and result.audio_data:
                narration_path.write_bytes(result.audio_data)
                manifest.audio.narration_path = str(narration_path)
                manifest.audio.status = "ready"
                manifest.audio.cost = result.cost or 0.0
                print(f"🎤 Narration generated: {narration_path}")
            else:
                manifest.audio.status = "failed"
                manifest.audio.error = result.error_message
        except Exception as e:
            manifest.audio.status = "failed"
            manifest.audio.error = str(e)
    else:
        # Mock audio
        narration_path = audio_dir / "narration.mp3"
        narration_path.write_bytes(b"MOCK_AUDIO")
        manifest.audio.narration_path = str(narration_path)
        manifest.audio.status = "ready"
        manifest.audio.cost = 0.0
        print(f"🎤 Mock narration created")

    manifest.stage = RunStage.ASSEMBLY
    manifest.save()


async def stage_assemble(manifest: RunManifest):
    """Assembly stage: combine video clips + audio into final output."""
    run_dir = Path(manifest.run_dir)
    output_path = run_dir / "final.mp4"

    ready_scenes = [s for s in manifest.scenes
                    if s.status in (SceneStatus.READY, SceneStatus.REPLACED)]

    if not ready_scenes:
        print("❌ No ready scenes to assemble")
        manifest.stage = RunStage.FAILED
        manifest.save()
        return

    # For real assembly, use ffmpeg concat
    real_clips = [s for s in ready_scenes
                  if s.asset_path and Path(s.asset_path).exists()
                  and Path(s.asset_path).stat().st_size > 100]

    if real_clips:
        # Build ffmpeg concat file
        concat_path = run_dir / "concat.txt"
        with open(concat_path, "w") as f:
            for scene in real_clips:
                f.write(f"file '{scene.asset_path}'\n")

        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_path),
            "-c", "copy",
            str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            # Try re-encoding if concat copy fails
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_path),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

    if output_path.exists():
        manifest.output_path = str(output_path)
        manifest.stage = RunStage.COMPLETE
        manifest.save()
        print(f"🎬 Final video: {output_path}")
        print(f"   Scenes: {len(ready_scenes)} | Cost: ${manifest.budget.spent:.2f}")
    else:
        # Mock mode — just mark complete
        manifest.output_path = str(output_path)
        manifest.stage = RunStage.COMPLETE
        manifest.save()
        print(f"✅ Assembly complete (mock)")

    print(f"\n{manifest.timeline()}")


def _run_kb_produce(manifest: RunManifest):
    """Bridge KB produce to the manifest-based pipeline.

    Loads KB project and creates scene placeholders from its content.
    """
    from core.pipeline.figures import load_kb_figures

    kb_data = None
    if manifest.kb_project:
        try:
            kb_data = load_kb_figures(manifest.kb_project)
            figure_count = len(kb_data.get("figure_paths", {}))
            print(f"📚 KB loaded: {manifest.kb_project} ({figure_count} figures)")
        except Exception as e:
            print(f"⚠️  KB load failed: {e}")

    # Create default scene plan based on estimated content
    scene_count = 6
    duration_each = 10.0

    for i in range(scene_count):
        manifest.scenes.append(SceneManifest(
            scene_id=f"scene_{i+1:03d}",
            title=f"Scene {i+1}",
            status=SceneStatus.PENDING,
            duration=duration_each,
            provider="auto",
        ))
