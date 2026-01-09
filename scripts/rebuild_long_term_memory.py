#!/usr/bin/env python3
"""
Rebuild long-term memory from all migrated runs.

Scans all memory.json files and rebuilds the long_term.json with
production history and statistics.
"""

import json
from pathlib import Path
from datetime import datetime


def main():
    """Rebuild long-term memory from all runs"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    runs_dir = project_root / "artifacts" / "runs"
    memory_dir = project_root / "artifacts" / "memory"
    long_term_path = memory_dir / "long_term.json"

    memory_dir.mkdir(parents=True, exist_ok=True)

    # Load existing long-term memory for preferences
    existing_ltm = {}
    if long_term_path.exists():
        try:
            with open(long_term_path, "r") as f:
                existing_ltm = json.load(f)
        except Exception:
            pass

    # Preserve user preferences
    preferences = existing_ltm.get("preferences", {
        "preferred_style": "balanced",
        "preferred_tier": None,
        "default_voice": "nova",
        "default_voice_speed": 1.0,
        "default_music_mood": "ambient",
        "default_audio_tier": "SIMPLE_OVERLAY",
        "brand_colors": [],
        "quality_threshold": 75,
        "max_budget_per_run": None
    })

    # Scan all runs
    production_history = []
    total_spent = 0.0
    tier_counts = {}

    print(f"Scanning {runs_dir} for memory.json files...\n")

    for run_path in sorted(runs_dir.iterdir()):
        if not run_path.is_dir():
            continue

        memory_path = run_path / "memory.json"
        if not memory_path.exists():
            continue

        try:
            with open(memory_path, "r") as f:
                memory = json.load(f)
        except Exception as e:
            print(f"  Error reading {run_path.name}: {e}")
            continue

        # Extract record
        run_id = memory.get("run_id", run_path.name)
        concept = memory.get("concept", "Unknown")
        status = memory.get("current_stage", "unknown")
        budget_spent = memory.get("budget_spent", 0)

        # Get winning tier
        winning_tier = None
        pilots = memory.get("pilots", [])
        winning_pilot_id = memory.get("winning_pilot_id")
        for pilot in pilots:
            if pilot.get("pilot_id") == winning_pilot_id:
                winning_tier = pilot.get("tier")
                break

        # Get timestamps
        started_at = memory.get("started_at")
        completed_at = memory.get("completed_at")

        # Calculate duration
        duration_seconds = 0
        if started_at and completed_at:
            try:
                start = datetime.fromisoformat(started_at)
                end = datetime.fromisoformat(completed_at)
                duration_seconds = (end - start).total_seconds()
            except Exception:
                pass

        # Get quality score from pilot
        final_score = None
        for pilot in pilots:
            if pilot.get("quality_score"):
                final_score = pilot.get("quality_score")
                break

        record = {
            "run_id": run_id,
            "concept": concept,
            "timestamp": completed_at or started_at,
            "status": status,
            "winning_tier": winning_tier,
            "final_score": final_score,
            "total_cost": budget_spent,
            "duration_seconds": duration_seconds,
            "scenes_count": memory.get("total_scenes", 0),
            "edit_style_used": "safe",
            "user_rating": None,
            "user_notes": None,
            "final_video_path": None,
            "edl_path": None
        }

        production_history.append(record)
        total_spent += budget_spent

        if winning_tier:
            tier_counts[winning_tier] = tier_counts.get(winning_tier, 0) + 1

        print(f"  Added {run_id}: {concept[:40]}... (${budget_spent:.2f})")

    # Sort by timestamp (newest first)
    production_history.sort(
        key=lambda x: x.get("timestamp") or "",
        reverse=True
    )

    # Build long-term memory
    long_term = {
        "preferences": preferences,
        "total_runs": len(production_history),
        "total_spent": total_spent,
        "production_history": production_history,
        "patterns": {},
        "saved_assets": [],
        "brand_assets": [],
        "updated_at": datetime.utcnow().isoformat()
    }

    # Write long-term memory
    with open(long_term_path, "w") as f:
        json.dump(long_term, f, indent=2)

    print(f"\nRebuilt long-term memory:")
    print(f"  Total runs: {len(production_history)}")
    print(f"  Total spent: ${total_spent:.2f}")
    print(f"  Tier distribution: {tier_counts}")
    print(f"  Saved to: {long_term_path}")


if __name__ == "__main__":
    main()
