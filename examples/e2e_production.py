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
from agents.critic import CriticAgent, PilotResults
from agents.qa_verifier import QAVerifierAgent, QAResult
from agents.editor import EditorAgent
from core.claude_client import ClaudeClient
from core.budget import ProductionTier
from core.models.audio import AudioTier
from core.models.edit_decision import EditDecisionList, ExportFormat
from core.providers import MockVideoProvider
from core.providers.audio.openai_tts import OpenAITTSProvider
from core.providers.base import AudioProviderConfig


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
        run_id: Optional[str] = None
    ):
        """
        Args:
            concept: Video concept description
            budget: Total budget in USD
            audio_tier: Audio production tier
            use_live_providers: If True, use real API providers; if False, use mocks
            run_id: Optional run ID (auto-generated if not provided)
        """
        self.concept = concept
        self.budget = budget
        self.audio_tier = audio_tier
        self.use_live_providers = use_live_providers
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create output directories
        self.run_dir = Path("artifacts/runs") / self.run_id
        self.scenes_dir = self.run_dir / "scenes"
        self.videos_dir = self.run_dir / "videos"
        self.audio_dir = self.run_dir / "audio"
        self.edl_dir = self.run_dir / "edl"

        for dir_path in [self.scenes_dir, self.videos_dir, self.audio_dir, self.edl_dir]:
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
                "STAGE": "[STAGE]  "
            }.get(level, "         ")
        else:
            prefix = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✅",
                "ERROR": "❌",
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
            qa_results = await self._run_qa_verifier(scenes, video_candidates)

            # Stage 6: Critic - Evaluate results
            evaluation = await self._run_critic(pilot_strategy, scenes, video_candidates, qa_results)

            # Stage 7: Editor - Create EDL
            edl = await self._run_editor(scenes, video_candidates, qa_results)

            # Finalize
            self.metadata["end_time"] = datetime.now().isoformat()
            self.metadata["status"] = "completed"
            self.save_metadata()

            self._print_summary(edl)

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
                    "budget_allocated": pilot.budget_allocated,
                    "test_scenes": pilot.test_scenes
                }
            }

            self.log(f"Selected pilot: {pilot.tier.value}", "SUCCESS")
            self.log(f"Budget allocated: ${pilot.budget_allocated:.2f}")
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
                user_request=self.concept,
                tier=pilot.tier,
                target_duration=30.0,  # 30 second video
                audio_tier=self.audio_tier
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
            if self.use_live_providers:
                # TODO: Initialize real Runway provider when available
                self.log("Live Runway provider not yet configured, using mock", "INFO")
                video_provider = MockVideoProvider()
            else:
                video_provider = MockVideoProvider()

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
                    budget_limit=pilot.budget_allocated / len(scenes),
                    num_variations=2
                )

                video_candidates[scene.scene_id] = videos

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
            if self.use_live_providers:
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    self.log("OPENAI_API_KEY not set, using mock audio", "INFO")
                    audio_provider = None  # Use mock
                else:
                    config = AudioProviderConfig(api_key=api_key, timeout=60)
                    audio_provider = OpenAITTSProvider(config=config, model="tts-1")
            else:
                audio_provider = None  # Use mock

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

            # Calculate cost
            total_cost = 0.0
            for audio in scene_audio:
                if audio.voiceover and audio.voiceover.audio:
                    total_cost += audio.voiceover.audio.generation_cost
                if audio.music and audio.music.audio:
                    total_cost += audio.music.audio.generation_cost
                for sfx in audio.sound_effects:
                    if sfx.audio:
                        total_cost += sfx.audio.generation_cost

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
        video_candidates: Dict[str, List[GeneratedVideo]]
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
                        generated_video=video
                    )
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

            # Flatten video candidates for evaluation
            all_videos = []
            for videos in video_candidates.values():
                all_videos.extend(videos)

            # Evaluate pilot
            evaluation = await critic.evaluate_pilot(
                original_request=self.concept,
                pilot=pilot,
                scene_results=all_videos,
                budget_spent=self.metadata["costs"]["total"],
                budget_allocated=pilot.budget_allocated
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            self.metadata["stages"]["critic"] = {
                "duration_seconds": elapsed,
                "decision": evaluation.decision.value,
                "quality_score": evaluation.quality_score,
                "should_continue": evaluation.should_continue
            }

            self.log(f"Evaluation: {evaluation.decision.value}", "SUCCESS")
            self.log(f"Quality score: {evaluation.quality_score:.1f}/100")
            self.log(f"Should continue: {evaluation.should_continue}")
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

    def _print_summary(self, edl: EditDecisionList):
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
        print(f"Total Cost: ${self.metadata['costs']['total']:.2f}")
        print(f"  - Video: ${self.metadata['costs']['video']:.2f}")
        print(f"  - Audio: ${self.metadata['costs']['audio']:.2f}")

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

    # Create and run pipeline
    pipeline = ProductionPipeline(
        concept=args.concept,
        budget=args.budget,
        audio_tier=audio_tier,
        use_live_providers=use_live
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
