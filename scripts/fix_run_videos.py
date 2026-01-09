#!/usr/bin/env python3
"""
Fix run memory files to properly reference downloaded videos.

Scans each run directory for video files and updates the memory.json
to include proper asset references.
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def main():
    """Fix video paths in run memory files"""
    # Check for --force flag
    force = "--force" in sys.argv

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    runs_dir = project_root / "artifacts" / "runs"

    print(f"Scanning {runs_dir} for runs with videos...\n")

    fixed_count = 0

    for run_path in sorted(runs_dir.iterdir()):
        if not run_path.is_dir():
            continue

        # Check for videos
        videos_dir = run_path / "videos"
        renders_dir = run_path / "renders" / run_path.name

        video_files = []
        final_video = None

        # Look for scene videos
        if videos_dir.exists():
            video_files.extend(list(videos_dir.glob("*.mp4")))

        # Look for final rendered videos
        if renders_dir.exists():
            for render in renders_dir.glob("*_final.mp4"):
                video_files.append(render)
                if "balanced" in render.name:
                    final_video = render
            if not final_video:
                finals = list(renders_dir.glob("*_final.mp4"))
                if finals:
                    final_video = finals[0]

        if not video_files:
            continue

        print(f"  {run_path.name}:")
        print(f"    Videos found: {len(video_files)}")

        # Load memory.json
        memory_path = run_path / "memory.json"
        if not memory_path.exists():
            print(f"    No memory.json - skipping")
            continue

        try:
            with open(memory_path, "r") as f:
                memory = json.load(f)
        except Exception as e:
            print(f"    Error reading memory.json: {e}")
            continue

        # Check if assets already exist (clear if force mode)
        existing_assets = memory.get("assets", [])
        if force:
            # Remove video assets to rebuild them
            existing_assets = [a for a in existing_assets if a.get("asset_type") != "video"]
        existing_video_paths = {a.get("path", "") for a in existing_assets if a.get("asset_type") == "video"}

        # Build new asset entries
        new_assets = []
        for vf in video_files:
            # Make path relative to artifacts/ with forward slashes for web URLs
            rel_path = str(vf.relative_to(project_root / "artifacts")).replace("\\", "/")

            if rel_path in existing_video_paths:
                continue  # Already exists

            # Determine scene_id from filename
            scene_id = None
            if "scene_" in vf.name:
                # Extract scene ID from filename like scene_1_v0.mp4
                parts = vf.stem.split("_")
                for i, p in enumerate(parts):
                    if p == "scene" and i + 1 < len(parts):
                        scene_id = f"scene_{parts[i+1]}"
                        break

            asset = {
                "asset_id": vf.stem,
                "asset_type": "video",
                "path": rel_path,
                "scene_id": scene_id,
                "duration": 5.0,  # Default
                "cost": 0.40 if "mock" not in memory.get("actual_video_provider", "mock") else 0.0,
                "metadata": {
                    "filename": vf.name,
                    "is_final": "_final" in vf.name
                }
            }
            new_assets.append(asset)
            print(f"      + {rel_path}")

        if not new_assets:
            print(f"    No new assets to add")
            continue

        # Add new assets to memory
        memory["assets"] = existing_assets + new_assets

        # Set final_video_path if we found a final render
        if final_video:
            rel_final = str(final_video.relative_to(project_root / "artifacts")).replace("\\", "/")
            memory["final_video_path"] = rel_final
            print(f"    Final video: {rel_final}")

        # Save updated memory
        with open(memory_path, "w") as f:
            json.dump(memory, f, indent=2)

        fixed_count += 1
        print(f"    Updated memory.json with {len(new_assets)} new asset(s)")

    print(f"\nFixed {fixed_count} run(s)")


if __name__ == "__main__":
    main()
