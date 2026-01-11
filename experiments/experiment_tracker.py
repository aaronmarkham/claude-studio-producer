"""
Experiment Tracking Spreadsheet Generator

Creates a structured Excel workbook for tracking experiments with:
1. Run Log - Basic run information
2. Prompt Evolution - How prompts change
3. Quality Metrics - Scores and QA results  
4. Intent Analysis - Preservation tracking
5. Learnings - What the system learned
6. Summary Dashboard - Key metrics

Also exports CSV versions for easy Pandas analysis.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import json


def create_experiment_workbook(output_path: str = "experiments/experiment_tracker.xlsx"):
    """Create a structured Excel workbook for experiment tracking"""
    
    # Sheet 1: Run Log
    run_log_columns = [
        "run_id",
        "timestamp", 
        "original_concept",
        "provider",
        "budget",
        "duration_target",
        "num_scenes",
        "execution_strategy",  # parallel, sequential, mixed
        "total_cost",
        "total_time_seconds",
        "overall_success",
        "notes"
    ]
    
    # Sheet 2: Prompt Evolution
    prompt_evolution_columns = [
        "run_id",
        "scene_id",
        "scene_order",
        "original_concept",  # User's request
        "scriptwriter_prompt",  # What ScriptWriter generated
        "provider_guidelines_used",  # Yes/No - did it use LTM?
        "guidelines_summary",  # What guidelines were applied
        
        # Prompt metrics
        "word_count",
        "sentence_count",
        "abstract_term_count",
        "concrete_term_count", 
        "vfx_term_count",
        "camera_term_count",
        "achievability_score",
        
        # Changes from previous run (manual or calculated)
        "prompt_simplified",  # Yes/No
        "elements_removed",
        "elements_added",
    ]
    
    # Sheet 3: Quality Metrics
    quality_columns = [
        "run_id",
        "scene_id",
        "video_filename",
        
        # QA Scores
        "qa_overall_score",
        "qa_visual_accuracy",
        "qa_style_consistency",
        "qa_technical_quality",
        "qa_narrative_fit",
        "qa_passed",
        "qa_threshold",
        
        # QA Feedback
        "qa_issues",
        "qa_suggestions",
        
        # Critic Evaluation
        "critic_adherence_score",
        "critic_quality_score",
        "critic_recommendation",
    ]
    
    # Sheet 4: Intent Preservation
    intent_columns = [
        "run_id",
        "scene_id",
        
        # Original intent elements
        "intent_keywords",  # Key words from original concept
        "intent_visual_elements",
        "intent_emotional_tone",
        "intent_narrative_elements",
        
        # Preservation scores (0-100)
        "semantic_preservation",
        "visual_preservation", 
        "emotional_preservation",
        "narrative_preservation",
        "overall_preservation",
        
        # Achievability (0-100)
        "achievability_score",
        
        # Balance
        "balance_score",  # sqrt(preservation * achievability)
        
        # Flags
        "racing_to_bottom",  # Yes/No
        "over_complicated",  # Yes/No
        "good_balance",  # Yes/No
        
        # Lost elements
        "lost_semantic",
        "lost_visual",
        "lost_emotional",
    ]
    
    # Sheet 5: Provider Learnings
    learnings_columns = [
        "run_id",
        "timestamp",
        "provider",
        
        # Learning summary
        "overall_success",
        "adherence_score",
        "quality_score",
        
        # What worked
        "effective_patterns",
        "strengths_observed",
        
        # What didn't work
        "ineffective_patterns",
        "weaknesses_observed",
        
        # Actionable tips
        "prompt_tips",
        "avoid_list",
        
        # Impact tracking
        "learning_applied_in_run",  # Which subsequent run used this?
        "impact_on_quality",  # Did it help?
    ]
    
    # Sheet 6: A/B Comparisons
    comparison_columns = [
        "comparison_id",
        "run_a_id",
        "run_b_id",
        "comparison_date",
        
        # What changed
        "variable_changed",  # e.g., "added provider guidelines"
        "hypothesis",
        
        # Results
        "run_a_avg_score",
        "run_b_avg_score",
        "score_delta",
        
        "run_a_preservation",
        "run_b_preservation",
        "preservation_delta",
        
        "run_a_achievability",
        "run_b_achievability",
        "achievability_delta",
        
        # Conclusion
        "winner",  # A, B, or Tie
        "conclusion",
        "next_experiment",
    ]
    
    # Sheet 7: Summary Dashboard Data
    dashboard_columns = [
        "metric",
        "current_value",
        "previous_value",
        "trend",  # up, down, stable
        "target",
        "status",  # good, warning, bad
    ]
    
    # Create empty DataFrames
    dfs = {
        "Run Log": pd.DataFrame(columns=run_log_columns),
        "Prompt Evolution": pd.DataFrame(columns=prompt_evolution_columns),
        "Quality Metrics": pd.DataFrame(columns=quality_columns),
        "Intent Preservation": pd.DataFrame(columns=intent_columns),
        "Provider Learnings": pd.DataFrame(columns=learnings_columns),
        "A-B Comparisons": pd.DataFrame(columns=comparison_columns),
        "Dashboard": pd.DataFrame(columns=dashboard_columns),
    }
    
    # Add some example/template rows
    dfs["Dashboard"] = pd.DataFrame([
        {"metric": "Avg QA Score", "current_value": "", "previous_value": "", "trend": "", "target": "80+", "status": ""},
        {"metric": "Avg Intent Preservation", "current_value": "", "previous_value": "", "trend": "", "target": "70+", "status": ""},
        {"metric": "Avg Achievability", "current_value": "", "previous_value": "", "trend": "", "target": "70+", "status": ""},
        {"metric": "Balance Score", "current_value": "", "previous_value": "", "trend": "", "target": "65+", "status": ""},
        {"metric": "Racing to Bottom %", "current_value": "", "previous_value": "", "trend": "", "target": "<10%", "status": ""},
        {"metric": "Over-Complicated %", "current_value": "", "previous_value": "", "trend": "", "target": "<10%", "status": ""},
        {"metric": "Learnings Recorded", "current_value": "", "previous_value": "", "trend": "", "target": "n/a", "status": ""},
        {"metric": "Total Runs", "current_value": "", "previous_value": "", "trend": "", "target": "n/a", "status": ""},
    ])
    
    # Write to Excel
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    print(f"Created experiment workbook: {output_path}")
    
    # Also create CSV templates
    csv_dir = output_path.parent / "csv_templates"
    csv_dir.mkdir(exist_ok=True)
    
    for sheet_name, df in dfs.items():
        csv_path = csv_dir / f"{sheet_name.lower().replace(' ', '_').replace('-', '_')}.csv"
        df.to_csv(csv_path, index=False)
    
    print(f"Created CSV templates in: {csv_dir}")
    
    return output_path


def populate_from_artifacts(
    artifacts_dir: str = "artifacts",
    output_path: str = "experiments/experiment_data.xlsx"
) -> str:
    """
    Populate experiment tracker from actual run artifacts.
    This extracts real data from your runs.
    """
    from pathlib import Path
    import json
    
    artifacts = Path(artifacts_dir)
    runs_dir = artifacts / "runs"
    memory_dir = artifacts / "memory"
    
    # Collect data
    run_logs = []
    prompt_evolutions = []
    quality_metrics = []
    intent_preservations = []
    learnings = []
    
    if not runs_dir.exists():
        print(f"No runs directory found at {runs_dir}")
        return None
    
    # Load LTM for learnings
    ltm_path = memory_dir / "long_term.json"
    ltm = {}
    if ltm_path.exists():
        with open(ltm_path) as f:
            ltm = json.load(f)
    
    # Process each run
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        
        run_id = run_dir.name
        
        # Load metadata
        metadata_path = run_dir / "metadata.json"
        metadata = {}
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
        
        # Load memory
        memory_path = run_dir / "memory.json"
        memory = {}
        if memory_path.exists():
            with open(memory_path) as f:
                memory = json.load(f)
        
        # Run log entry
        run_logs.append({
            "run_id": run_id,
            "timestamp": metadata.get("started_at", ""),
            "original_concept": metadata.get("concept", "")[:200],
            "provider": metadata.get("provider", ""),
            "budget": metadata.get("budget", 0),
            "duration_target": metadata.get("duration", 0),
            "num_scenes": len(metadata.get("scenes", [])),
            "execution_strategy": metadata.get("execution_strategy", "unknown"),
            "total_cost": metadata.get("total_cost", 0),
            "total_time_seconds": metadata.get("duration_seconds", 0),
            "overall_success": metadata.get("status") == "completed",
            "notes": ""
        })
        
        # Process scenes
        scenes_dir = run_dir / "scenes"
        if scenes_dir.exists():
            for i, scene_file in enumerate(sorted(scenes_dir.glob("*.json"))):
                with open(scene_file) as f:
                    scene = json.load(f)
                
                scene_id = scene.get("scene_id", f"scene_{i}")
                description = scene.get("description", "")
                concept = metadata.get("concept", "")
                
                # Prompt evolution
                prompt_evolutions.append({
                    "run_id": run_id,
                    "scene_id": scene_id,
                    "scene_order": i + 1,
                    "original_concept": concept[:200],
                    "scriptwriter_prompt": description[:300],
                    "provider_guidelines_used": "Unknown",
                    "guidelines_summary": "",
                    "word_count": len(description.split()),
                    "sentence_count": len([s for s in description.split('.') if s.strip()]),
                    "abstract_term_count": _count_abstract_terms(description),
                    "concrete_term_count": _count_concrete_terms(description),
                    "vfx_term_count": _count_vfx_terms(description),
                    "camera_term_count": _count_camera_terms(description),
                    "achievability_score": _calculate_achievability(description),
                    "prompt_simplified": "",
                    "elements_removed": "",
                    "elements_added": "",
                })
                
                # Intent preservation (basic calculation)
                intent_result = _analyze_intent_basic(concept, description)
                intent_preservations.append({
                    "run_id": run_id,
                    "scene_id": scene_id,
                    **intent_result
                })
        
        # Quality metrics from memory
        for asset in memory.get("assets", []):
            if asset.get("type") == "video":
                qa_meta = asset.get("metadata", {})
                quality_metrics.append({
                    "run_id": run_id,
                    "scene_id": asset.get("scene_id", ""),
                    "video_filename": Path(asset.get("path", "")).name,
                    "qa_overall_score": qa_meta.get("qa_score", 0),
                    "qa_visual_accuracy": qa_meta.get("visual_accuracy", 0),
                    "qa_style_consistency": qa_meta.get("style_consistency", 0),
                    "qa_technical_quality": qa_meta.get("technical_quality", 0),
                    "qa_narrative_fit": qa_meta.get("narrative_fit", 0),
                    "qa_passed": qa_meta.get("passed", False),
                    "qa_threshold": qa_meta.get("threshold", 80),
                    "qa_issues": "; ".join(qa_meta.get("issues", [])[:3]),
                    "qa_suggestions": "; ".join(qa_meta.get("suggestions", [])[:2]),
                    "critic_adherence_score": "",
                    "critic_quality_score": "",
                    "critic_recommendation": "",
                })
    
    # Extract learnings from LTM
    for provider, knowledge in ltm.get("provider_knowledge", {}).items():
        for learning in knowledge.get("recent_learnings", []):
            learnings.append({
                "run_id": learning.get("run_id", ""),
                "timestamp": learning.get("timestamp", ""),
                "provider": provider,
                "overall_success": learning.get("overall_success", False),
                "adherence_score": learning.get("adherence_score", 0),
                "quality_score": learning.get("quality_score", 0),
                "effective_patterns": "; ".join(learning.get("effective_patterns", [])[:3]),
                "strengths_observed": "; ".join(learning.get("strengths_observed", [])[:3]),
                "ineffective_patterns": "; ".join(learning.get("ineffective_patterns", [])[:3]),
                "weaknesses_observed": "; ".join(learning.get("weaknesses_observed", [])[:3]),
                "prompt_tips": "; ".join(learning.get("prompt_tips", [])[:3]),
                "avoid_list": "; ".join(learning.get("avoid_list", [])[:3]),
                "learning_applied_in_run": "",
                "impact_on_quality": "",
            })
    
    # Create DataFrames
    dfs = {
        "Run Log": pd.DataFrame(run_logs) if run_logs else pd.DataFrame(),
        "Prompt Evolution": pd.DataFrame(prompt_evolutions) if prompt_evolutions else pd.DataFrame(),
        "Quality Metrics": pd.DataFrame(quality_metrics) if quality_metrics else pd.DataFrame(),
        "Intent Preservation": pd.DataFrame(intent_preservations) if intent_preservations else pd.DataFrame(),
        "Provider Learnings": pd.DataFrame(learnings) if learnings else pd.DataFrame(),
    }
    
    # Calculate dashboard metrics
    dashboard_data = _calculate_dashboard_metrics(dfs)
    dfs["Dashboard"] = pd.DataFrame(dashboard_data)
    
    # Add empty A/B comparison sheet
    dfs["A-B Comparisons"] = pd.DataFrame(columns=[
        "comparison_id", "run_a_id", "run_b_id", "comparison_date",
        "variable_changed", "hypothesis", "run_a_avg_score", "run_b_avg_score",
        "score_delta", "conclusion"
    ])
    
    # Write to Excel
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    print(f"Populated experiment data: {output_path}")
    print(f"  - {len(run_logs)} runs")
    print(f"  - {len(prompt_evolutions)} scenes")
    print(f"  - {len(quality_metrics)} quality records")
    print(f"  - {len(learnings)} learnings")
    
    return str(output_path)


# Helper functions for analysis
def _count_abstract_terms(text: str) -> int:
    terms = ["visualization", "represents", "symbolizes", "abstract", "concept",
             "metaphor", "essence", "embodies", "journey", "narrative"]
    return sum(1 for t in terms if t in text.lower())

def _count_concrete_terms(text: str) -> int:
    terms = ["desk", "laptop", "keyboard", "screen", "hand", "face", "person",
             "room", "chair", "coffee", "window", "light", "lamp"]
    return sum(1 for t in terms if t in text.lower())

def _count_vfx_terms(text: str) -> int:
    terms = ["glowing", "transform", "magical", "sparkle", "particle",
             "floating", "dissolve", "morph", "shimmer", "pulse"]
    return sum(1 for t in terms if t in text.lower())

def _count_camera_terms(text: str) -> int:
    terms = ["close-up", "wide shot", "tracking", "pan", "zoom", "dolly",
             "cinematic", "shallow depth", "lens", "angle"]
    return sum(1 for t in terms if t in text.lower())

def _calculate_achievability(prompt: str) -> float:
    score = 50
    score += _count_concrete_terms(prompt) * 5
    score += _count_camera_terms(prompt) * 3
    score -= _count_abstract_terms(prompt) * 8
    score -= _count_vfx_terms(prompt) * 10
    if len(prompt.split()) > 50:
        score -= (len(prompt.split()) - 50) * 0.5
    return max(0, min(100, score))

def _analyze_intent_basic(concept: str, prompt: str) -> Dict:
    """Basic intent preservation analysis"""
    # Extract keywords from concept
    stop_words = {"a", "an", "the", "is", "are", "to", "of", "in", "for", "on", "with", "and", "or"}
    concept_words = set(w.lower().strip('.,!?') for w in concept.split() if w.lower() not in stop_words and len(w) > 2)
    prompt_lower = prompt.lower()
    
    preserved = [w for w in concept_words if w in prompt_lower]
    lost = [w for w in concept_words if w not in prompt_lower]
    
    preservation = len(preserved) / len(concept_words) * 100 if concept_words else 100
    achievability = _calculate_achievability(prompt)
    balance = (preservation * achievability) ** 0.5
    
    return {
        "intent_keywords": ", ".join(list(concept_words)[:10]),
        "intent_visual_elements": "",
        "intent_emotional_tone": "",
        "intent_narrative_elements": "",
        "semantic_preservation": preservation,
        "visual_preservation": "",
        "emotional_preservation": "",
        "narrative_preservation": "",
        "overall_preservation": preservation,
        "achievability_score": achievability,
        "balance_score": balance,
        "racing_to_bottom": "Yes" if preservation < 40 and achievability > 80 else "No",
        "over_complicated": "Yes" if preservation > 80 and achievability < 40 else "No",
        "good_balance": "Yes" if preservation > 60 and achievability > 60 else "No",
        "lost_semantic": ", ".join(lost[:5]),
        "lost_visual": "",
        "lost_emotional": "",
    }

def _calculate_dashboard_metrics(dfs: Dict[str, pd.DataFrame]) -> List[Dict]:
    """Calculate summary metrics for dashboard"""
    metrics = []
    
    # Avg QA Score
    if not dfs["Quality Metrics"].empty and "qa_overall_score" in dfs["Quality Metrics"].columns:
        avg_qa = dfs["Quality Metrics"]["qa_overall_score"].mean()
        metrics.append({
            "metric": "Avg QA Score",
            "current_value": f"{avg_qa:.1f}",
            "previous_value": "",
            "trend": "",
            "target": "80+",
            "status": "good" if avg_qa >= 80 else "warning" if avg_qa >= 60 else "bad"
        })
    
    # Avg Intent Preservation
    if not dfs["Intent Preservation"].empty and "overall_preservation" in dfs["Intent Preservation"].columns:
        avg_pres = dfs["Intent Preservation"]["overall_preservation"].mean()
        metrics.append({
            "metric": "Avg Intent Preservation",
            "current_value": f"{avg_pres:.1f}%",
            "previous_value": "",
            "trend": "",
            "target": "70+",
            "status": "good" if avg_pres >= 70 else "warning" if avg_pres >= 50 else "bad"
        })
    
    # Racing to Bottom %
    if not dfs["Intent Preservation"].empty and "racing_to_bottom" in dfs["Intent Preservation"].columns:
        rtb_pct = (dfs["Intent Preservation"]["racing_to_bottom"] == "Yes").mean() * 100
        metrics.append({
            "metric": "Racing to Bottom %",
            "current_value": f"{rtb_pct:.1f}%",
            "previous_value": "",
            "trend": "",
            "target": "<10%",
            "status": "good" if rtb_pct < 10 else "warning" if rtb_pct < 25 else "bad"
        })
    
    # Total Runs
    if not dfs["Run Log"].empty:
        metrics.append({
            "metric": "Total Runs",
            "current_value": str(len(dfs["Run Log"])),
            "previous_value": "",
            "trend": "",
            "target": "n/a",
            "status": ""
        })
    
    # Total Learnings
    if not dfs["Provider Learnings"].empty:
        metrics.append({
            "metric": "Learnings Recorded",
            "current_value": str(len(dfs["Provider Learnings"])),
            "previous_value": "",
            "trend": "",
            "target": "n/a",
            "status": ""
        })
    
    return metrics


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--populate":
        # Populate from real data
        artifacts_dir = sys.argv[2] if len(sys.argv) > 2 else "artifacts"
        populate_from_artifacts(artifacts_dir)
    else:
        # Create empty template
        create_experiment_workbook()
        print("\nTo populate with real data, run:")
        print("  python experiment_tracker.py --populate [artifacts_dir]")
