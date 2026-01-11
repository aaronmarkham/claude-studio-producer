"""
Claude Studio Producer - Experimentation & Analysis Framework

This module provides tools for analyzing the learning feedback loop:
1. How prompts evolve based on critic feedback
2. Whether quality improves over runs
3. Whether we're "racing to the bottom" (over-simplifying prompts)
4. Intent preservation vs. achievability tradeoffs

Usage:
    python -m experiments.analyze_runs
    python -m experiments.compare_prompts
    python -m experiments.intent_drift_analysis
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class PromptEvolution:
    """Tracks how a prompt concept evolved across runs"""
    run_id: str
    timestamp: datetime
    original_concept: str  # User's original request
    generated_prompt: str  # What ScriptWriter produced
    provider: str
    
    # Quality metrics
    qa_score: float
    adherence_score: float
    
    # Complexity metrics
    prompt_word_count: int
    prompt_sentence_count: int
    abstract_term_count: int  # Terms like "visualization", "represents"
    concrete_term_count: int  # Terms like "desk", "laptop", "hand"
    vfx_term_count: int  # Terms like "glowing", "transform", "magical"
    
    # Intent metrics
    intent_keywords: List[str]  # Key concepts from original
    preserved_keywords: List[str]  # Which keywords made it to prompt
    intent_preservation_score: float  # % of intent preserved
    
    # Critic feedback
    effective_patterns: List[str]
    ineffective_patterns: List[str]
    suggestions: List[str]


@dataclass
class RunComparison:
    """Compares two runs for A/B analysis"""
    run_a_id: str
    run_b_id: str
    
    # What changed
    prompt_changes: List[str]
    guideline_changes: List[str]
    
    # Results
    score_delta: float  # B - A
    adherence_delta: float
    complexity_delta: float
    intent_preservation_delta: float
    
    # Assessment
    improvement_type: str  # "quality_up", "quality_down", "tradeoff", "no_change"
    notes: str


# ============================================================================
# DATA EXTRACTION
# ============================================================================

class RunDataExtractor:
    """Extracts structured data from run artifacts"""
    
    def __init__(self, artifacts_dir: str = "artifacts"):
        self.artifacts_dir = Path(artifacts_dir)
        self.runs_dir = self.artifacts_dir / "runs"
        self.memory_dir = self.artifacts_dir / "memory"
    
    def get_all_runs(self) -> List[str]:
        """Get all run IDs"""
        if not self.runs_dir.exists():
            return []
        return sorted([d.name for d in self.runs_dir.iterdir() if d.is_dir()])
    
    def load_run(self, run_id: str) -> Dict[str, Any]:
        """Load all data for a run"""
        run_dir = self.runs_dir / run_id
        
        data = {
            "run_id": run_id,
            "metadata": self._load_json(run_dir / "metadata.json"),
            "memory": self._load_json(run_dir / "memory.json"),
            "scenes": self._load_scenes(run_dir / "scenes"),
        }
        
        return data
    
    def load_long_term_memory(self) -> Dict[str, Any]:
        """Load LTM data"""
        return self._load_json(self.memory_dir / "long_term.json")
    
    def _load_json(self, path: Path) -> Optional[Dict]:
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None
    
    def _load_scenes(self, scenes_dir: Path) -> List[Dict]:
        scenes = []
        if scenes_dir.exists():
            for scene_file in sorted(scenes_dir.glob("*.json")):
                with open(scene_file) as f:
                    scenes.append(json.load(f))
        return scenes


# ============================================================================
# PROMPT ANALYSIS
# ============================================================================

class PromptAnalyzer:
    """Analyzes prompt complexity and content"""
    
    # Term categories for classification
    ABSTRACT_TERMS = [
        "visualization", "represents", "symbolizes", "abstract", "concept",
        "metaphor", "essence", "embodies", "suggests", "implies", "evokes",
        "transformation", "journey", "narrative", "story"
    ]
    
    CONCRETE_TERMS = [
        "desk", "laptop", "keyboard", "screen", "monitor", "hand", "hands",
        "face", "person", "room", "chair", "table", "cup", "coffee", "window",
        "wall", "floor", "door", "light", "lamp", "cable", "mouse", "phone"
    ]
    
    VFX_TERMS = [
        "glowing", "glow", "transform", "magical", "sparkle", "particle",
        "floating", "dissolve", "morph", "shimmer", "pulse", "animate",
        "effect", "vfx", "cgi", "supernatural", "ethereal", "mystical"
    ]
    
    CAMERA_TERMS = [
        "close-up", "wide shot", "medium shot", "tracking", "pan", "zoom",
        "dolly", "orbit", "aerial", "overhead", "low-angle", "high-angle",
        "shallow depth", "cinematic", "film", "lens"
    ]
    
    def analyze(self, prompt: str) -> Dict[str, Any]:
        """Comprehensive prompt analysis"""
        words = prompt.lower().split()
        sentences = prompt.split('.')
        
        return {
            "word_count": len(words),
            "sentence_count": len([s for s in sentences if s.strip()]),
            "char_count": len(prompt),
            
            # Term counts
            "abstract_terms": self._count_terms(prompt, self.ABSTRACT_TERMS),
            "concrete_terms": self._count_terms(prompt, self.CONCRETE_TERMS),
            "vfx_terms": self._count_terms(prompt, self.VFX_TERMS),
            "camera_terms": self._count_terms(prompt, self.CAMERA_TERMS),
            
            # Ratios
            "concrete_ratio": self._term_ratio(prompt, self.CONCRETE_TERMS, self.ABSTRACT_TERMS),
            "achievability_score": self._achievability_score(prompt),
            
            # Found terms
            "abstract_found": self._find_terms(prompt, self.ABSTRACT_TERMS),
            "concrete_found": self._find_terms(prompt, self.CONCRETE_TERMS),
            "vfx_found": self._find_terms(prompt, self.VFX_TERMS),
        }
    
    def _count_terms(self, text: str, terms: List[str]) -> int:
        text_lower = text.lower()
        return sum(1 for term in terms if term in text_lower)
    
    def _find_terms(self, text: str, terms: List[str]) -> List[str]:
        text_lower = text.lower()
        return [term for term in terms if term in text_lower]
    
    def _term_ratio(self, text: str, numerator_terms: List[str], denominator_terms: List[str]) -> float:
        num = self._count_terms(text, numerator_terms)
        denom = self._count_terms(text, denominator_terms)
        if denom == 0:
            return float('inf') if num > 0 else 1.0
        return num / denom
    
    def _achievability_score(self, prompt: str) -> float:
        """
        Score 0-100 for how achievable the prompt is for AI video.
        Higher = more achievable (concrete, simple).
        Lower = less achievable (abstract, VFX-heavy).
        """
        analysis = {
            "concrete": self._count_terms(prompt, self.CONCRETE_TERMS),
            "abstract": self._count_terms(prompt, self.ABSTRACT_TERMS),
            "vfx": self._count_terms(prompt, self.VFX_TERMS),
            "camera": self._count_terms(prompt, self.CAMERA_TERMS),
        }
        
        # Scoring formula
        score = 50  # Base
        score += analysis["concrete"] * 5  # Concrete is good
        score += analysis["camera"] * 3   # Camera terms help
        score -= analysis["abstract"] * 8  # Abstract is bad
        score -= analysis["vfx"] * 10      # VFX is very bad
        
        # Word count penalty (too long = confusing)
        word_count = len(prompt.split())
        if word_count > 50:
            score -= (word_count - 50) * 0.5
        
        return max(0, min(100, score))


# ============================================================================
# INTENT ANALYSIS
# ============================================================================

class IntentAnalyzer:
    """Analyzes intent preservation across prompt transformations"""
    
    def extract_intent_keywords(self, concept: str) -> List[str]:
        """Extract key intent-bearing words from original concept"""
        # Remove common words
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "dare",
            "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
            "from", "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "under", "again", "further", "then", "once", "and",
            "but", "or", "nor", "so", "yet", "both", "either", "neither", "not",
            "only", "own", "same", "than", "too", "very", "just", "also"
        }
        
        words = concept.lower().split()
        keywords = [w.strip('.,!?";:') for w in words if w.lower() not in stop_words]
        return [k for k in keywords if len(k) > 2]
    
    def calculate_preservation(self, original_concept: str, generated_prompt: str) -> Dict[str, Any]:
        """Calculate how much of the original intent is preserved"""
        intent_keywords = self.extract_intent_keywords(original_concept)
        prompt_lower = generated_prompt.lower()
        
        preserved = [k for k in intent_keywords if k in prompt_lower]
        lost = [k for k in intent_keywords if k not in prompt_lower]
        
        preservation_score = len(preserved) / len(intent_keywords) * 100 if intent_keywords else 100
        
        return {
            "intent_keywords": intent_keywords,
            "preserved_keywords": preserved,
            "lost_keywords": lost,
            "preservation_score": preservation_score,
            "preservation_ratio": f"{len(preserved)}/{len(intent_keywords)}"
        }
    
    def detect_intent_drift(self, runs: List[Dict]) -> pd.DataFrame:
        """
        Detect if intent is drifting across runs.
        Returns DataFrame showing intent preservation over time.
        """
        records = []
        
        for run in runs:
            if not run.get("metadata"):
                continue
                
            concept = run["metadata"].get("concept", "")
            
            for scene in run.get("scenes", []):
                prompt = scene.get("description", "")
                analysis = self.calculate_preservation(concept, prompt)
                
                records.append({
                    "run_id": run["run_id"],
                    "scene_id": scene.get("scene_id"),
                    "preservation_score": analysis["preservation_score"],
                    "keywords_total": len(analysis["intent_keywords"]),
                    "keywords_preserved": len(analysis["preserved_keywords"]),
                    "keywords_lost": len(analysis["lost_keywords"]),
                    "lost_keywords": ", ".join(analysis["lost_keywords"][:5])
                })
        
        return pd.DataFrame(records)


# ============================================================================
# LEARNING LOOP ANALYSIS
# ============================================================================

class LearningLoopAnalyzer:
    """Analyzes the effectiveness of the learning feedback loop"""
    
    def __init__(self, extractor: RunDataExtractor):
        self.extractor = extractor
        self.prompt_analyzer = PromptAnalyzer()
        self.intent_analyzer = IntentAnalyzer()
    
    def build_evolution_dataframe(self) -> pd.DataFrame:
        """Build DataFrame tracking prompt evolution across runs"""
        records = []
        
        for run_id in self.extractor.get_all_runs():
            run = self.extractor.load_run(run_id)
            
            if not run.get("metadata"):
                continue
            
            metadata = run["metadata"]
            memory = run.get("memory", {})
            
            for scene in run.get("scenes", []):
                prompt = scene.get("description", "")
                prompt_analysis = self.prompt_analyzer.analyze(prompt)
                
                # Get QA results from memory if available
                qa_score = 0
                assets = memory.get("assets", []) if memory else []
                for asset in assets:
                    if asset.get("scene_id") == scene.get("scene_id"):
                        qa_meta = asset.get("metadata", {})
                        qa_score = qa_meta.get("qa_score", 0)
                        break
                
                records.append({
                    "run_id": run_id,
                    "timestamp": metadata.get("started_at"),
                    "scene_id": scene.get("scene_id"),
                    "concept": metadata.get("concept", "")[:100],
                    "prompt": prompt[:200],
                    "provider": metadata.get("provider", "unknown"),
                    
                    # Quality
                    "qa_score": qa_score,
                    
                    # Prompt metrics
                    "word_count": prompt_analysis["word_count"],
                    "sentence_count": prompt_analysis["sentence_count"],
                    "abstract_terms": prompt_analysis["abstract_terms"],
                    "concrete_terms": prompt_analysis["concrete_terms"],
                    "vfx_terms": prompt_analysis["vfx_terms"],
                    "camera_terms": prompt_analysis["camera_terms"],
                    "concrete_ratio": prompt_analysis["concrete_ratio"],
                    "achievability_score": prompt_analysis["achievability_score"],
                })
        
        df = pd.DataFrame(records)
        if not df.empty and "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")
        
        return df
    
    def build_learning_dataframe(self) -> pd.DataFrame:
        """Build DataFrame from LTM provider learnings"""
        ltm = self.extractor.load_long_term_memory()
        
        if not ltm:
            return pd.DataFrame()
        
        records = []
        
        provider_knowledge = ltm.get("provider_knowledge", {})
        for provider, knowledge in provider_knowledge.items():
            for learning in knowledge.get("recent_learnings", []):
                records.append({
                    "provider": provider,
                    "run_id": learning.get("run_id"),
                    "timestamp": learning.get("timestamp"),
                    "overall_success": learning.get("overall_success"),
                    "adherence_score": learning.get("adherence_score"),
                    "quality_score": learning.get("quality_score"),
                    "effective_patterns_count": len(learning.get("effective_patterns", [])),
                    "ineffective_patterns_count": len(learning.get("ineffective_patterns", [])),
                    "prompt_tips_count": len(learning.get("prompt_tips", [])),
                })
        
        df = pd.DataFrame(records)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")
        
        return df
    
    def analyze_quality_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze if quality is improving over time"""
        if df.empty or "qa_score" not in df.columns:
            return {"trend": "insufficient_data"}
        
        df_sorted = df.sort_values("timestamp")
        scores = df_sorted["qa_score"].dropna()
        
        if len(scores) < 3:
            return {"trend": "insufficient_data", "scores": scores.tolist()}
        
        # Calculate trend
        x = np.arange(len(scores))
        slope, intercept = np.polyfit(x, scores.values, 1)
        
        # Rolling average
        rolling_avg = scores.rolling(window=3, min_periods=1).mean()
        
        return {
            "trend": "improving" if slope > 0.5 else "declining" if slope < -0.5 else "stable",
            "slope": slope,
            "first_3_avg": scores.head(3).mean(),
            "last_3_avg": scores.tail(3).mean(),
            "overall_avg": scores.mean(),
            "scores": scores.tolist(),
            "rolling_avg": rolling_avg.tolist()
        }
    
    def analyze_complexity_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze if prompts are getting simpler (racing to bottom)"""
        if df.empty:
            return {"trend": "insufficient_data"}
        
        df_sorted = df.sort_values("timestamp")
        
        metrics = {
            "word_count": df_sorted["word_count"].tolist(),
            "achievability_score": df_sorted["achievability_score"].tolist(),
            "abstract_terms": df_sorted["abstract_terms"].tolist(),
            "vfx_terms": df_sorted["vfx_terms"].tolist(),
        }
        
        # Check for "racing to bottom"
        # Signs: increasing achievability, decreasing word count, decreasing abstract terms
        achievability_trend = np.polyfit(range(len(metrics["achievability_score"])), 
                                          metrics["achievability_score"], 1)[0] if len(metrics["achievability_score"]) > 1 else 0
        word_trend = np.polyfit(range(len(metrics["word_count"])), 
                                 metrics["word_count"], 1)[0] if len(metrics["word_count"]) > 1 else 0
        
        racing_to_bottom = achievability_trend > 2 and word_trend < -1
        
        return {
            "racing_to_bottom": racing_to_bottom,
            "achievability_trend": achievability_trend,
            "word_count_trend": word_trend,
            "metrics": metrics
        }


# ============================================================================
# REPORTS
# ============================================================================

class ExperimentReporter:
    """Generates analysis reports"""
    
    def __init__(self, analyzer: LearningLoopAnalyzer):
        self.analyzer = analyzer
    
    def generate_summary_report(self) -> str:
        """Generate text summary of learning loop effectiveness"""
        evolution_df = self.analyzer.build_evolution_dataframe()
        learning_df = self.analyzer.build_learning_dataframe()
        
        quality_analysis = self.analyzer.analyze_quality_trend(evolution_df)
        complexity_analysis = self.analyzer.analyze_complexity_trend(evolution_df)
        
        report = []
        report.append("=" * 60)
        report.append("CLAUDE STUDIO PRODUCER - LEARNING LOOP ANALYSIS")
        report.append("=" * 60)
        report.append("")
        
        # Overview
        report.append("📊 OVERVIEW")
        report.append(f"   Total runs analyzed: {len(evolution_df['run_id'].unique()) if not evolution_df.empty else 0}")
        report.append(f"   Total scenes: {len(evolution_df) if not evolution_df.empty else 0}")
        report.append(f"   Provider learnings recorded: {len(learning_df) if not learning_df.empty else 0}")
        report.append("")
        
        # Quality Trend
        report.append("📈 QUALITY TREND")
        report.append(f"   Trend: {quality_analysis.get('trend', 'unknown').upper()}")
        if "first_3_avg" in quality_analysis:
            report.append(f"   First 3 runs avg: {quality_analysis['first_3_avg']:.1f}")
            report.append(f"   Last 3 runs avg: {quality_analysis['last_3_avg']:.1f}")
            report.append(f"   Overall avg: {quality_analysis['overall_avg']:.1f}")
        report.append("")
        
        # Complexity / Racing to Bottom
        report.append("⚠️  COMPLEXITY ANALYSIS (Racing to Bottom Check)")
        report.append(f"   Racing to bottom: {'YES ⚠️' if complexity_analysis.get('racing_to_bottom') else 'NO ✓'}")
        report.append(f"   Achievability trend: {complexity_analysis.get('achievability_trend', 0):.2f}/run")
        report.append(f"   Word count trend: {complexity_analysis.get('word_count_trend', 0):.2f}/run")
        report.append("")
        
        # Learning Stats
        if not learning_df.empty:
            report.append("🧠 LEARNING STATISTICS")
            for provider in learning_df["provider"].unique():
                prov_df = learning_df[learning_df["provider"] == provider]
                report.append(f"   {provider}:")
                report.append(f"      Learnings recorded: {len(prov_df)}")
                report.append(f"      Avg adherence: {prov_df['adherence_score'].mean():.1f}")
                report.append(f"      Success rate: {prov_df['overall_success'].mean()*100:.0f}%")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def generate_csv_export(self, output_dir: str = "experiments/data"):
        """Export DataFrames to CSV for external analysis"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        evolution_df = self.analyzer.build_evolution_dataframe()
        learning_df = self.analyzer.build_learning_dataframe()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if not evolution_df.empty:
            evolution_df.to_csv(output_path / f"prompt_evolution_{timestamp}.csv", index=False)
        
        if not learning_df.empty:
            learning_df.to_csv(output_path / f"provider_learnings_{timestamp}.csv", index=False)
        
        print(f"Exported to {output_path}")
    
    def plot_quality_over_time(self, save_path: Optional[str] = None):
        """Plot quality scores over time"""
        evolution_df = self.analyzer.build_evolution_dataframe()
        
        if evolution_df.empty:
            print("No data to plot")
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # QA Score over time
        ax1 = axes[0, 0]
        if "qa_score" in evolution_df.columns:
            evolution_df.plot(x="timestamp", y="qa_score", ax=ax1, marker='o')
            ax1.axhline(y=80, color='g', linestyle='--', label='Pass threshold')
            ax1.set_title("QA Score Over Time")
            ax1.set_ylabel("Score")
            ax1.legend()
        
        # Achievability Score
        ax2 = axes[0, 1]
        evolution_df.plot(x="timestamp", y="achievability_score", ax=ax2, marker='s', color='orange')
        ax2.set_title("Prompt Achievability Over Time")
        ax2.set_ylabel("Achievability Score")
        
        # Word Count
        ax3 = axes[1, 0]
        evolution_df.plot(x="timestamp", y="word_count", ax=ax3, marker='^', color='purple')
        ax3.set_title("Prompt Complexity (Word Count)")
        ax3.set_ylabel("Words")
        
        # Term Distribution
        ax4 = axes[1, 1]
        term_cols = ["concrete_terms", "abstract_terms", "vfx_terms"]
        if all(c in evolution_df.columns for c in term_cols):
            evolution_df.plot(x="timestamp", y=term_cols, ax=ax4, marker='o')
            ax4.set_title("Term Types Over Time")
            ax4.set_ylabel("Count")
            ax4.legend()
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path)
            print(f"Saved plot to {save_path}")
        else:
            plt.show()


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Main entry point for analysis"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze Claude Studio Producer learning loop")
    parser.add_argument("--report", action="store_true", help="Generate summary report")
    parser.add_argument("--export", action="store_true", help="Export data to CSV")
    parser.add_argument("--plot", action="store_true", help="Generate plots")
    parser.add_argument("--output", type=str, default="experiments/output", help="Output directory")
    parser.add_argument("--artifacts", type=str, default="artifacts", help="Artifacts directory")
    
    args = parser.parse_args()
    
    # Initialize
    extractor = RunDataExtractor(args.artifacts)
    analyzer = LearningLoopAnalyzer(extractor)
    reporter = ExperimentReporter(analyzer)
    
    # Run analyses
    if args.report:
        print(reporter.generate_summary_report())
    
    if args.export:
        reporter.generate_csv_export(args.output)
    
    if args.plot:
        Path(args.output).mkdir(parents=True, exist_ok=True)
        reporter.plot_quality_over_time(f"{args.output}/quality_over_time.png")
    
    if not any([args.report, args.export, args.plot]):
        # Default: show report
        print(reporter.generate_summary_report())


if __name__ == "__main__":
    main()
