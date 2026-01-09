# Memory System and Dashboard Specification

## Overview

This document specifies the Strands memory integration and web dashboard for Claude Studio Producer. The system tracks state within runs (short-term), learns across runs (long-term), and provides a visual interface for monitoring, previewing, and managing productions.

## Memory Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       MEMORY SYSTEM                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SHORT-TERM MEMORY (per run)                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ run_id: "abc123"                                        │   │
│  │ stage: "video_generation"                               │   │
│  │ pilots: [{id, tier, score, status}]                     │   │
│  │ scenes_completed: 3/5                                   │   │
│  │ budget_spent: $2.61                                     │   │
│  │ assets: {videos: [...], audio: [...]}                   │   │
│  │ errors: []                                              │   │
│  │ timeline: [{stage, timestamp, duration}]                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         │                                        │
│                         ▼ (on completion, extract learnings)     │
│                                                                  │
│  LONG-TERM MEMORY (persists forever)                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ user_preferences:                                       │   │
│  │   ├── preferred_style: "cinematic"                      │   │
│  │   ├── default_voice: "nova"                             │   │
│  │   ├── default_music_mood: "ambient"                     │   │
│  │   ├── brand_colors: ["#4A90A4", "#333"]                │   │
│  │   └── quality_threshold: 75                             │   │
│  │                                                         │   │
│  │ production_history:                                     │   │
│  │   ├── total_runs: 47                                    │   │
│  │   ├── total_spent: $142.50                              │   │
│  │   └── runs: [{run_id, concept, result, score, cost}]   │   │
│  │                                                         │   │
│  │ learned_patterns:                                       │   │
│  │   ├── "podcast_intro" → {tier: ANIMATED, scenes: 2}    │   │
│  │   ├── "product_demo" → {tier: MOTION, scenes: 5}       │   │
│  │   └── "tutorial" → {tier: STATIC, scenes: 8}           │   │
│  │                                                         │   │
│  │ asset_library:                                          │   │
│  │   ├── logos: [{id, path, description}]                 │   │
│  │   ├── brand_assets: [...]                              │   │
│  │   └── favorite_clips: [...]                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Models

### core/models/memory.py

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class RunStage(Enum):
    """Stages of a production run"""
    INITIALIZED = "initialized"
    ANALYZING_ASSETS = "analyzing_assets"
    PLANNING_PILOTS = "planning_pilots"
    GENERATING_SCRIPTS = "generating_scripts"
    GENERATING_VIDEO = "generating_video"
    GENERATING_AUDIO = "generating_audio"
    EVALUATING = "evaluating"
    EDITING = "editing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StageEvent:
    """Event in the run timeline"""
    stage: RunStage
    timestamp: datetime
    duration_ms: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PilotMemory:
    """Memory of a pilot's performance"""
    pilot_id: str
    tier: str
    allocated_budget: float
    spent_budget: float
    scenes_generated: int
    quality_score: Optional[float] = None
    status: str = "running"  # running, approved, rejected
    rejection_reason: Optional[str] = None


@dataclass
class AssetMemory:
    """Memory of generated assets"""
    asset_id: str
    asset_type: str  # video, audio, image
    path: str
    scene_id: Optional[str] = None
    duration: Optional[float] = None
    cost: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class ShortTermMemory:
    """State within a single production run"""
    run_id: str
    concept: str
    budget_total: float
    budget_spent: float = 0
    audio_tier: str = "SIMPLE_OVERLAY"
    
    # Current state
    current_stage: RunStage = RunStage.INITIALIZED
    progress_percent: float = 0
    
    # Pilot tracking
    pilots: List[PilotMemory] = field(default_factory=list)
    winning_pilot_id: Optional[str] = None
    
    # Scene tracking
    total_scenes: int = 0
    scenes_completed: int = 0
    
    # Asset tracking
    assets: List[AssetMemory] = field(default_factory=list)
    
    # Timeline
    timeline: List[StageEvent] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Seed assets used
    seed_asset_ids: List[str] = field(default_factory=list)
    extracted_themes: List[str] = field(default_factory=list)
    extracted_colors: List[str] = field(default_factory=list)


@dataclass
class UserPreferences:
    """User preferences learned over time"""
    preferred_style: str = "balanced"  # safe, dynamic, cinematic
    preferred_tier: Optional[str] = None
    default_voice: str = "nova"
    default_voice_speed: float = 1.0
    default_music_mood: str = "ambient"
    default_audio_tier: str = "SIMPLE_OVERLAY"
    brand_colors: List[str] = field(default_factory=list)
    quality_threshold: int = 75  # Minimum acceptable score
    max_budget_per_run: Optional[float] = None


@dataclass
class ProductionRecord:
    """Record of a completed production"""
    run_id: str
    concept: str
    timestamp: datetime
    
    # Results
    status: str  # completed, failed, cancelled
    winning_tier: Optional[str] = None
    final_score: Optional[float] = None
    total_cost: float = 0
    duration_seconds: float = 0
    
    # What worked
    scenes_count: int = 0
    edit_style_used: str = "safe"
    
    # User feedback
    user_rating: Optional[int] = None  # 1-5
    user_notes: Optional[str] = None
    
    # Paths to outputs
    final_video_path: Optional[str] = None
    edl_path: Optional[str] = None


@dataclass
class LearnedPattern:
    """Pattern learned from successful productions"""
    pattern_name: str  # e.g., "podcast_intro", "product_demo"
    
    # Recommendations based on history
    recommended_tier: str
    recommended_scenes: int
    recommended_duration: int
    recommended_edit_style: str
    
    # Stats
    times_used: int = 0
    avg_score: float = 0
    avg_cost: float = 0
    
    # Keywords that trigger this pattern
    keywords: List[str] = field(default_factory=list)


@dataclass
class LongTermMemory:
    """Persistent memory across all runs"""
    # User preferences
    preferences: UserPreferences = field(default_factory=UserPreferences)
    
    # Production history
    total_runs: int = 0
    total_spent: float = 0
    production_history: List[ProductionRecord] = field(default_factory=list)
    
    # Learned patterns
    patterns: Dict[str, LearnedPattern] = field(default_factory=dict)
    
    # Favorite/saved assets
    saved_assets: List[AssetMemory] = field(default_factory=list)
    
    # Brand assets (logos, colors, etc.)
    brand_assets: List[Dict[str, Any]] = field(default_factory=list)
    
    # Last updated
    updated_at: Optional[datetime] = None
```

### core/memory/manager.py

```python
"""Memory manager for short-term and long-term memory"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import asyncio

from core.models.memory import (
    ShortTermMemory, LongTermMemory, UserPreferences,
    ProductionRecord, LearnedPattern, RunStage, StageEvent,
    PilotMemory, AssetMemory
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
    
    async def create_run(self, run_id: str, concept: str, budget: float, audio_tier: str = "SIMPLE_OVERLAY") -> ShortTermMemory:
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
    
    async def update_stage(self, run_id: str, stage: RunStage, details: dict = None):
        """Update current stage of a run"""
        memory = await self.get_run(run_id)
        if not memory:
            return
        
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
                        setattr(pilot, key, value)
                    break
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
    
    async def add_error(self, run_id: str, error: str):
        """Record an error"""
        memory = await self.get_run(run_id)
        if memory:
            memory.errors.append(error)
            await self._save_short_term(run_id)
    
    async def complete_run(self, run_id: str, status: str = "completed"):
        """Mark a run as complete and transfer learnings to long-term memory"""
        memory = await self.get_run(run_id)
        if not memory:
            return
        
        memory.current_stage = RunStage.COMPLETED if status == "completed" else RunStage.FAILED
        memory.completed_at = datetime.utcnow()
        memory.progress_percent = 100
        
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
    
    async def _transfer_to_long_term(self, short_term: ShortTermMemory):
        """Transfer learnings from completed run to long-term memory"""
        long_term = await self.get_long_term()
        
        # Find winning pilot
        winning_pilot = None
        for pilot in short_term.pilots:
            if pilot.pilot_id == short_term.winning_pilot_id:
                winning_pilot = pilot
                break
        
        # Create production record
        record = ProductionRecord(
            run_id=short_term.run_id,
            concept=short_term.concept,
            timestamp=short_term.completed_at or datetime.utcnow(),
            status="completed",
            winning_tier=winning_pilot.tier if winning_pilot else None,
            final_score=winning_pilot.quality_score if winning_pilot else None,
            total_cost=short_term.budget_spent,
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
        
        # Find or create pattern
        pattern_name = keywords[0] if keywords else "general"
        
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
            "podcast", "vlog", "review", "unboxing", "interview"
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
            memory_file = self.memory_path / "long_term.json"
            with open(memory_file, "w") as f:
                json.dump(self._serialize(self._long_term), f, indent=2, default=str)
    
    # ==================== SERIALIZATION ====================
    
    def _serialize(self, obj) -> dict:
        """Serialize dataclass to dict"""
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
        
        if "saved_assets" in data:
            data["saved_assets"] = [AssetMemory(**a) for a in data["saved_assets"]]
        
        if data.get("updated_at"):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        
        return LongTermMemory(**data)


# Global instance
memory_manager = MemoryManager()
```

## Dashboard Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      WEB DASHBOARD                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  PAGES:                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ /                    - Dashboard home                    │   │
│  │ /runs                - List all runs                     │   │
│  │ /runs/{id}           - Single run detail + preview       │   │
│  │ /runs/{id}/live      - Live progress (WebSocket)         │   │
│  │ /memory              - View/edit long-term memory        │   │
│  │ /preferences         - Edit user preferences             │   │
│  │ /library             - Saved assets & brand assets       │   │
│  │ /analytics           - Cost/quality trends               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  COMPONENTS:                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ RunCard         - Summary card for a run                │   │
│  │ PilotComparison - Side-by-side pilot comparison         │   │
│  │ SceneTimeline   - Visual timeline of scenes             │   │
│  │ VideoPlayer     - Preview video clips                   │   │
│  │ AudioPlayer     - Preview audio tracks                  │   │
│  │ BudgetGauge     - Visual budget tracker                 │   │
│  │ ProgressTracker - Stage-by-stage progress               │   │
│  │ MemoryViewer    - View learned patterns                 │   │
│  │ PreferencesForm - Edit preferences                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## API Endpoints

### server/routes/memory.py

```python
"""Memory API endpoints"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from core.memory.manager import memory_manager


router = APIRouter()


# ==================== REQUEST MODELS ====================

class PreferencesUpdate(BaseModel):
    preferred_style: Optional[str] = None
    preferred_tier: Optional[str] = None
    default_voice: Optional[str] = None
    default_voice_speed: Optional[float] = None
    default_music_mood: Optional[str] = None
    default_audio_tier: Optional[str] = None
    brand_colors: Optional[List[str]] = None
    quality_threshold: Optional[int] = None
    max_budget_per_run: Optional[float] = None


class RateRunRequest(BaseModel):
    rating: int  # 1-5
    notes: Optional[str] = None


# ==================== ENDPOINTS ====================

@router.get("/")
async def get_memory_overview():
    """Get overview of memory system"""
    long_term = await memory_manager.get_long_term()
    
    return {
        "total_runs": long_term.total_runs,
        "total_spent": long_term.total_spent,
        "patterns_learned": len(long_term.patterns),
        "saved_assets": len(long_term.saved_assets),
        "preferences_set": True
    }


@router.get("/preferences")
async def get_preferences():
    """Get user preferences"""
    prefs = await memory_manager.get_preferences()
    return prefs


@router.put("/preferences")
async def update_preferences(updates: PreferencesUpdate):
    """Update user preferences"""
    update_dict = {k: v for k, v in updates.dict().items() if v is not None}
    await memory_manager.update_preferences(**update_dict)
    return await memory_manager.get_preferences()


@router.get("/patterns")
async def get_patterns():
    """Get all learned patterns"""
    long_term = await memory_manager.get_long_term()
    return long_term.patterns


@router.get("/patterns/{pattern_name}")
async def get_pattern(pattern_name: str):
    """Get a specific pattern"""
    long_term = await memory_manager.get_long_term()
    if pattern_name not in long_term.patterns:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return long_term.patterns[pattern_name]


@router.get("/history")
async def get_history(limit: int = 20):
    """Get production history"""
    history = await memory_manager.get_production_history(limit)
    return {"runs": history, "total": len(history)}


@router.post("/history/{run_id}/rate")
async def rate_run(run_id: str, request: RateRunRequest):
    """Rate a completed run (for learning)"""
    long_term = await memory_manager.get_long_term()
    
    for record in long_term.production_history:
        if record.run_id == run_id:
            record.user_rating = request.rating
            record.user_notes = request.notes
            await memory_manager._save_long_term()
            return {"status": "updated"}
    
    raise HTTPException(status_code=404, detail="Run not found in history")


@router.get("/analytics")
async def get_analytics():
    """Get analytics from memory"""
    long_term = await memory_manager.get_long_term()
    history = long_term.production_history
    
    if not history:
        return {"message": "No production history yet"}
    
    # Calculate analytics
    total_runs = len(history)
    completed_runs = [r for r in history if r.status == "completed"]
    
    avg_cost = sum(r.total_cost for r in completed_runs) / len(completed_runs) if completed_runs else 0
    avg_score = sum(r.final_score for r in completed_runs if r.final_score) / len([r for r in completed_runs if r.final_score]) if completed_runs else 0
    
    # Tier distribution
    tier_counts = {}
    for r in completed_runs:
        tier = r.winning_tier or "unknown"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    return {
        "total_runs": total_runs,
        "completed_runs": len(completed_runs),
        "failed_runs": total_runs - len(completed_runs),
        "total_spent": long_term.total_spent,
        "avg_cost_per_run": avg_cost,
        "avg_quality_score": avg_score,
        "tier_distribution": tier_counts,
        "patterns_learned": len(long_term.patterns)
    }
```

### server/routes/runs.py (updated)

```python
"""Run management endpoints with memory integration"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import List
import asyncio
import json

from core.memory.manager import memory_manager, MemoryManager
from core.models.memory import ShortTermMemory, RunStage


router = APIRouter()


@router.get("/")
async def list_runs(limit: int = 20, status: str = None):
    """List all runs"""
    runs_path = memory_manager.base_path / "runs"
    
    if not runs_path.exists():
        return {"runs": []}
    
    runs = []
    for run_dir in sorted(runs_path.iterdir(), reverse=True)[:limit]:
        if run_dir.is_dir():
            memory = await memory_manager.get_run(run_dir.name)
            if memory:
                if status and memory.current_stage.value != status:
                    continue
                runs.append({
                    "run_id": memory.run_id,
                    "concept": memory.concept[:50] + "..." if len(memory.concept) > 50 else memory.concept,
                    "status": memory.current_stage.value,
                    "progress": memory.progress_percent,
                    "budget_total": memory.budget_total,
                    "budget_spent": memory.budget_spent,
                    "started_at": memory.started_at.isoformat() if memory.started_at else None
                })
    
    return {"runs": runs}


@router.get("/{run_id}")
async def get_run(run_id: str):
    """Get full run details"""
    memory = await memory_manager.get_run(run_id)
    
    if not memory:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return {
        "run_id": memory.run_id,
        "concept": memory.concept,
        "status": memory.current_stage.value,
        "progress": memory.progress_percent,
        "budget": {
            "total": memory.budget_total,
            "spent": memory.budget_spent,
            "remaining": memory.budget_total - memory.budget_spent
        },
        "pilots": [
            {
                "pilot_id": p.pilot_id,
                "tier": p.tier,
                "status": p.status,
                "score": p.quality_score,
                "budget_allocated": p.allocated_budget,
                "budget_spent": p.spent_budget
            }
            for p in memory.pilots
        ],
        "winning_pilot": memory.winning_pilot_id,
        "scenes": {
            "total": memory.total_scenes,
            "completed": memory.scenes_completed
        },
        "assets": [
            {
                "asset_id": a.asset_id,
                "type": a.asset_type,
                "path": a.path,
                "scene_id": a.scene_id,
                "duration": a.duration,
                "cost": a.cost
            }
            for a in memory.assets
        ],
        "timeline": [
            {
                "stage": e.stage.value,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "details": e.details
            }
            for e in memory.timeline
        ],
        "errors": memory.errors,
        "started_at": memory.started_at.isoformat() if memory.started_at else None,
        "completed_at": memory.completed_at.isoformat() if memory.completed_at else None
    }


@router.get("/{run_id}/assets")
async def get_run_assets(run_id: str, asset_type: str = None):
    """Get assets for a run"""
    memory = await memory_manager.get_run(run_id)
    
    if not memory:
        raise HTTPException(status_code=404, detail="Run not found")
    
    assets = memory.assets
    if asset_type:
        assets = [a for a in assets if a.asset_type == asset_type]
    
    return {"assets": assets}


@router.get("/{run_id}/preview")
async def get_run_preview(run_id: str):
    """Get HTML preview page for a run"""
    memory = await memory_manager.get_run(run_id)
    
    if not memory:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Generate HTML preview
    html = generate_preview_html(memory)
    return HTMLResponse(content=html)


@router.websocket("/{run_id}/live")
async def run_live_updates(websocket: WebSocket, run_id: str):
    """WebSocket for live run updates"""
    await websocket.accept()
    
    try:
        last_progress = -1
        while True:
            memory = await memory_manager.get_run(run_id)
            
            if memory:
                if memory.progress_percent != last_progress:
                    await websocket.send_json({
                        "run_id": run_id,
                        "stage": memory.current_stage.value,
                        "progress": memory.progress_percent,
                        "budget_spent": memory.budget_spent,
                        "scenes_completed": memory.scenes_completed,
                        "errors": memory.errors[-5:] if memory.errors else []
                    })
                    last_progress = memory.progress_percent
                
                if memory.current_stage in [RunStage.COMPLETED, RunStage.FAILED]:
                    await websocket.send_json({"status": "complete"})
                    break
            
            await asyncio.sleep(1)
    
    except WebSocketDisconnect:
        pass


def generate_preview_html(memory: ShortTermMemory) -> str:
    """Generate HTML preview page"""
    
    videos_html = ""
    audio_html = ""
    
    for asset in memory.assets:
        if asset.asset_type == "video":
            videos_html += f"""
            <div class="asset-card">
                <h4>{asset.scene_id or asset.asset_id}</h4>
                <video controls width="320">
                    <source src="/artifacts/runs/{memory.run_id}/{asset.path}" type="video/mp4">
                </video>
                <p>Duration: {asset.duration or 'N/A'}s | Cost: ${asset.cost:.2f}</p>
            </div>
            """
        elif asset.asset_type == "audio":
            audio_html += f"""
            <div class="asset-card">
                <h4>{asset.scene_id or asset.asset_id}</h4>
                <audio controls>
                    <source src="/artifacts/runs/{memory.run_id}/{asset.path}" type="audio/mpeg">
                </audio>
                <p>Duration: {asset.duration or 'N/A'}s | Cost: ${asset.cost:.2f}</p>
            </div>
            """
    
    pilots_html = ""
    for pilot in memory.pilots:
        status_color = "green" if pilot.status == "approved" else "red" if pilot.status == "rejected" else "orange"
        pilots_html += f"""
        <div class="pilot-card" style="border-left: 4px solid {status_color}">
            <h4>{pilot.pilot_id} ({pilot.tier})</h4>
            <p>Score: {pilot.quality_score or 'N/A'} | Status: {pilot.status}</p>
            <p>Budget: ${pilot.spent_budget:.2f} / ${pilot.allocated_budget:.2f}</p>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Run {memory.run_id} - Claude Studio Producer</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }}
            .header {{ background: #16213e; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .header h1 {{ margin: 0; color: #4a9eff; }}
            .concept {{ color: #888; margin-top: 10px; }}
            .budget {{ display: flex; gap: 20px; margin-top: 15px; }}
            .budget-item {{ background: #0f3460; padding: 10px 20px; border-radius: 4px; }}
            .budget-item .value {{ font-size: 24px; font-weight: bold; color: #4a9eff; }}
            .section {{ margin-bottom: 30px; }}
            .section h2 {{ border-bottom: 2px solid #4a9eff; padding-bottom: 10px; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
            .asset-card, .pilot-card {{ background: #16213e; padding: 15px; border-radius: 8px; }}
            .asset-card h4, .pilot-card h4 {{ margin: 0 0 10px 0; color: #4a9eff; }}
            video, audio {{ width: 100%; margin: 10px 0; }}
            .progress {{ background: #0f3460; border-radius: 4px; height: 20px; overflow: hidden; }}
            .progress-bar {{ background: #4a9eff; height: 100%; transition: width 0.3s; }}
            .timeline {{ background: #16213e; padding: 15px; border-radius: 8px; }}
            .timeline-item {{ padding: 10px 0; border-bottom: 1px solid #0f3460; }}
            .timeline-item:last-child {{ border-bottom: none; }}
            .status {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; }}
            .status.completed {{ background: #2ecc71; }}
            .status.running {{ background: #f39c12; }}
            .status.failed {{ background: #e74c3c; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎬 Run: {memory.run_id}</h1>
            <div class="concept">{memory.concept}</div>
            <div class="budget">
                <div class="budget-item">
                    <div class="label">Total Budget</div>
                    <div class="value">${memory.budget_total:.2f}</div>
                </div>
                <div class="budget-item">
                    <div class="label">Spent</div>
                    <div class="value">${memory.budget_spent:.2f}</div>
                </div>
                <div class="budget-item">
                    <div class="label">Remaining</div>
                    <div class="value">${memory.budget_total - memory.budget_spent:.2f}</div>
                </div>
            </div>
            <div style="margin-top: 15px;">
                <div class="progress">
                    <div class="progress-bar" style="width: {memory.progress_percent}%"></div>
                </div>
                <div style="margin-top: 5px;">
                    <span class="status {memory.current_stage.value}">{memory.current_stage.value}</span>
                    {memory.progress_percent}% complete
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>🎯 Pilots</h2>
            <div class="grid">
                {pilots_html or '<p>No pilots yet</p>'}
            </div>
        </div>
        
        <div class="section">
            <h2>🎬 Videos</h2>
            <div class="grid">
                {videos_html or '<p>No videos generated yet</p>'}
            </div>
        </div>
        
        <div class="section">
            <h2>🎤 Audio</h2>
            <div class="grid">
                {audio_html or '<p>No audio generated yet</p>'}
            </div>
        </div>
        
        <div class="section">
            <h2>📋 Timeline</h2>
            <div class="timeline">
                {''.join(f'<div class="timeline-item"><strong>{e.stage.value}</strong> - {e.timestamp}</div>' for e in memory.timeline) or '<p>No events yet</p>'}
            </div>
        </div>
        
        <script>
            // Auto-refresh if not completed
            const status = "{memory.current_stage.value}";
            if (status !== "completed" && status !== "failed") {{
                setTimeout(() => location.reload(), 5000);
            }}
        </script>
    </body>
    </html>
    """
```

## Integration with Orchestrator

### workflows/orchestrator.py (memory integration)

```python
# Add to StudioOrchestrator

from core.memory.manager import memory_manager
from core.models.memory import PilotMemory, AssetMemory, RunStage


class StudioOrchestrator(Workflow):
    
    async def run(self, concept: str, budget: float, **kwargs) -> ProductionResult:
        # Generate run ID
        run_id = str(uuid.uuid4())[:8]
        
        # Initialize short-term memory
        await memory_manager.create_run(
            run_id=run_id,
            concept=concept,
            budget=budget,
            audio_tier=kwargs.get("audio_tier", "SIMPLE_OVERLAY")
        )
        
        try:
            # Check long-term memory for similar patterns
            pattern = await memory_manager.get_pattern(concept)
            if pattern:
                print(f"Found pattern: {pattern.pattern_name}")
                print(f"Recommended: {pattern.recommended_tier}, {pattern.recommended_scenes} scenes")
            
            # Get user preferences
            prefs = await memory_manager.get_preferences()
            
            # Stage 1: Asset Analysis
            await memory_manager.update_stage(run_id, RunStage.ANALYZING_ASSETS)
            # ... asset analysis ...
            
            # Stage 2: Planning
            await memory_manager.update_stage(run_id, RunStage.PLANNING_PILOTS)
            pilots = await self.producer.run(concept, budget)
            
            # Record pilots in memory
            for pilot in pilots:
                await memory_manager.add_pilot(run_id, PilotMemory(
                    pilot_id=pilot.pilot_id,
                    tier=pilot.tier.value,
                    allocated_budget=pilot.allocated_budget,
                    spent_budget=0,
                    scenes_generated=0
                ))
            
            # Stage 3: Script Generation
            await memory_manager.update_stage(run_id, RunStage.GENERATING_SCRIPTS)
            # ... script generation ...
            
            # Stage 4: Video Generation
            await memory_manager.update_stage(run_id, RunStage.GENERATING_VIDEO)
            # ... video generation ...
            
            # Record each generated video
            for video in generated_videos:
                await memory_manager.add_asset(run_id, AssetMemory(
                    asset_id=video.video_id,
                    asset_type="video",
                    path=video.video_url,
                    scene_id=video.scene_id,
                    duration=video.duration,
                    cost=video.generation_cost
                ))
            
            # Stage 5: Audio Generation
            await memory_manager.update_stage(run_id, RunStage.GENERATING_AUDIO)
            # ... similar pattern ...
            
            # Stage 6: Evaluation
            await memory_manager.update_stage(run_id, RunStage.EVALUATING)
            # ... evaluation ...
            
            # Update pilot status based on evaluation
            for eval_result in evaluations:
                await memory_manager.update_pilot(
                    run_id,
                    eval_result.pilot_id,
                    quality_score=eval_result.score,
                    status="approved" if eval_result.approved else "rejected"
                )
            
            # Stage 7: Editing
            await memory_manager.update_stage(run_id, RunStage.EDITING)
            # ...
            
            # Stage 8: Rendering
            await memory_manager.update_stage(run_id, RunStage.RENDERING)
            # ...
            
            # Complete
            await memory_manager.complete_run(run_id, "completed")
            
            return result
            
        except Exception as e:
            await memory_manager.add_error(run_id, str(e))
            await memory_manager.complete_run(run_id, "failed")
            raise
```

## Dashboard Pages

### Templates Structure

```
server/
├── templates/
│   ├── base.html           # Base template with nav
│   ├── index.html          # Dashboard home
│   ├── runs/
│   │   ├── list.html       # All runs
│   │   └── detail.html     # Single run preview
│   ├── memory/
│   │   ├── overview.html   # Memory overview
│   │   ├── preferences.html # Edit preferences
│   │   └── patterns.html   # View patterns
│   └── analytics.html      # Charts and stats
```

## Summary

This spec provides:

1. **Short-Term Memory**: Track state within each run
   - Current stage, progress
   - Pilots and their scores
   - Generated assets
   - Timeline of events
   - Errors and warnings

2. **Long-Term Memory**: Learn across runs
   - User preferences
   - Production history
   - Learned patterns
   - Saved assets

3. **Memory Manager**: Core class for all memory operations
   - Create/update/complete runs
   - Persist to JSON files
   - Transfer learnings automatically

4. **API Endpoints**: Full REST API
   - `/memory/*` - Memory operations
   - `/runs/*` - Run management
   - WebSocket for live updates

5. **Dashboard Preview**: HTML preview pages
   - Video/audio players
   - Pilot comparison
   - Budget tracking
   - Progress visualization

6. **Orchestrator Integration**: Memory hooks throughout pipeline
   - Stage updates
   - Asset tracking
   - Error recording
   - Pattern learning
