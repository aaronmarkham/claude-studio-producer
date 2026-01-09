#!/usr/bin/env python3
"""
Sync metadata.json files to memory.json format for dashboard compatibility.

Scans run directories that have metadata.json but no memory.json,
and creates a compatible memory.json file.
"""

import json
from pathlib import Path
from datetime import datetime


def parse_datetime(dt_str: str) -> datetime:
    """Parse ISO datetime string"""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        return None


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    runs_dir = project_root / "artifacts" / "runs"

    print(f"Scanning {runs_dir} for runs with metadata.json but no memory.json...\n")

    synced_count = 0

    for run_path in sorted(runs_dir.iterdir()):
        if not run_path.is_dir():
            continue

        metadata_path = run_path / "metadata.json"
        memory_path = run_path / "memory.json"

        # Skip if no metadata or already has memory
        if not metadata_path.exists():
            continue
        if memory_path.exists():
            continue

        print(f"  {run_path.name}:")

        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"    Error reading metadata.json: {e}")
            continue

        # Build memory.json from metadata.json
        memory = {
            "run_id": metadata.get("run_id", run_path.name),
            "concept": metadata.get("concept", ""),
            "budget_total": metadata.get("budget", 10.0),
            "budget_spent": metadata.get("costs", {}).get("total", 0.0),
            "audio_tier": metadata.get("audio_tier", "NONE").upper(),
            "current_stage": "completed" if metadata.get("status") == "completed" else "failed",
            "progress_percent": 100 if metadata.get("status") == "completed" else 0,
            "pilots": [],
            "winning_pilot_id": None,
            "total_scenes": metadata.get("stages", {}).get("script_writer", {}).get("num_scenes", 0),
            "scenes_completed": metadata.get("stages", {}).get("video_generator", {}).get("num_videos", 0),
            "assets": [],
            "timeline": [],
            "started_at": metadata.get("start_time"),
            "completed_at": metadata.get("end_time"),
            "errors": [],
            "warnings": [],
            "seed_asset_ids": [],
            "extracted_themes": [],
            "extracted_colors": [],
            "final_video_path": None
        }

        # Add pilot info from producer stage
        producer = metadata.get("stages", {}).get("producer", {})
        if producer:
            memory["pilots"] = [{
                "pilot_id": "pilot_1",
                "tier": producer.get("pilot_tier", "MOTION_GRAPHICS").upper(),
                "allocated_budget": producer.get("allocated_budget", 0),
                "spent_budget": metadata.get("costs", {}).get("total", 0),
                "scenes_generated": memory["scenes_completed"],
                "quality_score": metadata.get("stages", {}).get("critic", {}).get("score"),
                "status": "approved",
                "rejection_reason": None
            }]
            memory["winning_pilot_id"] = "pilot_1"

        # Find video assets
        videos_dir = run_path / "videos"
        renders_dir = run_path / "renders" / run_path.name

        if videos_dir.exists():
            for vf in sorted(videos_dir.glob("*.mp4")):
                rel_path = f"runs/{run_path.name}/videos/{vf.name}"
                scene_id = None
                if "scene_" in vf.name:
                    parts = vf.stem.split("_")
                    for i, p in enumerate(parts):
                        if p == "scene" and i + 1 < len(parts):
                            scene_id = f"scene_{parts[i+1]}"
                            break

                memory["assets"].append({
                    "asset_id": vf.stem,
                    "asset_type": "video",
                    "path": rel_path,
                    "scene_id": scene_id,
                    "duration": 5.0,
                    "cost": 0.40 if metadata.get("live_mode") else 0.0,
                    "metadata": {"filename": vf.name, "is_final": False}
                })

        # Find final rendered video
        if renders_dir.exists():
            for rf in renders_dir.glob("*_final.mp4"):
                rel_path = f"runs/{run_path.name}/renders/{run_path.name}/{rf.name}"
                memory["assets"].append({
                    "asset_id": rf.stem,
                    "asset_type": "video",
                    "path": rel_path,
                    "scene_id": None,
                    "duration": metadata.get("duration", 15.0),
                    "cost": 0.0,
                    "metadata": {"filename": rf.name, "is_final": True}
                })
                # Set final video path (prefer balanced)
                if "balanced" in rf.name or not memory["final_video_path"]:
                    memory["final_video_path"] = rel_path

        # Save memory.json
        with open(memory_path, "w") as f:
            json.dump(memory, f, indent=2)

        print(f"    Created memory.json ({len(memory['assets'])} assets)")
        if memory["final_video_path"]:
            print(f"    Final video: {memory['final_video_path']}")
        synced_count += 1

    print(f"\nSynced {synced_count} run(s)")


if __name__ == "__main__":
    main()
