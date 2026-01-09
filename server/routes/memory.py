"""Memory API endpoints"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from core.memory import memory_manager


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
    return {
        "preferred_style": prefs.preferred_style,
        "preferred_tier": prefs.preferred_tier,
        "default_voice": prefs.default_voice,
        "default_voice_speed": prefs.default_voice_speed,
        "default_music_mood": prefs.default_music_mood,
        "default_audio_tier": prefs.default_audio_tier,
        "brand_colors": prefs.brand_colors,
        "quality_threshold": prefs.quality_threshold,
        "max_budget_per_run": prefs.max_budget_per_run
    }


@router.put("/preferences")
async def update_preferences(updates: PreferencesUpdate):
    """Update user preferences"""
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    await memory_manager.update_preferences(**update_dict)
    return await get_preferences()


@router.get("/patterns")
async def get_patterns():
    """Get all learned patterns"""
    long_term = await memory_manager.get_long_term()
    return {
        name: {
            "pattern_name": p.pattern_name,
            "recommended_tier": p.recommended_tier,
            "recommended_scenes": p.recommended_scenes,
            "recommended_duration": p.recommended_duration,
            "recommended_edit_style": p.recommended_edit_style,
            "times_used": p.times_used,
            "avg_score": p.avg_score,
            "avg_cost": p.avg_cost,
            "keywords": p.keywords
        }
        for name, p in long_term.patterns.items()
    }


@router.get("/patterns/{pattern_name}")
async def get_pattern(pattern_name: str):
    """Get a specific pattern"""
    long_term = await memory_manager.get_long_term()
    if pattern_name not in long_term.patterns:
        raise HTTPException(status_code=404, detail="Pattern not found")

    p = long_term.patterns[pattern_name]
    return {
        "pattern_name": p.pattern_name,
        "recommended_tier": p.recommended_tier,
        "recommended_scenes": p.recommended_scenes,
        "recommended_duration": p.recommended_duration,
        "recommended_edit_style": p.recommended_edit_style,
        "times_used": p.times_used,
        "avg_score": p.avg_score,
        "avg_cost": p.avg_cost,
        "keywords": p.keywords
    }


@router.get("/history")
async def get_history(limit: int = 20):
    """Get production history"""
    history = await memory_manager.get_production_history(limit)
    return {
        "runs": [
            {
                "run_id": r.run_id,
                "concept": r.concept,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "status": r.status,
                "winning_tier": r.winning_tier,
                "final_score": r.final_score,
                "total_cost": r.total_cost,
                "duration_seconds": r.duration_seconds,
                "scenes_count": r.scenes_count,
                "user_rating": r.user_rating
            }
            for r in history
        ],
        "total": len(history)
    }


@router.post("/history/{run_id}/rate")
async def rate_run(run_id: str, request: RateRunRequest):
    """Rate a completed run (for learning)"""
    if not 1 <= request.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    long_term = await memory_manager.get_long_term()

    for record in long_term.production_history:
        if record.run_id == run_id:
            record.user_rating = request.rating
            record.user_notes = request.notes
            await memory_manager._save_long_term()
            return {"status": "updated", "run_id": run_id, "rating": request.rating}

    raise HTTPException(status_code=404, detail="Run not found in history")


@router.get("/analytics")
async def get_analytics():
    """Get analytics from memory"""
    long_term = await memory_manager.get_long_term()
    history = long_term.production_history

    if not history:
        return {
            "message": "No production history yet",
            "total_runs": 0,
            "completed_runs": 0,
            "failed_runs": 0,
            "total_spent": 0,
            "avg_cost_per_run": 0,
            "avg_quality_score": 0,
            "tier_distribution": {},
            "patterns_learned": 0
        }

    # Calculate analytics
    completed_runs = [r for r in history if r.status == "completed"]
    failed_runs = [r for r in history if r.status == "failed"]

    avg_cost = sum(r.total_cost for r in completed_runs) / len(completed_runs) if completed_runs else 0

    scored_runs = [r for r in completed_runs if r.final_score]
    avg_score = sum(r.final_score for r in scored_runs) / len(scored_runs) if scored_runs else 0

    # Tier distribution
    tier_counts = {}
    for r in completed_runs:
        tier = r.winning_tier or "unknown"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # Rating distribution
    rated_runs = [r for r in completed_runs if r.user_rating]
    rating_counts = {}
    for r in rated_runs:
        rating_counts[r.user_rating] = rating_counts.get(r.user_rating, 0) + 1

    return {
        "total_runs": len(history),
        "completed_runs": len(completed_runs),
        "failed_runs": len(failed_runs),
        "total_spent": long_term.total_spent,
        "avg_cost_per_run": round(avg_cost, 2),
        "avg_quality_score": round(avg_score, 1),
        "tier_distribution": tier_counts,
        "rating_distribution": rating_counts,
        "patterns_learned": len(long_term.patterns),
        "runs_rated": len(rated_runs)
    }
