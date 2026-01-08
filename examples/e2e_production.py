"""
End-to-end production pipeline test

Runs the full video production pipeline from concept to final edit.
Supports both mock mode (for testing) and live mode (with real API calls).

Usage:
    python examples/e2e_production.py --mock
    python examples/e2e_production.py --live --budget 15 --concept "Product demo for a todo app"
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.producer import ProducerAgent, PilotStrategy
from agents.script_writer import ScriptWriterAgent, Scene
from agents.video_generator import VideoGeneratorAgent, GeneratedVideo
from agents.audio_generator import AudioGeneratorAgent
from agents.critic import CriticAgent, PilotResults, SceneResult
from agents.qa_verifier import QAVerifierAgent, QAResult
from agents.editor import EditorAgent
from core.claude_client import ClaudeClient
from core.budget import ProductionTier
from core.models.audio import AudioTier
from core.models.edit_decision import EditDecisionList, ExportFormat
from core.models.render import AudioTrack, TrackType, RenderResult
from core.models.seed_assets import SeedAsset, SeedAssetCollection, SeedAssetType, AssetRole
from core.renderer import FFmpegRenderer
from core.providers import MockVideoProvider
from core.providers.video.runway import RunwayProvider
from core.providers.video.luma import LumaProvider
from core.providers.audio.openai_tts import OpenAITTSProvider
from core.providers.base import AudioProviderConfig, VideoProviderConfig, ProviderType


class ProductionPipeline:
    """
    Full end-to-end video production pipeline.

    Orchestrates all agents from concept to final edit.
    """

    def __init__(
        self,
        concept: str,
        budget: float,
        audio_tier: AudioTier = AudioTier.SIMPLE_OVERLAY,
        use_live_providers: bool = False,
        run_id: Optional[str] = None,
        seed_assets: Optional[SeedAssetCollection] = None
    ):
        """
        Args:
            concept: Video concept description
            budget: Total budget in USD
            audio_tier: Audio production tier
            use_live_providers: If True, use real API providers; if False, use mocks
            run_id: Optional run ID (auto-generated if not provided)
            seed_assets: Optional collection of seed assets (images, etc.)
        """
        self.concept = concept
        self.budget = budget
        self.audio_tier = audio_tier
        self.use_live_providers = use_live_providers
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.seed_assets = seed_assets or SeedAssetCollection()

        # Create output directories
        self.run_dir = Path("artifacts/runs") / self.run_id
        self.scenes_dir = self.run_dir / "scenes"
        self.videos_dir = self.run_dir / "videos"
        self.audio_dir = self.run_dir / "audio"
        self.edl_dir = self.run_dir / "edl"
        self.render_dir = self.run_dir / "renders"

        for dir_path in [self.scenes_dir, self.videos_dir, self.audio_dir, self.edl_dir, self.render_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Initialize Claude client
        self.claude = ClaudeClient()

        # Tracking
        self.metadata = {
            "run_id": self.run_id,
            "concept": concept,
            "budget": budget,
            "audio_tier": audio_tier.value,
            "use_live_providers": use_live_providers,
            "start_time": datetime.now().isoformat(),
            "stages": {},
            "costs": {
                "video": 0.0,
                "audio": 0.0,
                "total": 0.0
            },
            "errors": []
        }

    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Use plain text on Windows to avoid emoji encoding issues
        if sys.platform == "win32":
            prefix = {
                "INFO": "[INFO]   ",
                "SUCCESS": "[OK]     ",
                "ERROR": "[ERROR]  ",
                "WARNING": "[WARN]   ",
                "STAGE": "[STAGE]  "
            }.get(level, "         ")
            # Remove emojis from message on Windows
            import re
            message = re.sub(r'[^\x00-\x7F]+', '', message)
        else:
            prefix = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✅",
                "ERROR": "❌",
                "WARNING": "⚠️ ",
                "STAGE": "🎬"
            }.get(level, "  ")
        print(f"[{timestamp}] {prefix} {message}")

    def save_metadata(self):
        """Save metadata to disk"""
        metadata_path = self.run_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    async def run(self) -> Dict:
        """
        Run the full production pipeline.

        Returns:
            Dictionary with results and metadata
        """
        try:
            self.log(f"Starting production pipeline - Run ID: {self.run_id}", "STAGE")
            self.log(f"Concept: {self.concept}")
            self.log(f"Budget: ${self.budget:.2f}")
            self.log(f"Audio Tier: {self.audio_tier.value}")
            self.log(f"Mode: {'LIVE' if self.use_live_providers else 'MOCK'}")
            print()

            # Stage 1: Producer - Create pilot strategies
            pilot_strategy = await self._run_producer()

            # Stage 2: Script Writer - Generate scenes
            scenes = await self._run_script_writer(pilot_strategy)

            # Stage 3: Video Generator - Generate videos
            video_candidates = await self._run_video_generator(scenes, pilot_strategy)

            # Stage 4: Audio Generator - Generate audio
            scene_audio = await self._run_audio_generator(scenes)

            # Stage 5: QA Verifier - Verify quality
            qa_results = await self._run_qa_verifier(scenes, video_candidates, pilot_strategy)

            # Stage 6: Critic - Evaluate results
            evaluation = await self._run_critic(pilot_strategy, scenes, video_candidates, qa_results)

            # Stage 7: Editor - Create EDL
            edl = await self._run_editor(scenes, video_candidates, qa_results)

            # Stage 8: Renderer - Combine video + audio into final output
            render_result = await self._run_renderer(edl, scene_audio)

            # Finalize
            self.metadata["end_time"] = datetime.now().isoformat()
            self.metadata["status"] = "completed"
            self.save_metadata()

            self._print_summary(edl, render_result)

            return {
                "success": True,
                "run_id": self.run_id,
                "run_dir": str(self.run_dir),
                "pilot_strategy": pilot_strategy,
                "scenes": scenes,
                "video_candidates": video_candidates,
                "scene_audio": scene_audio,
                "qa_results": qa_results,
                "evaluation": evaluation,
                "edl": edl,
                "render_result": render_result,
                "metadata": self.metadata
            }

        except Exception as e:
            self.log(f"Pipeline failed: {str(e)}", "ERROR")
            self.metadata["status"] = "failed"
            self.metadata["error"] = str(e)
            self.metadata["end_time"] = datetime.now().isoformat()
            self.save_metadata()
            raise

    async def _run_producer(self) -> PilotStrategy:
        """Stage 1: Producer - Create pilot strategies"""
        self.log("Stage 1: Producer - Creating pilot strategies", "STAGE")
        start_time = datetime.now()

        try:
            producer = ProducerAgent(claude_client=self.claude)

            # Get pilot strategies
            pilots = await producer.analyze_and_plan(
                user_request=self.concept,
                total_budget=self.budget
            )

            # Use first pilot for now (could implement selection logic)
            pilot = pilots[0]

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["producer"] = {
                "duration_seconds": elapsed,
                "pilot_selected": {
                    "tier": pilot.tier.value,
                    "allocated_budget": pilot.allocated_budget,
                    "test_scene_count": pilot.test_scene_count
                }
            }

            self.log(f"Selected pilot: {pilot.tier.value}", "SUCCESS")
            self.log(f"Budget allocated: ${pilot.allocated_budget:.2f}")
            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return pilot

        except Exception as e:
            self.metadata["errors"].append({"stage": "producer", "error": str(e)})
            raise

    async def _run_script_writer(self, pilot: PilotStrategy) -> List[Scene]:
        """Stage 2: Script Writer - Generate scenes"""
        self.log("Stage 2: Script Writer - Generating scenes", "STAGE")
        start_time = datetime.now()

        try:
            script_writer = ScriptWriterAgent(claude_client=self.claude)

            # Generate scenes
            scenes = await script_writer.create_script(
                video_concept=self.concept,
                production_tier=pilot.tier,
                target_duration=30.0,  # 30 second video
                num_scenes=None  # Let the agent decide based on duration
            )

            # Save scenes to disk
            for scene in scenes:
                scene_path = self.scenes_dir / f"{scene.scene_id}.json"
                with open(scene_path, 'w') as f:
                    json.dump({
                        "scene_id": scene.scene_id,
                        "title": scene.title,
                        "description": scene.description,
                        "duration": scene.duration,
                        "visual_elements": scene.visual_elements,
                        "audio_notes": scene.audio_notes,
                        "voiceover_text": scene.voiceover_text,
                        "transition_in": scene.transition_in,
                        "transition_out": scene.transition_out
                    }, f, indent=2)

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["script_writer"] = {
                "duration_seconds": elapsed,
                "num_scenes": len(scenes),
                "total_duration": sum(s.duration for s in scenes),
                "scenes": [s.scene_id for s in scenes]
            }

            self.log(f"Generated {len(scenes)} scenes", "SUCCESS")
            self.log(f"Total video duration: {sum(s.duration for s in scenes):.1f}s")
            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return scenes

        except Exception as e:
            self.metadata["errors"].append({"stage": "script_writer", "error": str(e)})
            raise

    async def _run_video_generator(
        self,
        scenes: List[Scene],
        pilot: PilotStrategy
    ) -> Dict[str, List[GeneratedVideo]]:
        """Stage 3: Video Generator - Generate videos"""
        self.log("Stage 3: Video Generator - Generating videos", "STAGE")
        start_time = datetime.now()

        try:
            # Create video provider
            # Get seed images for video generation (Runway requires an input image)
            seed_images = self.seed_assets.get_by_type(SeedAssetType.IMAGE)
            seed_image_path = seed_images[0].file_path if seed_images else None

            # Track actual provider used for clarity
            actual_provider_name = None

            if self.use_live_providers:
                # Prefer Luma - supports text-to-video without seed images
                luma_key = os.getenv("LUMA_API_KEY")
                runway_key = os.getenv("RUNWAY_API_KEY")

                if luma_key:
                    # Luma supports text-to-video - no seed image required!
                    self.log("Using LIVE provider: Luma (text-to-video)", "SUCCESS")
                    video_provider = LumaProvider()
                    actual_provider_name = "luma"
                elif runway_key and seed_image_path:
                    # Runway requires seed image for image-to-video
                    self.log(f"Using LIVE provider: Runway (image: {seed_image_path})", "SUCCESS")
                    config = VideoProviderConfig(
                        provider_type=ProviderType.RUNWAY,
                        api_key=runway_key,
                        timeout=300
                    )
                    video_provider = RunwayProvider(config=config)
                    actual_provider_name = "runway"
                elif runway_key:
                    self.log("=" * 60, "WARNING")
                    self.log("FALLBACK TO MOCK: RUNWAY_API_KEY set but no seed image!", "WARNING")
                    self.log("Add --seed-asset path/to/image.jpg to use Runway", "WARNING")
                    self.log("Videos will be SIMULATED, not real API calls", "WARNING")
                    self.log("=" * 60, "WARNING")
                    video_provider = MockVideoProvider()
                    actual_provider_name = "mock"
                else:
                    self.log("=" * 60, "WARNING")
                    self.log("FALLBACK TO MOCK: No video API keys found!", "WARNING")
                    self.log("Set LUMA_API_KEY or RUNWAY_API_KEY for live generation", "WARNING")
                    self.log("Videos will be SIMULATED, not real API calls", "WARNING")
                    self.log("=" * 60, "WARNING")
                    video_provider = MockVideoProvider()
                    actual_provider_name = "mock"
            else:
                self.log("Using MOCK provider (--mock mode)", "INFO")
                video_provider = MockVideoProvider()
                actual_provider_name = "mock"

            # Store in metadata for clarity
            self.metadata["actual_video_provider"] = actual_provider_name

            video_generator = VideoGeneratorAgent(
                provider=video_provider,
                num_variations=2  # Generate 2 variations per scene
            )

            # Generate videos for each scene
            video_candidates = {}
            total_cost = 0.0

            for scene in scenes:
                self.log(f"Generating videos for {scene.scene_id}...")

                videos = await video_generator.generate_scene(
                    scene=scene,
                    production_tier=pilot.tier,
                    budget_limit=pilot.allocated_budget / len(scenes),
                    num_variations=2,
                    image_url=seed_image_path  # Pass seed image to provider
                )

                video_candidates[scene.scene_id] = videos

                # Download videos to local storage
                for i, video in enumerate(videos):
                    if video.video_url and video.video_url.startswith("http"):
                        local_path = self.videos_dir / f"{scene.scene_id}_v{i}.mp4"
                        self.log(f"  Downloading video {i} to {local_path.name}...")
                        success = await video_provider.download_video(video.video_url, str(local_path))
                        if success:
                            video.video_url = str(local_path)  # Update to local path
                        else:
                            self.log(f"  Warning: Failed to download video {i}", "INFO")

                # Calculate cost
                scene_cost = sum(v.generation_cost for v in videos)
                total_cost += scene_cost

                self.log(f"  Generated {len(videos)} variations (${scene_cost:.2f})")

            self.metadata["costs"]["video"] = total_cost
            self.metadata["costs"]["total"] += total_cost

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["video_generator"] = {
                "duration_seconds": elapsed,
                "num_videos": sum(len(v) for v in video_candidates.values()),
                "cost": total_cost,
                "scenes_processed": len(video_candidates)
            }

            self.log(f"Generated {sum(len(v) for v in video_candidates.values())} videos", "SUCCESS")
            self.log(f"Video cost: ${total_cost:.2f}")
            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return video_candidates

        except Exception as e:
            self.metadata["errors"].append({"stage": "video_generator", "error": str(e)})
            raise

    async def _run_audio_generator(self, scenes: List[Scene]) -> List:
        """Stage 4: Audio Generator - Generate audio"""
        self.log("Stage 4: Audio Generator - Generating audio", "STAGE")
        start_time = datetime.now()

        try:
            # Create audio provider
            actual_audio_provider = None

            if self.use_live_providers:
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    self.log("FALLBACK TO MOCK: OPENAI_API_KEY not set", "WARNING")
                    self.log("Audio will be SIMULATED, not real TTS", "WARNING")
                    audio_provider = None  # Use mock
                    actual_audio_provider = "mock"
                else:
                    self.log("Using LIVE provider: OpenAI TTS", "SUCCESS")
                    config = AudioProviderConfig(api_key=api_key, timeout=60)
                    audio_provider = OpenAITTSProvider(config=config, model="tts-1")
                    actual_audio_provider = "openai_tts"
            else:
                self.log("Using MOCK audio provider (--mock mode)", "INFO")
                audio_provider = None  # Use mock
                actual_audio_provider = "mock"

            self.metadata["actual_audio_provider"] = actual_audio_provider

            audio_generator = AudioGeneratorAgent(
                claude_client=self.claude,
                audio_provider=audio_provider
            )

            # Generate audio for each scene
            scene_audio = await audio_generator.run(
                scenes=scenes,
                audio_tier=self.audio_tier,
                budget_limit=self.budget * 0.2  # Allocate 20% of budget to audio
            )

            # Calculate cost (mock mode has minimal cost)
            # In real mode, costs would come from actual audio generation
            total_cost = len(scene_audio) * 0.05  # Estimate $0.05 per scene

            self.metadata["costs"]["audio"] = total_cost
            self.metadata["costs"]["total"] += total_cost

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["audio_generator"] = {
                "duration_seconds": elapsed,
                "num_scenes": len(scene_audio),
                "cost": total_cost,
                "audio_tier": self.audio_tier.value
            }

            self.log(f"Generated audio for {len(scene_audio)} scenes", "SUCCESS")
            self.log(f"Audio cost: ${total_cost:.2f}")
            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return scene_audio

        except Exception as e:
            self.metadata["errors"].append({"stage": "audio_generator", "error": str(e)})
            raise

    async def _run_qa_verifier(
        self,
        scenes: List[Scene],
        video_candidates: Dict[str, List[GeneratedVideo]],
        pilot: PilotStrategy
    ) -> Dict[str, List[QAResult]]:
        """Stage 5: QA Verifier - Verify quality"""
        self.log("Stage 5: QA Verifier - Verifying quality", "STAGE")
        start_time = datetime.now()

        try:
            qa_verifier = QAVerifierAgent(claude_client=self.claude)

            # Verify each video
            qa_results = {}
            total_videos = 0
            passed_videos = 0

            for scene in scenes:
                videos = video_candidates.get(scene.scene_id, [])
                scene_qa = []

                for video in videos:
                    result = await qa_verifier.verify_video(
                        scene=scene,
                        generated_video=video,
                        original_request=self.concept,
                        production_tier=pilot.tier
                    )
                    # Set quality score on video
                    video.quality_score = result.overall_score

                    scene_qa.append(result)
                    total_videos += 1
                    if result.passed:
                        passed_videos += 1

                qa_results[scene.scene_id] = scene_qa

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["qa_verifier"] = {
                "duration_seconds": elapsed,
                "total_videos": total_videos,
                "passed_videos": passed_videos,
                "pass_rate": passed_videos / total_videos if total_videos > 0 else 0.0
            }

            self.log(f"Verified {total_videos} videos", "SUCCESS")
            self.log(f"Pass rate: {passed_videos}/{total_videos} ({100*passed_videos/total_videos:.1f}%)")
            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return qa_results

        except Exception as e:
            self.metadata["errors"].append({"stage": "qa_verifier", "error": str(e)})
            raise

    async def _run_critic(
        self,
        pilot: PilotStrategy,
        scenes: List[Scene],
        video_candidates: Dict[str, List[GeneratedVideo]],
        qa_results: Dict[str, List[QAResult]]
    ):
        """Stage 6: Critic - Evaluate results"""
        self.log("Stage 6: Critic - Evaluating results", "STAGE")
        start_time = datetime.now()

        try:
            critic = CriticAgent(claude_client=self.claude)

            # Convert videos to SceneResults for critic
            scene_results = []
            for scene in scenes:
                videos = video_candidates.get(scene.scene_id, [])
                if videos:
                    # Use first video (or could pick best QA score)
                    video = videos[0]
                    scene_results.append(SceneResult(
                        scene_id=scene.scene_id,
                        description=scene.description,
                        video_url=video.video_url,
                        qa_score=video.quality_score or 0.0,
                        generation_cost=video.generation_cost
                    ))

            # Evaluate pilot
            evaluation = await critic.evaluate_pilot(
                original_request=self.concept,
                pilot=pilot,
                scene_results=scene_results,
                budget_spent=self.metadata["costs"]["total"],
                budget_allocated=pilot.allocated_budget
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["critic"] = {
                "duration_seconds": elapsed,
                "approved": evaluation.approved,
                "critic_score": evaluation.critic_score,
                "avg_qa_score": evaluation.avg_qa_score
            }

            self.log(f"Evaluation: {'APPROVED' if evaluation.approved else 'REJECTED'}", "SUCCESS")
            self.log(f"Critic score: {evaluation.critic_score:.1f}/100")
            self.log(f"Avg QA score: {evaluation.avg_qa_score:.1f}/100")
            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return evaluation

        except Exception as e:
            self.metadata["errors"].append({"stage": "critic", "error": str(e)})
            raise

    async def _run_editor(
        self,
        scenes: List[Scene],
        video_candidates: Dict[str, List[GeneratedVideo]],
        qa_results: Dict[str, List[QAResult]]
    ) -> EditDecisionList:
        """Stage 7: Editor - Create EDL"""
        self.log("Stage 7: Editor - Creating Edit Decision List", "STAGE")
        start_time = datetime.now()

        try:
            editor = EditorAgent(claude_client=self.claude)

            # Create EDL with 3 candidates
            edl = await editor.run(
                scenes=scenes,
                video_candidates=video_candidates,
                qa_results=qa_results,
                original_request=self.concept,
                num_candidates=3
            )

            # Export EDL to JSON
            edl_path = self.edl_dir / "edit_candidates.json"
            for candidate in edl.candidates:
                candidate_export = editor.export(candidate, ExportFormat.JSON)
                candidate_path = self.edl_dir / f"{candidate.candidate_id}.json"
                with open(candidate_path, 'w') as f:
                    f.write(candidate_export)

            # Save full EDL metadata
            with open(edl_path, 'w') as f:
                json.dump({
                    "edl_id": edl.edl_id,
                    "project_name": edl.project_name,
                    "recommended_candidate_id": edl.recommended_candidate_id,
                    "total_scenes": edl.total_scenes,
                    "num_candidates": len(edl.candidates),
                    "candidates": [
                        {
                            "candidate_id": c.candidate_id,
                            "name": c.name,
                            "style": c.style,
                            "total_duration": c.total_duration,
                            "estimated_quality": c.estimated_quality,
                            "description": c.description
                        }
                        for c in edl.candidates
                    ]
                }, f, indent=2)

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["editor"] = {
                "duration_seconds": elapsed,
                "num_candidates": len(edl.candidates),
                "recommended": edl.recommended_candidate_id,
                "edl_path": str(edl_path)
            }

            self.log(f"Created {len(edl.candidates)} edit candidates", "SUCCESS")
            self.log(f"Recommended: {edl.recommended_candidate_id}")
            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return edl

        except Exception as e:
            self.metadata["errors"].append({"stage": "editor", "error": str(e)})
            raise

    async def _run_renderer(self, edl: EditDecisionList, scene_audio: List) -> RenderResult:
        """Stage 8: Renderer - Combine video + audio into final output"""
        self.log("Stage 8: Renderer - Creating final video", "STAGE")
        start_time = datetime.now()

        try:
            # Initialize renderer
            renderer = FFmpegRenderer(output_dir=str(self.render_dir))

            # Check if FFmpeg is available
            ffmpeg_check = await renderer.check_ffmpeg_installed()
            if not ffmpeg_check["installed"]:
                self.log("FFmpeg not installed - skipping render", "INFO")
                self.log("Install FFmpeg to enable final video rendering", "INFO")
                return RenderResult(
                    success=False,
                    error_message="FFmpeg not installed"
                )

            self.log(f"FFmpeg found: {ffmpeg_check.get('version', 'unknown')[:50]}...")

            # Build audio tracks from scene_audio
            audio_tracks = []
            current_time = 0.0

            for i, audio in enumerate(scene_audio):
                # Extract voiceover if available
                if hasattr(audio, 'voiceover') and audio.voiceover:
                    vo = audio.voiceover
                    if hasattr(vo, 'audio_path') and vo.audio_path:
                        audio_tracks.append(AudioTrack(
                            path=vo.audio_path,
                            start_time=current_time,
                            volume_db=-3.0,  # Slightly boost VO
                            track_type=TrackType.VOICEOVER,
                            fade_in=0.1,
                            scene_id=audio.scene_id if hasattr(audio, 'scene_id') else f"scene_{i}"
                        ))

                # Extract music if available
                if hasattr(audio, 'music') and audio.music:
                    music = audio.music
                    if hasattr(music, 'audio_path') and music.audio_path:
                        audio_tracks.append(AudioTrack(
                            path=music.audio_path,
                            start_time=current_time,
                            volume_db=-12.0,  # Music lower than VO
                            track_type=TrackType.MUSIC,
                            duck_under=[TrackType.VOICEOVER],
                            fade_in=1.0,
                            fade_out=2.0
                        ))

                # Estimate scene duration for timing
                scene_duration = getattr(audio, 'duration', 5.0) if hasattr(audio, 'duration') else 5.0
                current_time += scene_duration

            self.log(f"Prepared {len(audio_tracks)} audio tracks for mixing")

            # Render the EDL
            render_result = await renderer.render(
                edl=edl,
                audio_tracks=audio_tracks,
                run_id=self.run_id
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["renderer"] = {
                "duration_seconds": elapsed,
                "success": render_result.success,
                "output_path": render_result.output_path,
                "file_size": render_result.file_size,
                "render_time": render_result.render_time
            }

            if render_result.success:
                self.log(f"Rendered final video: {render_result.output_path}", "SUCCESS")
                if render_result.file_size:
                    size_mb = render_result.file_size / (1024 * 1024)
                    self.log(f"File size: {size_mb:.1f} MB")
            else:
                self.log(f"Render note: {render_result.error_message}", "INFO")

            self.log(f"Duration: {elapsed:.1f}s")
            print()

            return render_result

        except Exception as e:
            self.metadata["errors"].append({"stage": "renderer", "error": str(e)})
            self.log(f"Renderer error: {str(e)}", "ERROR")
            return RenderResult(
                success=False,
                error_message=str(e)
            )

    def _print_summary(self, edl: EditDecisionList, render_result: RenderResult = None):
        """Print final summary"""
        print("\n" + "="*70)
        if sys.platform == "win32":
            print("PRODUCTION COMPLETE")
        else:
            print("🎉 PRODUCTION COMPLETE")
        print("="*70)
        print(f"\nRun ID: {self.run_id}")
        print(f"Run Directory: {self.run_dir}")
        print(f"\nConcept: {self.concept}")
        print(f"Budget: ${self.budget:.2f}")

        # Show actual providers used
        video_provider = self.metadata.get("actual_video_provider", "unknown")
        audio_provider = self.metadata.get("actual_audio_provider", "unknown")
        print(f"\nProviders Used:")
        print(f"  - Video: {video_provider.upper()}" + (" (simulated costs)" if video_provider == "mock" else " (real API)"))
        print(f"  - Audio: {audio_provider.upper()}" + (" (simulated)" if audio_provider == "mock" else " (real API)"))

        print(f"\nCosts:")
        if video_provider == "mock":
            print(f"  - Video: ${self.metadata['costs']['video']:.2f} (SIMULATED - no actual charges)")
        else:
            print(f"  - Video: ${self.metadata['costs']['video']:.2f}")
        if audio_provider == "mock":
            print(f"  - Audio: ${self.metadata['costs']['audio']:.2f} (SIMULATED - no actual charges)")
        else:
            print(f"  - Audio: ${self.metadata['costs']['audio']:.2f}")
        print(f"  - Total: ${self.metadata['costs']['total']:.2f}")

        print(f"\nScenes Generated: {self.metadata['stages']['script_writer']['num_scenes']}")
        print(f"Videos Generated: {self.metadata['stages']['video_generator']['num_videos']}")
        print(f"Audio Tracks: {self.metadata['stages']['audio_generator']['num_scenes']}")

        print(f"\nQA Results:")
        qa_stage = self.metadata['stages']['qa_verifier']
        print(f"  - Verified: {qa_stage['total_videos']} videos")
        print(f"  - Passed: {qa_stage['passed_videos']} ({qa_stage['pass_rate']*100:.1f}%)")

        print(f"\nEdit Candidates: {len(edl.candidates)}")
        for candidate in edl.candidates:
            if sys.platform == "win32":
                marker = "*" if candidate.candidate_id == edl.recommended_candidate_id else " "
            else:
                marker = "⭐" if candidate.candidate_id == edl.recommended_candidate_id else "  "
            print(f"{marker} {candidate.name} ({candidate.style})")
            print(f"     Quality: {candidate.estimated_quality:.1f}/100")
            print(f"     Duration: {candidate.total_duration:.1f}s")

        print(f"\nRecommended Edit: {edl.recommended_candidate_id}")

        # Render results
        if render_result:
            print(f"\nFinal Render:")
            if render_result.success and render_result.output_path:
                print(f"  - Output: {render_result.output_path}")
                if render_result.file_size:
                    size_mb = render_result.file_size / (1024 * 1024)
                    print(f"  - Size: {size_mb:.1f} MB")
                if render_result.duration:
                    print(f"  - Duration: {render_result.duration:.1f}s")
            else:
                print(f"  - Status: {render_result.error_message or 'Not rendered'}")

        total_duration = (datetime.fromisoformat(self.metadata['end_time']) -
                         datetime.fromisoformat(self.metadata['start_time'])).total_seconds()
        print(f"\nTotal Pipeline Duration: {total_duration:.1f}s")
        print(f"\nArtifacts saved to: {self.run_dir}")
        print("="*70 + "\n")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run end-to-end video production pipeline")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock providers (default)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live API providers (Runway + OpenAI TTS)"
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=20.0,
        help="Total budget in USD (default: 20.0)"
    )
    parser.add_argument(
        "--concept",
        type=str,
        default="A 30-second video about a developer building an AI app",
        help="Video concept description"
    )
    parser.add_argument(
        "--audio-tier",
        type=str,
        choices=["none", "music_only", "simple_overlay", "time_synced", "full_production"],
        default="simple_overlay",
        help="Audio production tier (default: simple_overlay)"
    )
    parser.add_argument(
        "--seed-asset",
        type=str,
        action="append",
        dest="seed_assets",
        help="Path to seed asset (image, etc.). Can be specified multiple times."
    )

    args = parser.parse_args()

    # Determine mode
    use_live = args.live
    if not args.mock and not args.live:
        use_live = False  # Default to mock

    # Parse audio tier
    audio_tier_map = {
        "none": AudioTier.NONE,
        "music_only": AudioTier.MUSIC_ONLY,
        "simple_overlay": AudioTier.SIMPLE_OVERLAY,
        "time_synced": AudioTier.TIME_SYNCED,
        "full_production": AudioTier.FULL_PRODUCTION
    }
    audio_tier = audio_tier_map[args.audio_tier]

    # Build seed asset collection from CLI arguments
    seed_collection = SeedAssetCollection()
    if args.seed_assets:
        for i, asset_path in enumerate(args.seed_assets):
            path = Path(asset_path)
            if not path.exists():
                print(f"Warning: Seed asset not found: {asset_path}")
                continue

            # Detect asset type from extension
            ext = path.suffix.lower()
            if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                asset_type = SeedAssetType.IMAGE
            elif ext in (".mp4", ".mov", ".webm"):
                asset_type = SeedAssetType.REFERENCE_VIDEO
            elif ext in (".mp3", ".wav", ".ogg"):
                asset_type = SeedAssetType.MUSIC_REFERENCE
            else:
                asset_type = SeedAssetType.IMAGE  # Default to image

            seed_collection.add_asset(SeedAsset(
                asset_id=f"seed_{i}",
                asset_type=asset_type,
                role=AssetRole.CONTENT_SOURCE,
                file_path=str(path.absolute()),
                description=f"Seed asset: {path.name}",
                usage_instructions="Use as input for video generation"
            ))
            print(f"Loaded seed asset: {path.name} ({asset_type.value})")

    # Create and run pipeline
    pipeline = ProductionPipeline(
        concept=args.concept,
        budget=args.budget,
        audio_tier=audio_tier,
        use_live_providers=use_live,
        seed_assets=seed_collection
    )

    try:
        result = await pipeline.run()
        sys.exit(0)
    except Exception as e:
        if sys.platform == "win32":
            print(f"\n[ERROR] Pipeline failed: {str(e)}")
        else:
            print(f"\n❌ Pipeline failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
