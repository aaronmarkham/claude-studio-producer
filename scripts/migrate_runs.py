#!/usr/bin/env python3
"""
Migrate old production runs to the new memory system.

Reads metadata.json from existing runs and creates memory.json files
compatible with the new MemoryManager system.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse datetime string from metadata"""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None


def migrate_run(run_path: Path) -> bool:
    """
    Migrate a single run to the new memory format.
    Returns True if migration was successful.
    """
    metadata_path = run_path / "metadata.json"
    memory_path = run_path / "memory.json"

    # Skip if no metadata.json
    if not metadata_path.exists():
        return False

    # Skip if already has memory.json
    if memory_path.exists():
        print(f"  Skipping {run_path.name} - already has memory.json")
        return False

    # Load metadata
    try:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"  Error reading metadata for {run_path.name}: {e}")
        return False

    # Extract data from metadata
    run_id = metadata.get("run_id", run_path.name)
    concept = metadata.get("concept", "Unknown concept")
    budget_total = metadata.get("budget", 10.0)
    audio_tier = metadata.get("audio_tier", "SIMPLE_OVERLAY").upper()
    status = metadata.get("status", "completed")
    costs = metadata.get("costs", {})
    stages = metadata.get("stages", {})
    errors = metadata.get("errors", [])

    # Parse times
    started_at = parse_datetime(metadata.get("start_time"))
    completed_at = parse_datetime(metadata.get("end_time"))

    # Determine stage
    if status == "completed":
        current_stage = "completed"
        progress = 100
    elif status == "failed":
        current_stage = "failed"
        progress = 0
    else:
        current_stage = "completed"
        progress = 100

    # Count scenes and assets
    scenes_dir = run_path / "scenes"
    videos_dir = run_path / "videos"
    audio_dir = run_path / "audio"
    renders_dir = run_path / "renders"

    scene_files = list(scenes_dir.glob("*.json")) if scenes_dir.exists() else []
    video_files = list(videos_dir.glob("*.mp4")) if videos_dir.exists() else []
    audio_files = list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.wav")) if audio_dir.exists() else []

    total_scenes = len(scene_files)
    scenes_completed = len(video_files)

    # Build assets list
    assets = []

    # Add video assets
    for vf in video_files:
        assets.append({
            "asset_id": vf.stem,
            "asset_type": "video",
            "path": f"runs/{run_id}/videos/{vf.name}",
            "scene_id": vf.stem.replace("_v0", ""),
            "duration": 5.0,  # Default duration
            "cost": costs.get("video", 0) / max(len(video_files), 1),
            "metadata": {}
        })

    # Add audio assets
    for af in audio_files:
        assets.append({
            "asset_id": af.stem,
            "asset_type": "audio",
            "path": f"runs/{run_id}/audio/{af.name}",
            "scene_id": af.stem.replace("_voice", "").replace("_music", ""),
            "duration": None,
            "cost": costs.get("audio", 0) / max(len(audio_files), 1),
            "metadata": {}
        })

    # Add rendered videos
    if renders_dir.exists():
        render_subdir = renders_dir / run_id
        if render_subdir.exists():
            for rf in render_subdir.glob("*_final.mp4"):
                assets.append({
                    "asset_id": rf.stem,
                    "asset_type": "video",
                    "path": f"runs/{run_id}/renders/{run_id}/{rf.name}",
                    "scene_id": "final",
                    "duration": None,
                    "cost": 0,
                    "metadata": {"render_type": "final"}
                })

    # Build pilot info from metadata
    pilots = []
    producer_stage = stages.get("producer", {})
    pilot_info = producer_stage.get("pilot_selected", {})
    if pilot_info:
        pilots.append({
            "pilot_id": "pilot_1",
            "tier": pilot_info.get("tier", "STANDARD").upper(),
            "allocated_budget": pilot_info.get("allocated_budget", budget_total),
            "spent_budget": costs.get("total", 0),
            "scenes_generated": scenes_completed,
            "quality_score": stages.get("critic", {}).get("critic_score"),
            "status": "approved" if status == "completed" else "rejected",
            "rejection_reason": None
        })

    # Build timeline from stages
    timeline = []
    stage_order = [
        ("initialized", "producer"),
        ("planning_pilots", "producer"),
        ("generating_scripts", "script_writer"),
        ("generating_video", "video_generator"),
        ("generating_audio", "audio_generator"),
        ("evaluating", "qa_verifier"),
        ("editing", "editor"),
        ("rendering", "renderer"),
    ]

    current_time = started_at or datetime.utcnow()
    for stage_name, metadata_key in stage_order:
        stage_data = stages.get(metadata_key, {})
        duration_ms = int(stage_data.get("duration_seconds", 0) * 1000)

        timeline.append({
            "stage": stage_name,
            "timestamp": current_time.isoformat() if current_time else None,
            "duration_ms": duration_ms if duration_ms > 0 else None,
            "details": {},
            "error": None
        })

        if duration_ms > 0 and current_time:
            current_time = datetime.fromtimestamp(current_time.timestamp() + stage_data.get("duration_seconds", 0))

    # Add completion stage
    timeline.append({
        "stage": current_stage,
        "timestamp": completed_at.isoformat() if completed_at else None,
        "duration_ms": None,
        "details": {},
        "error": None
    })

    # Build memory.json structure
    memory_data = {
        "run_id": run_id,
        "concept": concept,
        "budget_total": budget_total,
        "budget_spent": costs.get("total", 0),
        "audio_tier": audio_tier,
        "current_stage": current_stage,
        "progress_percent": progress,
        "pilots": pilots,
        "winning_pilot_id": "pilot_1" if pilots else None,
        "total_scenes": total_scenes,
        "scenes_completed": scenes_completed,
        "assets": assets,
        "timeline": timeline,
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "errors": errors,
        "warnings": [],
        "seed_asset_ids": [],
        "extracted_themes": [],
        "extracted_colors": []
    }

    # Write memory.json
    try:
        with open(memory_path, "w") as f:
            json.dump(memory_data, f, indent=2)
        print(f"  Migrated {run_id}: {total_scenes} scenes, {len(assets)} assets, ${costs.get('total', 0):.2f} spent")
        return True
    except Exception as e:
        print(f"  Error writing memory.json for {run_id}: {e}")
        return False


def main():
    """Run migration on all runs in artifacts/runs/"""
    # Find artifacts directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    runs_dir = project_root / "artifacts" / "runs"

    if not runs_dir.exists():
        print(f"Runs directory not found: {runs_dir}")
        return

    print(f"Scanning {runs_dir} for runs to migrate...\n")

    migrated = 0
    skipped = 0
    failed = 0

    for run_path in sorted(runs_dir.iterdir()):
        if not run_path.is_dir():
            continue

        # Skip test runs (they already have memory.json)
        if run_path.name.startswith("test_"):
            skipped += 1
            continue

        result = migrate_run(run_path)
        if result:
            migrated += 1
        elif (run_path / "memory.json").exists():
            skipped += 1
        else:
            failed += 1

    print(f"\nMigration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped:  {skipped}")
    print(f"  Failed:   {failed}")


if __name__ == "__main__":
    main()
