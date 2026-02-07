"""
Structured script model - single source of truth for production.

Replaces flat _script.txt with structured JSON that both audio
and visual production pipelines read from.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class SegmentIntent(str, Enum):
    """What a script segment IS - drives visual and pacing decisions."""
    INTRO = "intro"
    BACKGROUND = "background"
    METHODOLOGY = "methodology"
    KEY_FINDING = "key_finding"
    FIGURE_WALKTHROUGH = "figure_walkthrough"
    DATA_DISCUSSION = "data_discussion"
    COMPARISON = "comparison"
    TRANSITION = "transition"
    RECAP = "recap"
    OUTRO = "outro"


@dataclass
class FigureInventory:
    """A figure available from the KB for this script."""
    figure_number: int                              # The "Figure N" number from paper
    kb_path: str                                    # Path to extracted figure image
    caption: str = ""
    description: str = ""                           # LLM-generated description
    discussed_in_segments: List[int] = field(default_factory=list)


@dataclass
class ScriptSegment:
    """A single segment of the structured script."""
    idx: int
    text: str                                       # Narration text
    intent: SegmentIntent = SegmentIntent.BACKGROUND
    figure_refs: List[int] = field(default_factory=list)  # "Figure N" mentions
    key_concepts: List[str] = field(default_factory=list)
    visual_direction: str = ""                      # DoP annotation

    # Estimated before TTS
    estimated_duration_sec: Optional[float] = None
    importance_score: float = 0.5                   # For budget allocation

    # Populated after audio generation
    audio_file: Optional[str] = None
    actual_duration_sec: Optional[float] = None

    # Populated after visual assignment (by DoP)
    visual_asset_id: Optional[str] = None
    display_mode: Optional[str] = None              # "figure_sync", "dall_e", "carry_forward", "text_only"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "idx": self.idx,
            "text": self.text,
            "intent": self.intent.value,
            "figure_refs": self.figure_refs,
            "key_concepts": self.key_concepts,
            "visual_direction": self.visual_direction,
            "estimated_duration_sec": self.estimated_duration_sec,
            "importance_score": self.importance_score,
            "audio_file": self.audio_file,
            "actual_duration_sec": self.actual_duration_sec,
            "visual_asset_id": self.visual_asset_id,
            "display_mode": self.display_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptSegment":
        """Deserialize from dictionary."""
        return cls(
            idx=data["idx"],
            text=data["text"],
            intent=SegmentIntent(data.get("intent", "background")),
            figure_refs=data.get("figure_refs", []),
            key_concepts=data.get("key_concepts", []),
            visual_direction=data.get("visual_direction", ""),
            estimated_duration_sec=data.get("estimated_duration_sec"),
            importance_score=data.get("importance_score", 0.5),
            audio_file=data.get("audio_file"),
            actual_duration_sec=data.get("actual_duration_sec"),
            visual_asset_id=data.get("visual_asset_id"),
            display_mode=data.get("display_mode"),
        )


@dataclass
class StructuredScript:
    """The single source of truth for a production."""
    script_id: str                                  # e.g., "trial_000_v1"
    trial_id: str
    version: int = 1

    segments: List[ScriptSegment] = field(default_factory=list)
    figure_inventory: Dict[int, FigureInventory] = field(default_factory=dict)

    # Metadata
    total_segments: int = 0
    total_estimated_duration_sec: float = 0.0
    source_document: Optional[str] = None           # KB source
    generation_prompt: Optional[str] = None         # What Claude was asked
    created_at: Optional[str] = None

    def get_figure_segments(self) -> List[ScriptSegment]:
        """Return segments that reference figures."""
        return [s for s in self.segments if s.figure_refs]

    def get_segments_by_intent(self, intent: SegmentIntent) -> List[ScriptSegment]:
        """Return all segments with a specific intent."""
        return [s for s in self.segments if s.intent == intent]

    def get_segment(self, idx: int) -> Optional[ScriptSegment]:
        """Get segment by index."""
        for s in self.segments:
            if s.idx == idx:
                return s
        return None

    def update_segment(self, idx: int, **kwargs) -> bool:
        """Update a segment's fields. Returns True if found."""
        seg = self.get_segment(idx)
        if seg:
            for key, value in kwargs.items():
                if hasattr(seg, key):
                    setattr(seg, key, value)
            return True
        return False

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "script_id": self.script_id,
            "trial_id": self.trial_id,
            "version": self.version,
            "segments": [s.to_dict() for s in self.segments],
            "figure_inventory": {
                str(k): {
                    "figure_number": v.figure_number,
                    "kb_path": v.kb_path,
                    "caption": v.caption,
                    "description": v.description,
                    "discussed_in_segments": v.discussed_in_segments,
                }
                for k, v in self.figure_inventory.items()
            },
            "total_segments": self.total_segments,
            "total_estimated_duration_sec": self.total_estimated_duration_sec,
            "source_document": self.source_document,
            "generation_prompt": self.generation_prompt,
            "created_at": self.created_at,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path) -> None:
        """Save to JSON file."""
        path.write_text(self.to_json())

    def to_flat_text(self) -> str:
        """Export as flat text (for backward compatibility with _script.txt)."""
        return "\n\n".join(s.text for s in self.segments)

    @classmethod
    def from_dict(cls, data: dict) -> "StructuredScript":
        """Deserialize from dictionary."""
        figure_inv = {}
        for k, v in data.get("figure_inventory", {}).items():
            fig_num = int(k)
            figure_inv[fig_num] = FigureInventory(
                figure_number=v["figure_number"],
                kb_path=v["kb_path"],
                caption=v.get("caption", ""),
                description=v.get("description", ""),
                discussed_in_segments=v.get("discussed_in_segments", []),
            )

        return cls(
            script_id=data["script_id"],
            trial_id=data["trial_id"],
            version=data.get("version", 1),
            segments=[ScriptSegment.from_dict(s) for s in data.get("segments", [])],
            figure_inventory=figure_inv,
            total_segments=data.get("total_segments", 0),
            total_estimated_duration_sec=data.get("total_estimated_duration_sec", 0.0),
            source_document=data.get("source_document"),
            generation_prompt=data.get("generation_prompt"),
            created_at=data.get("created_at"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "StructuredScript":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def load(cls, path: Path) -> "StructuredScript":
        """Load from JSON file."""
        return cls.from_json(path.read_text())

    @classmethod
    def from_script_text(
        cls,
        script_text: str,
        trial_id: str,
        kb_figures: Optional[Dict[int, str]] = None,
    ) -> "StructuredScript":
        """
        Parse a flat _script.txt into a StructuredScript.

        This is the migration path from the current pipeline.

        1. Split into paragraphs by double newline
        2. Regex for "Figure N" mentions
        3. Classify intent via heuristics
        4. Map figure refs to kb_figure_paths

        Args:
            script_text: The flat script text
            trial_id: Trial identifier
            kb_figures: Optional mapping of figure number -> kb_path
        """
        # Split into paragraphs
        paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]

        segments = []
        figure_mentions: Dict[int, List[int]] = {}  # figure_number -> segment indices

        for idx, para in enumerate(paragraphs):
            # Parse "Figure N" mentions
            figure_pattern = r"Figure\s+(\d+)"
            matches = re.findall(figure_pattern, para, re.IGNORECASE)
            figure_refs = [int(m) for m in matches]

            # Track which segments mention each figure
            for fig_num in figure_refs:
                if fig_num not in figure_mentions:
                    figure_mentions[fig_num] = []
                figure_mentions[fig_num].append(idx)

            # Classify intent via heuristics
            intent = cls._classify_intent(para, idx, len(paragraphs), figure_refs)

            # Estimate duration (~150 words per minute)
            word_count = len(para.split())
            estimated_duration = (word_count / 150) * 60  # seconds

            # Calculate importance score
            importance = cls._calculate_importance(para, intent, figure_refs)

            segments.append(ScriptSegment(
                idx=idx,
                text=para,
                intent=intent,
                figure_refs=figure_refs,
                estimated_duration_sec=estimated_duration,
                importance_score=importance,
            ))

        # Build figure inventory
        figure_inventory = {}
        if kb_figures:
            for fig_num, kb_path in kb_figures.items():
                figure_inventory[fig_num] = FigureInventory(
                    figure_number=fig_num,
                    kb_path=kb_path,
                    discussed_in_segments=figure_mentions.get(fig_num, []),
                )
        else:
            # Just record what figures were mentioned
            for fig_num, seg_indices in figure_mentions.items():
                figure_inventory[fig_num] = FigureInventory(
                    figure_number=fig_num,
                    kb_path="",  # Unknown
                    discussed_in_segments=seg_indices,
                )

        total_duration = sum(s.estimated_duration_sec or 0 for s in segments)

        return cls(
            script_id=f"{trial_id}_v1",
            trial_id=trial_id,
            version=1,
            segments=segments,
            figure_inventory=figure_inventory,
            total_segments=len(segments),
            total_estimated_duration_sec=total_duration,
            created_at=datetime.now().isoformat(),
        )

    @staticmethod
    def _classify_intent(
        text: str,
        idx: int,
        total: int,
        figure_refs: List[int],
    ) -> SegmentIntent:
        """
        Classify segment intent via heuristics.

        Priority order:
        1. First segment -> INTRO
        2. Last segment -> OUTRO
        3. Has figure references -> FIGURE_WALKTHROUGH (content takes priority)
        4. Keyword-based classification
        5. Second-to-last with no other match -> RECAP

        This can be upgraded to an LLM call for better accuracy.
        """
        text_lower = text.lower()

        # Position-based: INTRO and OUTRO are absolute
        if idx == 0:
            return SegmentIntent.INTRO
        if idx == total - 1:
            return SegmentIntent.OUTRO

        # Content takes priority: figure references
        if figure_refs:
            return SegmentIntent.FIGURE_WALKTHROUGH

        # Keyword-based classification
        if any(word in text_lower for word in ["methodology", "approach", "method", "algorithm", "technique"]):
            return SegmentIntent.METHODOLOGY
        if any(word in text_lower for word in ["compared", "versus", "comparison", "better than", "outperforms"]):
            return SegmentIntent.COMPARISON
        if any(word in text_lower for word in ["results", "finding", "found", "shows", "demonstrates", "performance"]):
            return SegmentIntent.KEY_FINDING
        if any(word in text_lower for word in ["data", "dataset", "experiment", "evaluation", "metrics"]):
            return SegmentIntent.DATA_DISCUSSION
        if any(word in text_lower for word in ["let's", "now", "moving", "turning", "next"]):
            return SegmentIntent.TRANSITION
        if any(word in text_lower for word in ["context", "background", "history", "traditionally"]):
            return SegmentIntent.BACKGROUND

        # Position-based fallback: second-to-last with no other match
        if idx == total - 2:
            return SegmentIntent.RECAP

        return SegmentIntent.BACKGROUND

    @staticmethod
    def _calculate_importance(
        text: str,
        intent: SegmentIntent,
        figure_refs: List[int],
    ) -> float:
        """
        Calculate importance score for budget allocation.

        Higher scores get priority for DALL-E images.
        """
        score = 0.5  # Base

        # Intent-based scoring
        intent_scores = {
            SegmentIntent.INTRO: 0.8,
            SegmentIntent.KEY_FINDING: 0.9,
            SegmentIntent.FIGURE_WALKTHROUGH: 1.0,  # Highest - will use KB figure
            SegmentIntent.METHODOLOGY: 0.7,
            SegmentIntent.DATA_DISCUSSION: 0.6,
            SegmentIntent.COMPARISON: 0.7,
            SegmentIntent.BACKGROUND: 0.4,
            SegmentIntent.TRANSITION: 0.2,
            SegmentIntent.RECAP: 0.5,
            SegmentIntent.OUTRO: 0.6,
        }
        score = intent_scores.get(intent, 0.5)

        # Boost for figure references
        if figure_refs:
            score = min(1.0, score + 0.2)

        # Boost for longer, substantial content
        word_count = len(text.split())
        if word_count > 150:
            score = min(1.0, score + 0.1)

        return round(score, 2)
