"""
Intent Preservation Analysis

This module specifically tracks the tension between:
1. Making prompts more "achievable" for AI video models
2. Preserving the user's original creative intent

The "Racing to the Bottom" problem:
- Critic says "VFX doesn't work" → prompt gets simpler
- Prompt gets simpler → more achievable but less expressive
- Eventually prompt is "person sitting at desk" instead of the rich vision

We measure intent along multiple dimensions:
- Semantic Intent: Key concepts and themes
- Visual Intent: Specific visual elements requested
- Emotional Intent: Mood, tone, feeling
- Narrative Intent: Story or message
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from collections import Counter
import re


@dataclass
class IntentDimension:
    """A single dimension of intent"""
    name: str
    original_elements: List[str]
    preserved_elements: List[str]
    lost_elements: List[str]
    added_elements: List[str]  # New things not in original
    preservation_score: float
    drift_score: float  # How much has it changed (not necessarily bad)


@dataclass
class IntentAnalysisResult:
    """Full intent analysis for a prompt transformation"""
    original_concept: str
    generated_prompt: str
    
    # Dimension analyses
    semantic: IntentDimension
    visual: IntentDimension
    emotional: IntentDimension
    narrative: IntentDimension
    
    # Overall scores
    overall_preservation: float  # 0-100, higher = more preserved
    overall_achievability: float  # 0-100, higher = more achievable
    balance_score: float  # Sweet spot between preservation and achievability
    
    # Flags
    racing_to_bottom: bool
    over_complicated: bool
    good_balance: bool


class IntentExtractor:
    """Extracts intent elements from text"""
    
    # Semantic markers
    SEMANTIC_PATTERNS = [
        r'\b(about|represents?|symbolizes?|shows?|depicts?|illustrates?)\s+(\w+(?:\s+\w+){0,3})',
        r'\b(theme|concept|idea|notion)\s+of\s+(\w+(?:\s+\w+){0,2})',
    ]
    
    # Visual element patterns
    VISUAL_ELEMENTS = [
        "person", "face", "hands", "desk", "laptop", "computer", "screen",
        "room", "office", "window", "light", "lamp", "keyboard", "chair",
        "coffee", "cup", "plant", "book", "phone", "camera", "background",
        "foreground", "silhouette", "shadow", "reflection"
    ]
    
    # Emotional/mood words
    EMOTIONAL_WORDS = [
        "happy", "sad", "excited", "frustrated", "tired", "energetic",
        "peaceful", "tense", "dramatic", "calm", "intense", "subtle",
        "warm", "cold", "cozy", "sterile", "inviting", "mysterious",
        "triumphant", "defeated", "hopeful", "anxious", "confident"
    ]
    
    # Narrative markers
    NARRATIVE_PATTERNS = [
        r'\b(then|next|after|before|finally|suddenly|gradually)\b',
        r'\b(begins?|starts?|ends?|continues?|transforms?|changes?|becomes?)\b',
        r'\b(journey|story|arc|progression|sequence|transition)\b',
    ]
    
    # Action words that indicate achievability challenges
    CHALLENGING_ACTIONS = [
        "transforms", "morphs", "dissolves", "materializes", "glows",
        "floats", "flies", "teleports", "explodes", "implodes",
        "sparkles", "shimmers", "pulses", "radiates"
    ]
    
    def extract_semantic(self, text: str) -> List[str]:
        """Extract semantic/thematic elements"""
        elements = []
        text_lower = text.lower()
        
        for pattern in self.SEMANTIC_PATTERNS:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if isinstance(match, tuple):
                    elements.append(match[-1].strip())
                else:
                    elements.append(match.strip())
        
        # Also extract key nouns that might carry meaning
        words = text_lower.split()
        key_nouns = ["project", "demo", "code", "coding", "developer", "development",
                     "creation", "building", "making", "work", "breakthrough", "success"]
        elements.extend([w for w in words if w in key_nouns])
        
        return list(set(elements))
    
    def extract_visual(self, text: str) -> List[str]:
        """Extract visual elements"""
        text_lower = text.lower()
        return [elem for elem in self.VISUAL_ELEMENTS if elem in text_lower]
    
    def extract_emotional(self, text: str) -> List[str]:
        """Extract emotional/mood elements"""
        text_lower = text.lower()
        return [word for word in self.EMOTIONAL_WORDS if word in text_lower]
    
    def extract_narrative(self, text: str) -> List[str]:
        """Extract narrative elements"""
        elements = []
        text_lower = text.lower()
        
        for pattern in self.NARRATIVE_PATTERNS:
            matches = re.findall(pattern, text_lower)
            elements.extend(matches)
        
        return list(set(elements))
    
    def extract_challenging(self, text: str) -> List[str]:
        """Extract elements that are challenging for AI video"""
        text_lower = text.lower()
        return [action for action in self.CHALLENGING_ACTIONS if action in text_lower]


class IntentPreservationAnalyzer:
    """Analyzes intent preservation between original and generated prompts"""
    
    def __init__(self):
        self.extractor = IntentExtractor()
    
    def analyze(self, original_concept: str, generated_prompt: str) -> IntentAnalysisResult:
        """Full intent preservation analysis"""
        
        # Extract elements from both
        orig_semantic = set(self.extractor.extract_semantic(original_concept))
        gen_semantic = set(self.extractor.extract_semantic(generated_prompt))
        
        orig_visual = set(self.extractor.extract_visual(original_concept))
        gen_visual = set(self.extractor.extract_visual(generated_prompt))
        
        orig_emotional = set(self.extractor.extract_emotional(original_concept))
        gen_emotional = set(self.extractor.extract_emotional(generated_prompt))
        
        orig_narrative = set(self.extractor.extract_narrative(original_concept))
        gen_narrative = set(self.extractor.extract_narrative(generated_prompt))
        
        # Build dimension analyses
        semantic = self._analyze_dimension("semantic", orig_semantic, gen_semantic)
        visual = self._analyze_dimension("visual", orig_visual, gen_visual)
        emotional = self._analyze_dimension("emotional", orig_emotional, gen_emotional)
        narrative = self._analyze_dimension("narrative", orig_narrative, gen_narrative)
        
        # Calculate overall scores
        preservation_scores = [
            semantic.preservation_score,
            visual.preservation_score,
            emotional.preservation_score,
            narrative.preservation_score
        ]
        # Weight semantic and emotional higher
        weights = [0.35, 0.25, 0.25, 0.15]
        overall_preservation = sum(s * w for s, w in zip(preservation_scores, weights))
        
        # Achievability (inverse of challenging elements)
        challenging = self.extractor.extract_challenging(generated_prompt)
        overall_achievability = max(0, 100 - len(challenging) * 15)
        
        # Balance score: sweet spot is high preservation AND high achievability
        balance_score = (overall_preservation * overall_achievability) ** 0.5
        
        # Detect problems
        racing_to_bottom = overall_preservation < 40 and overall_achievability > 80
        over_complicated = overall_preservation > 80 and overall_achievability < 40
        good_balance = overall_preservation > 60 and overall_achievability > 60
        
        return IntentAnalysisResult(
            original_concept=original_concept,
            generated_prompt=generated_prompt,
            semantic=semantic,
            visual=visual,
            emotional=emotional,
            narrative=narrative,
            overall_preservation=overall_preservation,
            overall_achievability=overall_achievability,
            balance_score=balance_score,
            racing_to_bottom=racing_to_bottom,
            over_complicated=over_complicated,
            good_balance=good_balance
        )
    
    def _analyze_dimension(self, name: str, original: set, generated: set) -> IntentDimension:
        """Analyze a single intent dimension"""
        preserved = original & generated
        lost = original - generated
        added = generated - original
        
        if len(original) == 0:
            preservation_score = 100.0  # Nothing to lose
        else:
            preservation_score = len(preserved) / len(original) * 100
        
        # Drift is how different generated is from original
        total_elements = len(original | generated)
        if total_elements == 0:
            drift_score = 0.0
        else:
            drift_score = (len(lost) + len(added)) / total_elements * 100
        
        return IntentDimension(
            name=name,
            original_elements=list(original),
            preserved_elements=list(preserved),
            lost_elements=list(lost),
            added_elements=list(added),
            preservation_score=preservation_score,
            drift_score=drift_score
        )
    
    def analyze_run_history(self, runs: List[Dict]) -> pd.DataFrame:
        """Analyze intent preservation across multiple runs"""
        records = []
        
        for run in runs:
            concept = run.get("metadata", {}).get("concept", "")
            
            for scene in run.get("scenes", []):
                prompt = scene.get("description", "")
                
                if not concept or not prompt:
                    continue
                
                result = self.analyze(concept, prompt)
                
                records.append({
                    "run_id": run.get("run_id"),
                    "scene_id": scene.get("scene_id"),
                    "overall_preservation": result.overall_preservation,
                    "overall_achievability": result.overall_achievability,
                    "balance_score": result.balance_score,
                    "semantic_preservation": result.semantic.preservation_score,
                    "visual_preservation": result.visual.preservation_score,
                    "emotional_preservation": result.emotional.preservation_score,
                    "narrative_preservation": result.narrative.preservation_score,
                    "racing_to_bottom": result.racing_to_bottom,
                    "over_complicated": result.over_complicated,
                    "good_balance": result.good_balance,
                    "semantic_lost": ", ".join(result.semantic.lost_elements[:3]),
                    "emotional_lost": ", ".join(result.emotional.lost_elements[:3]),
                })
        
        return pd.DataFrame(records)


class BalanceOptimizer:
    """Suggests how to optimize the preservation/achievability balance"""
    
    def suggest_improvements(self, result: IntentAnalysisResult) -> List[str]:
        """Suggest improvements based on analysis"""
        suggestions = []
        
        if result.racing_to_bottom:
            suggestions.append("⚠️ RACING TO BOTTOM DETECTED")
            suggestions.append("The prompt has been over-simplified. Consider:")
            
            if result.semantic.lost_elements:
                suggestions.append(f"  - Restore semantic elements: {', '.join(result.semantic.lost_elements[:3])}")
            if result.emotional.lost_elements:
                suggestions.append(f"  - Restore emotional tone: {', '.join(result.emotional.lost_elements[:3])}")
            
            suggestions.append("  - Use more descriptive language while keeping visuals concrete")
            suggestions.append("  - Add mood/atmosphere details that don't require VFX")
        
        elif result.over_complicated:
            suggestions.append("⚠️ OVER-COMPLICATED PROMPT")
            suggestions.append("The prompt is too ambitious for AI video. Consider:")
            suggestions.append("  - Remove transformation/VFX language")
            suggestions.append("  - Replace abstract concepts with concrete visuals")
            suggestions.append("  - Simplify to achievable camera movements")
        
        elif result.good_balance:
            suggestions.append("✅ GOOD BALANCE")
            suggestions.append("The prompt balances intent preservation with achievability.")
        
        else:
            suggestions.append("📊 ANALYSIS")
            suggestions.append(f"Preservation: {result.overall_preservation:.0f}%")
            suggestions.append(f"Achievability: {result.overall_achievability:.0f}%")
            suggestions.append("Consider adjusting based on which metric needs improvement.")
        
        return suggestions


# ============================================================================
# QUICK ANALYSIS FUNCTIONS
# ============================================================================

def quick_analyze(original: str, generated: str) -> None:
    """Quick analysis for interactive use"""
    analyzer = IntentPreservationAnalyzer()
    result = analyzer.analyze(original, generated)
    
    print("\n" + "=" * 60)
    print("INTENT PRESERVATION ANALYSIS")
    print("=" * 60)
    
    print(f"\n📝 Original: {original[:100]}...")
    print(f"📝 Generated: {generated[:100]}...")
    
    print(f"\n📊 SCORES")
    print(f"   Overall Preservation: {result.overall_preservation:.0f}%")
    print(f"   Overall Achievability: {result.overall_achievability:.0f}%")
    print(f"   Balance Score: {result.balance_score:.0f}")
    
    print(f"\n🔍 DIMENSIONS")
    for dim in [result.semantic, result.visual, result.emotional, result.narrative]:
        status = "✓" if dim.preservation_score > 60 else "⚠️"
        print(f"   {status} {dim.name.capitalize()}: {dim.preservation_score:.0f}%")
        if dim.lost_elements:
            print(f"      Lost: {', '.join(dim.lost_elements[:3])}")
    
    print(f"\n🚦 STATUS")
    if result.racing_to_bottom:
        print("   ⚠️  RACING TO BOTTOM - Prompt over-simplified!")
    elif result.over_complicated:
        print("   ⚠️  OVER-COMPLICATED - Prompt too ambitious!")
    elif result.good_balance:
        print("   ✅ GOOD BALANCE - Well optimized!")
    
    optimizer = BalanceOptimizer()
    suggestions = optimizer.suggest_improvements(result)
    print(f"\n💡 SUGGESTIONS")
    for s in suggestions:
        print(f"   {s}")


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 3:
        original = sys.argv[1]
        generated = sys.argv[2]
        quick_analyze(original, generated)
    else:
        # Demo with example
        original = "A 15-second story of a developer having a breakthrough moment, going from frustrated to triumphant"
        generated = "Close-up of person at desk, neutral expression, soft lighting"
        
        print("Demo analysis (provide original and generated as arguments):")
        quick_analyze(original, generated)
