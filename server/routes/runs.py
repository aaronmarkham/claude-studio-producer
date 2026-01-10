"""Run management endpoints with memory integration"""

from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import asyncio

from core.memory import memory_manager
from core.models.memory import ShortTermMemory, RunStage


router = APIRouter()

# Setup Jinja2 templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    page: int = 1,
    per_page: int = 25,
    sort: str = "newest",
    status_filter: str = None
):
    """Dashboard page with overview of runs and stats, pagination, filtering, sorting"""
    # Get ALL runs for filtering/sorting (we need full list for accurate pagination)
    all_run_ids = await memory_manager.list_runs(limit=500)
    all_runs = []

    for run_id in all_run_ids:
        memory = await memory_manager.get_run(run_id)
        if memory:
            # Calculate duration
            duration = None
            if memory.started_at and memory.completed_at:
                delta = memory.completed_at - memory.started_at
                duration = f"{delta.total_seconds():.1f}s"
            elif memory.started_at:
                delta = datetime.utcnow() - memory.started_at
                duration = f"{delta.total_seconds():.0f}s (running)"

            # Format created time
            created_at = memory.started_at.strftime("%Y-%m-%d %H:%M") if memory.started_at else "-"

            # Determine display status - mock runs show "mock" instead of "completed"
            display_status = memory.current_stage.value
            is_mock = memory.budget_spent == 0 and memory.current_stage == RunStage.COMPLETED
            if is_mock:
                display_status = "mock"

            all_runs.append({
                "run_id": memory.run_id,
                "concept": memory.concept[:60] + "..." if len(memory.concept) > 60 else memory.concept,
                "status": display_status,
                "raw_status": memory.current_stage.value,
                "is_mock": is_mock,
                "progress": memory.progress_percent,
                "budget_total": memory.budget_total,
                "budget_spent": memory.budget_spent,
                "duration": duration,
                "created_at": created_at,
                "started_at": memory.started_at
            })

    # Count statuses for filter badges
    status_counts = {}
    for run in all_runs:
        s = run["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    # Apply status filter
    if status_filter:
        filters = status_filter.split(",")
        all_runs = [r for r in all_runs if r["status"] in filters]

    # Apply sorting
    if sort == "newest":
        all_runs.sort(key=lambda r: r["started_at"] or datetime.min, reverse=True)
    elif sort == "oldest":
        all_runs.sort(key=lambda r: r["started_at"] or datetime.min)
    elif sort == "budget_high":
        all_runs.sort(key=lambda r: r["budget_spent"], reverse=True)
    elif sort == "budget_low":
        all_runs.sort(key=lambda r: r["budget_spent"])
    elif sort == "name":
        all_runs.sort(key=lambda r: r["run_id"])

    # Pagination
    total_runs = len(all_runs)
    total_pages = max(1, (total_runs + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    runs = all_runs[start_idx:end_idx]

    # Get stats from long-term memory
    ltm = await memory_manager.get_long_term()

    # Calculate success rate
    completed = sum(1 for r in ltm.production_history if r.status == "completed")
    failed = sum(1 for r in ltm.production_history if r.status == "failed")
    total = completed + failed
    success_rate = int((completed / total * 100) if total > 0 else 100)

    stats = {
        "total_runs": ltm.total_runs,
        "total_spent": ltm.total_spent,
        "success_rate": success_rate,
        "patterns_learned": len(ltm.patterns)
    }

    # Pagination info
    pagination = {
        "page": page,
        "per_page": per_page,
        "total_runs": total_runs,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "showing_start": start_idx + 1 if total_runs > 0 else 0,
        "showing_end": min(end_idx, total_runs)
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "runs": runs,
        "stats": stats,
        "pagination": pagination,
        "sort": sort,
        "status_filter": status_filter or "",
        "status_counts": status_counts,
        "active_page": "dashboard"
    })


@router.get("/")
async def list_runs(limit: int = 20, status: str = None):
    """List all runs"""
    run_ids = await memory_manager.list_runs(limit=limit * 2)  # Get more to filter

    runs = []
    for run_id in run_ids:
        memory = await memory_manager.get_run(run_id)
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
                "scenes": f"{memory.scenes_completed}/{memory.total_scenes}",
                "started_at": memory.started_at.isoformat() if memory.started_at else None,
                "completed_at": memory.completed_at.isoformat() if memory.completed_at else None
            })
            if len(runs) >= limit:
                break

    return {"runs": runs, "total": len(runs)}


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
                "budget_spent": p.spent_budget,
                "scenes_generated": p.scenes_generated
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
                "cost": a.cost,
                "metadata": a.metadata
            }
            for a in memory.assets
        ],
        "timeline": [
            {
                "stage": e.stage.value,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "duration_ms": e.duration_ms,
                "details": e.details
            }
            for e in memory.timeline
        ],
        "errors": memory.errors,
        "warnings": memory.warnings,
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

    return {
        "assets": [
            {
                "asset_id": a.asset_id,
                "type": a.asset_type,
                "path": a.path,
                "scene_id": a.scene_id,
                "duration": a.duration,
                "cost": a.cost,
                "metadata": a.metadata
            }
            for a in assets
        ]
    }


@router.delete("/{run_id}")
async def delete_run(run_id: str):
    """Delete a run and all its artifacts"""
    deleted = await memory_manager.delete_run(run_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")

    return {"status": "deleted", "run_id": run_id}


@router.get("/{run_id}/preview", response_class=HTMLResponse)
async def get_run_preview(request: Request, run_id: str):
    """Get HTML preview page for a run"""
    memory = await memory_manager.get_run(run_id)

    if not memory:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get final video path (prefer the direct field, fallback to searching assets/renders)
    final_video_path = memory.final_video_path
    if not final_video_path:
        # First try to find in assets
        for asset in memory.assets:
            if asset.asset_type == "video" and "final" in asset.path.lower():
                final_video_path = asset.path
                break

    # If still no final video, look for rendered videos in the renders directory
    rendered_videos = []
    renders_dir = Path(f"artifacts/runs/{run_id}/renders")
    if renders_dir.exists():
        # Search recursively for all mp4 files in renders/
        for video_file in renders_dir.glob("**/*.mp4"):
            if video_file.is_file():
                # Get relative path from artifacts dir
                rel_path = str(video_file.relative_to(Path("artifacts"))).replace("\\", "/")
                rendered_videos.append({
                    "name": video_file.name,
                    "path": rel_path,
                    "size": video_file.stat().st_size,
                    "mtime": video_file.stat().st_mtime
                })
        # Sort by modification time, newest first
        rendered_videos.sort(key=lambda x: x["mtime"], reverse=True)

        # Use the most recent render as final video if not set
        # Prefer "final" in name, otherwise use most recent
        if not final_video_path and rendered_videos:
            final_candidates = [v for v in rendered_videos if "final" in v["name"].lower()]
            if final_candidates:
                final_video_path = final_candidates[0]["path"]
            else:
                final_video_path = rendered_videos[0]["path"]

    # Also collect individual scene videos if no renders found
    scene_videos = []
    videos_dir = Path(f"artifacts/runs/{run_id}/videos")
    if videos_dir.exists():
        for video_file in videos_dir.glob("*.mp4"):
            if video_file.is_file():
                rel_path = f"runs/{run_id}/videos/{video_file.name}"
                scene_videos.append({
                    "name": video_file.name,
                    "path": rel_path,
                    "size": video_file.stat().st_size
                })
        scene_videos.sort(key=lambda x: x["name"])

    # If still no final video but we have scene videos, use first scene
    if not final_video_path and scene_videos:
        final_video_path = scene_videos[0]["path"]

    # Find audio path
    audio_path = None
    for asset in memory.assets:
        if asset.asset_type == "audio":
            audio_path = asset.path
            break

    # Format timeline for display
    timeline = []
    for event in memory.timeline:
        timeline.append({
            "stage": event.stage.value,
            "timestamp": event.timestamp.strftime("%H:%M:%S") if event.timestamp else "-",
            "duration_ms": event.duration_ms
        })

    # Build seed assets list from seed_asset_ids
    seed_assets = []
    for asset in memory.assets:
        if asset.asset_id in memory.seed_asset_ids:
            seed_assets.append({
                "asset_id": asset.asset_id,
                "asset_type": asset.asset_type,
                "path": asset.path
            })

    # Prepare run data for template
    run_data = {
        "run_id": memory.run_id,
        "concept": memory.concept,
        "current_stage": memory.current_stage.value,
        "progress_percent": memory.progress_percent,
        "budget_total": memory.budget_total,
        "budget_spent": memory.budget_spent,
        "audio_tier": memory.audio_tier,
        "total_scenes": memory.total_scenes,
        "scenes_completed": memory.scenes_completed,
        "winning_pilot_id": memory.winning_pilot_id,
        "final_video_path": final_video_path,
        "rendered_videos": rendered_videos,
        "scene_videos": scene_videos,
        "audio_path": audio_path,
        "seed_assets": seed_assets,
        "extracted_themes": memory.extracted_themes,
        "extracted_colors": memory.extracted_colors,
        "pilots": [
            {
                "pilot_id": p.pilot_id,
                "tier": p.tier,
                "allocated_budget": p.allocated_budget,
                "spent_budget": p.spent_budget,
                "scenes_generated": p.scenes_generated,
                "quality_score": p.quality_score,
                "status": p.status
            }
            for p in memory.pilots
        ],
        "assets": [
            {
                "asset_id": a.asset_id,
                "asset_type": a.asset_type,
                "path": a.path,
                "duration": a.duration,
                "cost": a.cost
            }
            for a in memory.assets
        ],
        "timeline": timeline,
        "errors": memory.errors
    }

    return templates.TemplateResponse("preview.html", {
        "request": request,
        "run": run_data,
        "active_page": "runs"
    })


@router.websocket("/{run_id}/live")
async def run_live_updates(websocket: WebSocket, run_id: str):
    """WebSocket for live run updates"""
    await websocket.accept()

    try:
        last_progress = -1
        last_stage = None

        while True:
            memory = await memory_manager.get_run(run_id)

            if memory:
                # Send update if progress or stage changed
                if memory.progress_percent != last_progress or memory.current_stage != last_stage:
                    await websocket.send_json({
                        "run_id": run_id,
                        "stage": memory.current_stage.value,
                        "progress": memory.progress_percent,
                        "budget_spent": memory.budget_spent,
                        "scenes_completed": memory.scenes_completed,
                        "total_scenes": memory.total_scenes,
                        "assets_count": len(memory.assets),
                        "errors": memory.errors[-5:] if memory.errors else []
                    })
                    last_progress = memory.progress_percent
                    last_stage = memory.current_stage

                if memory.current_stage in [RunStage.COMPLETED, RunStage.FAILED]:
                    await websocket.send_json({
                        "status": "complete",
                        "final_stage": memory.current_stage.value
                    })
                    break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
