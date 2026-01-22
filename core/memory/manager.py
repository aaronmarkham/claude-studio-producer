"""Memory manager for short-term and long-term memory"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from enum import Enum
import asyncio

from core.models.memory import (
    ShortTermMemory, LongTermMemory, UserPreferences,
    ProductionRecord, LearnedPattern, RunStage, StageEvent,
    PilotMemory, AssetMemory, ProviderLearning, ProviderKnowledge
)


class MemoryManager:
    """
    Manages short-term and long-term memory for Claude Studio Producer.

    Short-term: In-memory during run, saved to artifacts/runs/{run_id}/memory.json
    Long-term: Persisted to artifacts/memory/long_term.json
    """

    def __init__(self, base_path: str = "artifacts"):
        self.base_path = Path(base_path)
        self.memory_path = self.base_path / "memory"
        self.memory_path.mkdir(parents=True, exist_ok=True)

        self._long_term: Optional[LongTermMemory] = None
        self._short_term: dict[str, ShortTermMemory] = {}  # run_id -> memory
        self._lock = asyncio.Lock()

    # ==================== SHORT-TERM MEMORY ====================

    async def create_run(
        self, run_id: str, concept: str, budget: float, audio_tier: str = "SIMPLE_OVERLAY"
    ) -> ShortTermMemory:
        """Create short-term memory for a new run"""
        memory = ShortTermMemory(
            run_id=run_id,
            concept=concept,
            budget_total=budget,
            audio_tier=audio_tier,
            started_at=datetime.utcnow()
        )
        self._short_term[run_id] = memory
        await self._save_short_term(run_id)
        return memory

    async def get_run(self, run_id: str) -> Optional[ShortTermMemory]:
        """Get short-term memory for a run"""
        if run_id in self._short_term:
            return self._short_term[run_id]

        # Try to load from disk
        return await self._load_short_term(run_id)

    async def list_runs(self, limit: int = 20) -> List[str]:
        """List all run IDs from disk"""
        runs_path = self.base_path / "runs"
        if not runs_path.exists():
            return []

        run_dirs = []
        for run_dir in sorted(runs_path.iterdir(), reverse=True):
            if run_dir.is_dir() and (run_dir / "memory.json").exists():
                run_dirs.append(run_dir.name)
                if len(run_dirs) >= limit:
                    break
        return run_dirs

    async def delete_run(self, run_id: str) -> bool:
        """Delete a run and all its artifacts"""
        import shutil

        run_path = self.base_path / "runs" / run_id
        if not run_path.exists():
            return False

        # Remove from in-memory cache
        if run_id in self._short_term:
            del self._short_term[run_id]

        # Delete the directory and all contents
        shutil.rmtree(run_path)
        return True

    async def update_stage(self, run_id: str, stage: RunStage, details: dict = None):
        """Update current stage of a run"""
        memory = await self.get_run(run_id)
        if not memory:
            return

        # Calculate duration of previous stage
        if memory.timeline:
            prev_event = memory.timeline[-1]
            if prev_event.timestamp:
                duration = (datetime.utcnow() - prev_event.timestamp).total_seconds() * 1000
                prev_event.duration_ms = int(duration)

        # Record timeline event
        event = StageEvent(
            stage=stage,
            timestamp=datetime.utcnow(),
            details=details or {}
        )
        memory.timeline.append(event)
        memory.current_stage = stage

        # Update progress estimate
        stage_progress = {
            RunStage.INITIALIZED: 0,
            RunStage.ANALYZING_ASSETS: 10,
            RunStage.PLANNING_PILOTS: 20,
            RunStage.GENERATING_SCRIPTS: 30,
            RunStage.GENERATING_VIDEO: 50,
            RunStage.GENERATING_AUDIO: 70,
            RunStage.EVALUATING: 80,
            RunStage.EDITING: 90,
            RunStage.RENDERING: 95,
            RunStage.COMPLETED: 100,
            RunStage.FAILED: 100,
        }
        memory.progress_percent = stage_progress.get(stage, 0)

        await self._save_short_term(run_id)

    async def add_pilot(self, run_id: str, pilot: PilotMemory):
        """Add a pilot to the run"""
        memory = await self.get_run(run_id)
        if memory:
            memory.pilots.append(pilot)
            await self._save_short_term(run_id)

    async def update_pilot(self, run_id: str, pilot_id: str, **updates):
        """Update a pilot's status"""
        memory = await self.get_run(run_id)
        if memory:
            for pilot in memory.pilots:
                if pilot.pilot_id == pilot_id:
                    for key, value in updates.items():
                        if hasattr(pilot, key):
                            setattr(pilot, key, value)
                    break
            await self._save_short_term(run_id)

    async def set_winning_pilot(self, run_id: str, pilot_id: str):
        """Set the winning pilot for a run"""
        memory = await self.get_run(run_id)
        if memory:
            memory.winning_pilot_id = pilot_id
            await self._save_short_term(run_id)

    async def add_asset(self, run_id: str, asset: AssetMemory):
        """Add a generated asset to the run"""
        memory = await self.get_run(run_id)
        if memory:
            memory.assets.append(asset)
            memory.budget_spent += asset.cost
            if asset.asset_type == "video" and asset.scene_id:
                memory.scenes_completed += 1
            await self._save_short_term(run_id)

    async def update_scenes(self, run_id: str, total: int, completed: int = None):
        """Update scene counts"""
        memory = await self.get_run(run_id)
        if memory:
            memory.total_scenes = total
            if completed is not None:
                memory.scenes_completed = completed
            await self._save_short_term(run_id)

    async def add_error(self, run_id: str, error: str):
        """Record an error"""
        memory = await self.get_run(run_id)
        if memory:
            memory.errors.append(error)
            await self._save_short_term(run_id)

    async def add_warning(self, run_id: str, warning: str):
        """Record a warning"""
        memory = await self.get_run(run_id)
        if memory:
            memory.warnings.append(warning)
            await self._save_short_term(run_id)

    async def complete_run(self, run_id: str, status: str = "completed"):
        """Mark a run as complete and transfer learnings to long-term memory"""
        memory = await self.get_run(run_id)
        if not memory:
            return

        memory.current_stage = RunStage.COMPLETED if status == "completed" else RunStage.FAILED
        memory.completed_at = datetime.utcnow()
        memory.progress_percent = 100

        # Calculate duration of last stage
        if memory.timeline:
            prev_event = memory.timeline[-1]
            if prev_event.timestamp:
                duration = (datetime.utcnow() - prev_event.timestamp).total_seconds() * 1000
                prev_event.duration_ms = int(duration)

        await self._save_short_term(run_id)

        # Transfer to long-term memory
        if status == "completed":
            await self._transfer_to_long_term(memory)

    async def _save_short_term(self, run_id: str):
        """Save short-term memory to disk"""
        memory = self._short_term.get(run_id)
        if not memory:
            return

        run_path = self.base_path / "runs" / run_id
        run_path.mkdir(parents=True, exist_ok=True)

        memory_file = run_path / "memory.json"
        with open(memory_file, "w") as f:
            json.dump(self._serialize(memory), f, indent=2, default=str)

    async def _load_short_term(self, run_id: str) -> Optional[ShortTermMemory]:
        """Load short-term memory from disk"""
        memory_file = self.base_path / "runs" / run_id / "memory.json"
        if not memory_file.exists():
            return None

        with open(memory_file) as f:
            data = json.load(f)

        # Deserialize back to dataclass
        memory = self._deserialize_short_term(data)
        self._short_term[run_id] = memory
        return memory

    # ==================== LONG-TERM MEMORY ====================

    async def get_long_term(self) -> LongTermMemory:
        """Get long-term memory"""
        if self._long_term is None:
            await self._load_long_term()
        return self._long_term

    async def get_preferences(self) -> UserPreferences:
        """Get user preferences"""
        long_term = await self.get_long_term()
        return long_term.preferences

    async def update_preferences(self, **updates):
        """Update user preferences"""
        long_term = await self.get_long_term()
        for key, value in updates.items():
            if hasattr(long_term.preferences, key):
                setattr(long_term.preferences, key, value)
        await self._save_long_term()

    async def get_pattern(self, concept: str) -> Optional[LearnedPattern]:
        """Find a learned pattern matching the concept"""
        long_term = await self.get_long_term()

        concept_lower = concept.lower()
        for pattern_name, pattern in long_term.patterns.items():
            for keyword in pattern.keywords:
                if keyword in concept_lower:
                    return pattern
        return None

    async def get_production_history(self, limit: int = 10) -> List[ProductionRecord]:
        """Get recent production history"""
        long_term = await self.get_long_term()
        return long_term.production_history[-limit:]

    # ==================== PROVIDER LEARNING ====================

    async def record_provider_learning(self, learning: ProviderLearning):
        """Record a provider learning and update accumulated knowledge"""
        long_term = await self.get_long_term()

        # Get or create provider knowledge
        if learning.provider not in long_term.provider_knowledge:
            long_term.provider_knowledge[learning.provider] = ProviderKnowledge(
                provider=learning.provider
            )

        knowledge = long_term.provider_knowledge[learning.provider]

        # Update stats
        knowledge.total_runs += 1
        if knowledge.total_runs == 1:
            knowledge.avg_adherence = learning.adherence_score
            knowledge.avg_quality = learning.quality_score
        else:
            knowledge.avg_adherence = (
                (knowledge.avg_adherence * (knowledge.total_runs - 1) + learning.adherence_score)
                / knowledge.total_runs
            )
            knowledge.avg_quality = (
                (knowledge.avg_quality * (knowledge.total_runs - 1) + learning.quality_score)
                / knowledge.total_runs
            )

        # Aggregate learnings (deduplicate)
        for strength in learning.strengths_observed:
            if strength and strength not in knowledge.known_strengths:
                knowledge.known_strengths.append(strength)

        for weakness in learning.weaknesses_observed:
            if weakness and weakness not in knowledge.known_weaknesses:
                knowledge.known_weaknesses.append(weakness)

        for tip in learning.prompt_tips:
            if tip and tip not in knowledge.prompt_guidelines:
                knowledge.prompt_guidelines.append(tip)

        for avoid in learning.avoid_list:
            if avoid and avoid not in knowledge.avoid_list:
                knowledge.avoid_list.append(avoid)

        for pattern in learning.effective_patterns:
            if pattern and pattern not in knowledge.best_prompt_patterns:
                knowledge.best_prompt_patterns.append(pattern)

        # Keep recent learnings (last 10)
        knowledge.recent_learnings.append(learning)
        knowledge.recent_learnings = knowledge.recent_learnings[-10:]

        await self._save_long_term()

    async def get_provider_guidelines(self, provider: str) -> Optional[ProviderKnowledge]:
        """Get accumulated knowledge about a provider"""
        long_term = await self.get_long_term()
        return long_term.provider_knowledge.get(provider)

    async def bootstrap_provider_knowledge(self, provider: str, knowledge: ProviderKnowledge):
        """Bootstrap initial provider knowledge (used for seeding known info)"""
        long_term = await self.get_long_term()

        if provider not in long_term.provider_knowledge:
            long_term.provider_knowledge[provider] = knowledge
            await self._save_long_term()

    async def record_onboarding_learnings(
        self,
        provider: str,
        tips: List[str] = None,
        gotchas: List[str] = None,
        model_limitations: List[str] = None,
    ):
        """
        Record learnings from provider onboarding.

        This is used during provider onboarding to store tips, gotchas,
        and limitations discovered from API documentation analysis.

        Args:
            provider: Provider name (e.g., "elevenlabs", "luma")
            tips: List of helpful tips for using the provider
            gotchas: List of things to avoid or watch out for
            model_limitations: List of model-specific limitations
        """
        long_term = await self.get_long_term()

        # Get or create provider knowledge
        if provider not in long_term.provider_knowledge:
            long_term.provider_knowledge[provider] = ProviderKnowledge(
                provider=provider
            )

        knowledge = long_term.provider_knowledge[provider]

        # Add tips to prompt guidelines (deduplicated)
        for tip in (tips or []):
            if tip and tip not in knowledge.prompt_guidelines:
                knowledge.prompt_guidelines.append(tip)

        # Add gotchas to avoid list (deduplicated)
        for gotcha in (gotchas or []):
            if gotcha and gotcha not in knowledge.avoid_list:
                knowledge.avoid_list.append(gotcha)

        # Add model limitations to weaknesses (deduplicated)
        for limitation in (model_limitations or []):
            if limitation and limitation not in knowledge.known_weaknesses:
                knowledge.known_weaknesses.append(limitation)

        await self._save_long_term()

    async def _transfer_to_long_term(self, short_term: ShortTermMemory):
        """Transfer learnings from completed run to long-term memory"""
        long_term = await self.get_long_term()

        # Find winning pilot
        winning_pilot = None
        for pilot in short_term.pilots:
            if pilot.pilot_id == short_term.winning_pilot_id:
                winning_pilot = pilot
                break

        # Calculate duration
        duration_seconds = 0
        if short_term.started_at and short_term.completed_at:
            duration_seconds = (short_term.completed_at - short_term.started_at).total_seconds()

        # Create production record
        record = ProductionRecord(
            run_id=short_term.run_id,
            concept=short_term.concept,
            timestamp=short_term.completed_at or datetime.utcnow(),
            status="completed",
            winning_tier=winning_pilot.tier if winning_pilot else None,
            final_score=winning_pilot.quality_score if winning_pilot else None,
            total_cost=short_term.budget_spent,
            duration_seconds=duration_seconds,
            scenes_count=short_term.scenes_completed,
        )

        long_term.production_history.append(record)
        long_term.total_runs += 1
        long_term.total_spent += short_term.budget_spent

        # Update patterns
        await self._update_patterns(short_term, record)

        await self._save_long_term()

    async def _update_patterns(self, short_term: ShortTermMemory, record: ProductionRecord):
        """Update learned patterns based on this run"""
        long_term = await self.get_long_term()

        # Extract keywords from concept
        keywords = self._extract_keywords(short_term.concept)

        if not keywords:
            return

        # Find or create pattern
        pattern_name = keywords[0]

        if pattern_name not in long_term.patterns:
            long_term.patterns[pattern_name] = LearnedPattern(
                pattern_name=pattern_name,
                recommended_tier=record.winning_tier or "ANIMATED",
                recommended_scenes=record.scenes_count,
                recommended_duration=60,
                recommended_edit_style="safe",
                keywords=keywords
            )

        pattern = long_term.patterns[pattern_name]
        pattern.times_used += 1

        # Update averages
        if record.final_score:
            pattern.avg_score = (
                (pattern.avg_score * (pattern.times_used - 1) + record.final_score)
                / pattern.times_used
            )
        pattern.avg_cost = (
            (pattern.avg_cost * (pattern.times_used - 1) + record.total_cost)
            / pattern.times_used
        )

    def _extract_keywords(self, concept: str) -> List[str]:
        """Extract keywords from concept for pattern matching"""
        keywords = []

        patterns = [
            "intro", "outro", "demo", "tutorial", "explainer",
            "ad", "commercial", "promo", "teaser", "trailer",
            "podcast", "vlog", "review", "unboxing", "interview",
            "logo", "reveal", "animation", "product", "brand"
        ]

        concept_lower = concept.lower()
        for pattern in patterns:
            if pattern in concept_lower:
                keywords.append(pattern)

        return keywords

    async def _load_long_term(self):
        """Load long-term memory from disk"""
        memory_file = self.memory_path / "long_term.json"

        if memory_file.exists():
            with open(memory_file) as f:
                data = json.load(f)
            self._long_term = self._deserialize_long_term(data)
        else:
            self._long_term = LongTermMemory()

    async def _save_long_term(self):
        """Save long-term memory to disk"""
        async with self._lock:
            if self._long_term:
                self._long_term.updated_at = datetime.utcnow()
            memory_file = self.memory_path / "long_term.json"
            with open(memory_file, "w") as f:
                json.dump(self._serialize(self._long_term), f, indent=2, default=str)

    # ==================== SERIALIZATION ====================

    def _serialize(self, obj) -> dict:
        """Serialize dataclass to dict"""
        if obj is None:
            return None
        if hasattr(obj, "__dataclass_fields__"):
            result = {}
            for field_name in obj.__dataclass_fields__:
                value = getattr(obj, field_name)
                result[field_name] = self._serialize(value)
            return result
        elif isinstance(obj, list):
            return [self._serialize(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        elif isinstance(obj, Enum):
            return obj.value
        elif isinstance(obj, datetime):
            return obj.isoformat()
        else:
            return obj

    def _deserialize_short_term(self, data: dict) -> ShortTermMemory:
        """Deserialize dict to ShortTermMemory"""
        # Handle nested objects
        if "timeline" in data:
            data["timeline"] = [
                StageEvent(
                    stage=RunStage(e["stage"]),
                    timestamp=datetime.fromisoformat(e["timestamp"]) if e.get("timestamp") else None,
                    duration_ms=e.get("duration_ms"),
                    details=e.get("details", {}),
                    error=e.get("error")
                )
                for e in data["timeline"]
            ]

        if "pilots" in data:
            data["pilots"] = [PilotMemory(**p) for p in data["pilots"]]

        if "assets" in data:
            data["assets"] = [AssetMemory(**a) for a in data["assets"]]

        if "current_stage" in data:
            data["current_stage"] = RunStage(data["current_stage"])

        for dt_field in ["started_at", "completed_at"]:
            if data.get(dt_field):
                data[dt_field] = datetime.fromisoformat(data[dt_field])

        return ShortTermMemory(**data)

    def _deserialize_long_term(self, data: dict) -> LongTermMemory:
        """Deserialize dict to LongTermMemory"""
        if "preferences" in data:
            data["preferences"] = UserPreferences(**data["preferences"])

        if "production_history" in data:
            data["production_history"] = [
                ProductionRecord(
                    **{**p, "timestamp": datetime.fromisoformat(p["timestamp"]) if p.get("timestamp") else None}
                )
                for p in data["production_history"]
            ]

        if "patterns" in data:
            data["patterns"] = {
                k: LearnedPattern(**v) for k, v in data["patterns"].items()
            }

        if "provider_knowledge" in data:
            data["provider_knowledge"] = {
                provider: self._deserialize_provider_knowledge(pk)
                for provider, pk in data["provider_knowledge"].items()
            }

        if "saved_assets" in data:
            data["saved_assets"] = [AssetMemory(**a) for a in data["saved_assets"]]

        if data.get("updated_at"):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return LongTermMemory(**data)

    def _deserialize_provider_knowledge(self, data: dict) -> ProviderKnowledge:
        """Deserialize dict to ProviderKnowledge"""
        # Deserialize recent_learnings
        if "recent_learnings" in data:
            data["recent_learnings"] = [
                ProviderLearning(
                    **{
                        **pl,
                        "timestamp": datetime.fromisoformat(pl["timestamp"]) if pl.get("timestamp") else datetime.utcnow()
                    }
                )
                for pl in data["recent_learnings"]
            ]

        return ProviderKnowledge(**data)
