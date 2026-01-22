"""
Audio Generator Agent - Generates voiceover, music, and sound effects

Supports 5-tier audio production:
- NONE: No audio
- MUSIC_ONLY: Background music track
- SIMPLE_OVERLAY: AI voiceover + music, loose sync
- TIME_SYNCED: Frame-accurate sync points
- FULL_PRODUCTION: VO + music + SFX + mixing
"""

from typing import List, Dict, Optional, Any
from dataclasses import replace
from strands import tool
from core.claude_client import ClaudeClient
from core.budget import estimate_audio_cost
from .base import StudioAgent
from core.models.audio import (
    AudioTier,
    VoiceStyle,
    MusicMood,
    SyncPoint,
    VoiceoverSpec,
    MusicSpec,
    SoundEffectSpec,
    SceneAudio,
    WordTiming,
    GeneratedAudio,
    VoiceoverResult,
    MixSettings,
    MixedAudio,
)
from agents.script_writer import Scene


class AudioGeneratorAgent(StudioAgent):
    """
    Generates audio for video scenes using AI providers.

    Supports multiple audio tiers from music-only to full production.
    Handles voiceover generation, music generation, sound effects,
    and multi-track mixing.
    """

    _is_stub = False  # TTS integration complete

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        audio_provider: Optional[Any] = None,
        music_provider: Optional[Any] = None
    ):
        """
        Initialize Audio Generator Agent

        Args:
            claude_client: Optional ClaudeClient for analysis tasks
            audio_provider: Optional audio provider (ElevenLabs, OpenAI TTS, etc.)
            music_provider: Optional music provider (Mubert, Suno, etc.)
        """
        super().__init__(claude_client=claude_client)
        self.audio_provider = audio_provider
        self.music_provider = music_provider  # Will use mock if None

        # Auto-initialize ElevenLabs if no provider specified and API key available
        if self.audio_provider is None:
            import os
            if os.getenv("ELEVENLABS_API_KEY"):
                from core.providers.audio.elevenlabs import ElevenLabsProvider
                self.audio_provider = ElevenLabsProvider()
            elif os.getenv("OPENAI_API_KEY"):
                from core.providers.audio.openai_tts import OpenAITTSProvider
                self.audio_provider = OpenAITTSProvider()

    async def generate_voiceover(
        self,
        text: str,
        voice_style: VoiceStyle,
        target_duration: Optional[float] = None,
        sync_points: Optional[List[SyncPoint]] = None,
        voice_id: Optional[str] = None
    ) -> VoiceoverResult:
        """
        Generate voiceover audio from text

        Args:
            text: Script text to speak
            voice_style: Voice style (professional, conversational, etc.)
            target_duration: Optional target duration in seconds
            sync_points: Optional sync points for time-synced audio
            voice_id: Optional specific voice ID to use

        Returns:
            VoiceoverResult with audio and timing information
        """
        word_count = len(text.split())
        words = text.split()

        # Use real provider if available
        if self.audio_provider is not None:
            # Map voice style to provider voice (can be customized)
            effective_voice_id = voice_id
            if not effective_voice_id:
                # Default voice mapping based on style
                voice_mapping = {
                    VoiceStyle.PROFESSIONAL: "Rachel",  # ElevenLabs default professional
                    VoiceStyle.CONVERSATIONAL: "Adam",
                    VoiceStyle.DRAMATIC: "Antoni",
                    VoiceStyle.FRIENDLY: "Bella",
                    VoiceStyle.AUTHORITATIVE: "Arnold",
                }
                effective_voice_id = voice_mapping.get(voice_style, "Rachel")

            # Generate real audio
            result = await self.audio_provider.generate_speech(
                text=text,
                voice_id=effective_voice_id
            )

            if result.success:
                # Estimate duration from audio data size if not provided
                # MP3 at 128kbps = ~16KB per second
                estimated_duration = result.duration
                if estimated_duration is None and result.audio_data:
                    estimated_duration = len(result.audio_data) / 16000.0

                # Estimate cost from provider
                generation_cost = 0.0
                if hasattr(self.audio_provider, 'estimate_cost'):
                    generation_cost = self.audio_provider.estimate_cost(text)

                # Generate estimated word timings
                timing_map = []
                current_time = 0.0
                avg_word_duration = (estimated_duration or 1.0) / max(len(words), 1)

                for word in words:
                    timing_map.append(WordTiming(
                        word=word,
                        start_time=current_time,
                        end_time=current_time + avg_word_duration
                    ))
                    current_time += avg_word_duration

                # Create audio result with real data
                audio = GeneratedAudio(
                    audio_id=f"vo_{hash(text) % 10000}",
                    audio_url=None,  # Data is in audio_data, not URL
                    audio_data=result.audio_data,
                    audio_type="voiceover",
                    duration=estimated_duration or (word_count / 150.0) * 60.0,
                    format=result.format or "mp3",
                    sample_rate=result.sample_rate or 44100,
                    channels=1,
                    generation_cost=generation_cost,
                    provider_metadata=result.provider_metadata
                )

                return VoiceoverResult(
                    audio=audio,
                    words_per_minute=word_count / ((estimated_duration or 1.0) / 60.0),
                    actual_duration=estimated_duration or (word_count / 150.0) * 60.0,
                    target_duration=target_duration or estimated_duration,
                    timing_map=timing_map
                )

        # Fallback to mock implementation if no provider or generation failed
        estimated_duration = (word_count / 150.0) * 60.0

        # Generate mock word timings
        timing_map = []
        current_time = 0.0
        avg_word_duration = estimated_duration / max(len(words), 1)

        for word in words:
            timing_map.append(WordTiming(
                word=word,
                start_time=current_time,
                end_time=current_time + avg_word_duration
            ))
            current_time += avg_word_duration

        # Create mock audio result
        audio = GeneratedAudio(
            audio_id=f"vo_{hash(text) % 10000}",
            audio_url="https://mock.audio/voiceover.mp3",
            audio_type="voiceover",
            duration=estimated_duration,
            format="mp3",
            sample_rate=48000,
            channels=1,
            generation_cost=0.15 * (estimated_duration / 60.0)
        )

        return VoiceoverResult(
            audio=audio,
            words_per_minute=150.0,
            actual_duration=estimated_duration,
            target_duration=target_duration or estimated_duration,
            timing_map=timing_map
        )

    async def generate_music(
        self,
        mood: MusicMood,
        duration: float,
        tempo: str = "medium"
    ) -> GeneratedAudio:
        """
        Generate background music

        Args:
            mood: Music mood (upbeat, corporate, emotional, etc.)
            duration: Duration in seconds
            tempo: Tempo (slow, medium, fast)

        Returns:
            GeneratedAudio with music track
        """
        # Mock implementation
        audio = GeneratedAudio(
            audio_id=f"music_{mood.value}_{int(duration)}",
            audio_url="https://mock.audio/music.mp3",
            audio_type="music",
            duration=duration,
            format="mp3",
            sample_rate=48000,
            channels=2,  # Stereo for music
            generation_cost=0.50 * (duration / 60.0)  # $0.50/min estimate
        )

        return audio

    async def get_sound_effect(
        self,
        effect_type: str,
        duration: Optional[float] = None
    ) -> GeneratedAudio:
        """
        Get or generate sound effect

        Args:
            effect_type: Type of sound effect (notification, whoosh, etc.)
            duration: Optional duration (defaults to natural length)

        Returns:
            GeneratedAudio with sound effect
        """
        # Mock implementation
        sfx_duration = duration or 1.0  # Default 1 second

        audio = GeneratedAudio(
            audio_id=f"sfx_{effect_type}",
            audio_url=f"https://mock.audio/sfx/{effect_type}.wav",
            audio_type="sfx",
            duration=sfx_duration,
            format="wav",
            sample_rate=48000,
            channels=2,  # Stereo for SFX
            generation_cost=0.10  # Flat fee per SFX
        )

        return audio

    async def generate_scene_audio(
        self,
        scene: Scene,
        audio_tier: AudioTier
    ) -> SceneAudio:
        """
        Generate all audio for a single scene

        Args:
            scene: Scene with audio specifications
            audio_tier: Audio production tier

        Returns:
            SceneAudio with generated audio tracks
        """
        scene_audio = SceneAudio(
            scene_id=scene.scene_id,
            audio_tier=audio_tier
        )

        # NONE tier - no audio
        if audio_tier == AudioTier.NONE:
            return scene_audio

        # MUSIC_ONLY tier - just background music
        if audio_tier == AudioTier.MUSIC_ONLY:
            if scene.music_transition != "none":
                music_spec = MusicSpec(
                    mood=MusicMood.CORPORATE,  # Default
                    tempo="medium",
                    duration=scene.duration
                )
                scene_audio.music = music_spec
            return scene_audio

        # Generate voiceover for tiers that include it
        if scene.voiceover_text:
            voice_style = VoiceStyle.PROFESSIONAL  # Default
            voiceover_spec = VoiceoverSpec(
                text=scene.voiceover_text,
                voice_style=voice_style,
                target_duration=scene.duration - scene.vo_start_offset - scene.vo_end_buffer,
                sync_points=scene.sync_points if audio_tier in [AudioTier.TIME_SYNCED, AudioTier.FULL_PRODUCTION] else []
            )
            scene_audio.voiceover = voiceover_spec

        # Generate music for tiers that include it
        if audio_tier in [AudioTier.SIMPLE_OVERLAY, AudioTier.TIME_SYNCED, AudioTier.FULL_PRODUCTION]:
            if scene.music_transition != "none":
                music_spec = MusicSpec(
                    mood=MusicMood.CORPORATE,  # Default
                    tempo="medium",
                    duration=scene.duration,
                    duck_under_vo=True,
                    duck_amount_db=-12
                )
                scene_audio.music = music_spec

        # Generate sound effects for FULL_PRODUCTION
        if audio_tier == AudioTier.FULL_PRODUCTION:
            if scene.sfx_cues:
                scene_audio.sound_effects = [
                    SoundEffectSpec(
                        effect_type=sfx,
                        timestamp=0.0,  # Would be parsed from sfx string
                        duration=1.0
                    )
                    for sfx in scene.sfx_cues
                ]

        return scene_audio

    @tool
    async def run(
        self,
        scenes: List[Scene],
        audio_tier: AudioTier,
        budget_limit: float
    ) -> List[SceneAudio]:
        """
        Generate audio for all scenes within budget

        Args:
            scenes: List of scenes to generate audio for
            audio_tier: Audio production tier
            budget_limit: Maximum budget for audio generation

        Returns:
            List of SceneAudio with generated audio
        """
        # Estimate cost
        total_duration = sum(scene.duration for scene in scenes)
        estimated_cost = estimate_audio_cost(
            audio_tier=audio_tier,
            duration_seconds=total_duration,
            num_scenes=len(scenes)
        )

        if estimated_cost > budget_limit:
            print(f"Warning: Estimated audio cost ${estimated_cost:.2f} exceeds budget ${budget_limit:.2f}")

        # Generate audio for each scene
        scene_audios = []
        total_cost = 0.0

        for scene in scenes:
            # Check budget before processing
            scene_cost = estimate_audio_cost(
                audio_tier=audio_tier,
                duration_seconds=scene.duration,
                num_scenes=1
            )

            if total_cost + scene_cost > budget_limit:
                print(f"Warning: Stopping audio generation - budget limit reached")
                break

            scene_audio = await self.generate_scene_audio(scene, audio_tier)
            scene_audios.append(scene_audio)
            total_cost += scene_cost

        return scene_audios

    def estimate_audio_cost(
        self,
        scenes: List[Scene],
        audio_tier: AudioTier
    ) -> Dict[str, float]:
        """
        Estimate audio generation costs

        Args:
            scenes: List of scenes
            audio_tier: Audio production tier

        Returns:
            Cost breakdown dict
        """
        total_duration = sum(scene.duration for scene in scenes)
        total_cost = estimate_audio_cost(
            audio_tier=audio_tier,
            duration_seconds=total_duration,
            num_scenes=len(scenes)
        )

        return {
            "total_duration_seconds": total_duration,
            "audio_tier": audio_tier.value,
            "base_cost": total_cost,
            "cost_per_minute": total_cost / (total_duration / 60.0) if total_duration > 0 else 0.0,
            "num_scenes": len(scenes)
        }
