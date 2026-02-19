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
    """
    What this segment DOES in the narrative.
    Content-type agnostic — works for papers, news, datasets, mixed sources.
    """

    # === Structural ===
    # These control pacing and flow, not content.
    INTRO = "intro"                         # Opening hook, topic framing
    TRANSITION = "transition"               # Bridge between topics or segments
    RECAP = "recap"                         # Summary of what was covered
    OUTRO = "outro"                         # Closing, call to action, sign-off

    # === Exposition ===
    # Segments that teach, explain, or set the scene.
    CONTEXT = "context"                     # Background, history, setting the scene
    EXPLANATION = "explanation"             # Breaking down a concept or process
    DEFINITION = "definition"               # Defining terms, scope, or frameworks
    NARRATIVE = "narrative"                 # Storytelling, anecdote, timeline of events

    # === Evidence & Data ===
    # Segments that present facts, numbers, or artifacts.
    CLAIM = "claim"                         # Presenting an assertion or finding
    EVIDENCE = "evidence"                   # Supporting a claim with data/quotes/citations
    DATA_WALKTHROUGH = "data_walkthrough"   # Walking through numbers, charts, datasets
    FIGURE_REFERENCE = "figure_reference"   # Discussing a specific visual artifact

    # === Analysis & Perspective ===
    # Segments that interpret, compare, or challenge.
    ANALYSIS = "analysis"                   # Interpreting evidence, drawing conclusions
    COMPARISON = "comparison"               # Contrasting sources, methods, viewpoints
    COUNTERPOINT = "counterpoint"           # Presenting opposing view or challenge
    SYNTHESIS = "synthesis"                 # Combining multiple sources into new insight

    # === Editorial ===
    # Segments with a point of view.
    COMMENTARY = "commentary"               # Host/narrator opinion or editorial voice
    QUESTION = "question"                   # Posing a question to the audience
    SPECULATION = "speculation"             # Forward-looking, hypothetical, what-if


# === Compatibility Aliases ===
# These map old intent names to new vocabulary for backward compatibility.
# Can be removed once all code uses the new vocabulary.
SegmentIntent.BACKGROUND = SegmentIntent.CONTEXT
SegmentIntent.METHODOLOGY = SegmentIntent.EXPLANATION
SegmentIntent.KEY_FINDING = SegmentIntent.CLAIM
SegmentIntent.FIGURE_WALKTHROUGH = SegmentIntent.FIGURE_REFERENCE
SegmentIntent.DATA_DISCUSSION = SegmentIntent.DATA_WALKTHROUGH


class SourceType(str, Enum):
    """What kind of source this is."""
    PAPER = "paper"
    NEWS = "news"
    DATASET = "dataset"
    GOVERNMENT = "government"
    TRANSCRIPT = "transcript"
    NOTE = "note"               # User's own observations
    ARTIFACT = "artifact"       # Previously generated content
    URL = "url"                 # Generic web content


@dataclass
class SourceAttribution:
    """Tracks which source(s) a segment draws from."""
    source_id: str                          # KB source ID
    source_type: SourceType
    atoms_used: List[str] = field(default_factory=list)  # Specific atom IDs
    confidence: float = 1.0                 # How directly this segment uses the source
    label: Optional[str] = None             # Display label, e.g. "Smith et al. 2024"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "atoms_used": self.atoms_used,
            "confidence": self.confidence,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceAttribution":
        """Deserialize from dictionary."""
        return cls(
            source_id=data["source_id"],
            source_type=SourceType(data.get("source_type", "paper")),
            atoms_used=data.get("atoms_used", []),
            confidence=data.get("confidence", 1.0),
            label=data.get("label"),
        )


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
    intent: SegmentIntent = SegmentIntent.CONTEXT   # Default to CONTEXT (was BACKGROUND)

    # Source tracking (replaces simple figure_refs for multi-source support)
    source_attributions: List[SourceAttribution] = field(default_factory=list)
    figure_refs: List[int] = field(default_factory=list)   # Kept for convenience — "Figure N" mentions
    key_concepts: List[str] = field(default_factory=list)

    # Production variant support
    perspective: Optional[str] = None               # e.g., "neutral", "left_0.2", "right_0.8"
    content_type_hint: Optional[str] = None         # e.g., "news", "research", "policy", "mixed"

    # Visual direction (populated by DoP)
    visual_direction: str = ""                      # Free-text hint for DALL-E prompt
    display_mode: Optional[str] = None              # "figure_sync", "dall_e", "carry_forward", etc.
    importance_score: float = 0.5                   # For budget allocation

    # Audio (populated by Audio Producer)
    audio_file: Optional[str] = None
    estimated_duration_sec: Optional[float] = None
    actual_duration_sec: Optional[float] = None

    # Visual asset (populated by Visual Producer)
    visual_asset_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "idx": self.idx,
            "text": self.text,
            "intent": self.intent.value,
            "source_attributions": [sa.to_dict() for sa in self.source_attributions],
            "figure_refs": self.figure_refs,
            "key_concepts": self.key_concepts,
            "perspective": self.perspective,
            "content_type_hint": self.content_type_hint,
            "visual_direction": self.visual_direction,
            "display_mode": self.display_mode,
            "importance_score": self.importance_score,
            "audio_file": self.audio_file,
            "estimated_duration_sec": self.estimated_duration_sec,
            "actual_duration_sec": self.actual_duration_sec,
            "visual_asset_id": self.visual_asset_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptSegment":
        """Deserialize from dictionary."""
        # Handle intent with backward compatibility for old values
        intent_val = data.get("intent", "context")
        # Map old intent values to new ones
        intent_mapping = {
            "background": "context",
            "methodology": "explanation",
            "key_finding": "claim",
            "figure_walkthrough": "figure_reference",
            "data_discussion": "data_walkthrough",
        }
        intent_val = intent_mapping.get(intent_val, intent_val)

        return cls(
            idx=data["idx"],
            text=data["text"],
            intent=SegmentIntent(intent_val),
            source_attributions=[
                SourceAttribution.from_dict(sa)
                for sa in data.get("source_attributions", [])
            ],
            figure_refs=data.get("figure_refs", []),
            key_concepts=data.get("key_concepts", []),
            perspective=data.get("perspective"),
            content_type_hint=data.get("content_type_hint"),
            visual_direction=data.get("visual_direction", ""),
            display_mode=data.get("display_mode"),
            importance_score=data.get("importance_score", 0.5),
            audio_file=data.get("audio_file"),
            estimated_duration_sec=data.get("estimated_duration_sec"),
            actual_duration_sec=data.get("actual_duration_sec"),
            visual_asset_id=data.get("visual_asset_id"),
        )


@dataclass
class StructuredScript:
    """The single source of truth for a production."""
    script_id: str                                  # e.g., "trial_000_v1"
    trial_id: str
    version: int = 1

    segments: List[ScriptSegment] = field(default_factory=list)
    figure_inventory: Dict[int, FigureInventory] = field(default_factory=dict)

    # Multi-source metadata
    sources_used: List[str] = field(default_factory=list)  # Source IDs from KB
    content_type: str = "research"                  # Primary content type
    production_style: str = "explainer"             # "explainer", "news_analysis", "debate", "narrative"

    # Variant support
    perspective: Optional[str] = None               # Production-level perspective
    variant_of: Optional[str] = None                # script_id of the base version (for bias variants)

    # Existing metadata
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

    def get_segments_by_source(self, source_id: str) -> List[ScriptSegment]:
        """Return segments that draw from a specific source."""
        return [
            s for s in self.segments
            if any(a.source_id == source_id for a in s.source_attributions)
        ]

    def get_sources_summary(self) -> Dict[str, int]:
        """Return {source_id: segment_count} for all sources."""
        counts: Dict[str, int] = {}
        for seg in self.segments:
            for attr in seg.source_attributions:
                counts[attr.source_id] = counts.get(attr.source_id, 0) + 1
        return counts

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
            # Multi-source metadata
            "sources_used": self.sources_used,
            "content_type": self.content_type,
            "production_style": self.production_style,
            # Variant support
            "perspective": self.perspective,
            "variant_of": self.variant_of,
            # Existing metadata
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
            # Multi-source metadata
            sources_used=data.get("sources_used", []),
            content_type=data.get("content_type", "research"),
            production_style=data.get("production_style", "explainer"),
            # Variant support
            perspective=data.get("perspective"),
            variant_of=data.get("variant_of"),
            # Existing metadata
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
        kb_figures: Optional[Dict[int, dict]] = None,
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
            kb_figures: Optional mapping of figure number -> figure metadata dict.
                Each dict can have: kb_path, caption, description.
                Legacy: Also accepts Dict[int, str] for backward compatibility.
        """
        # Split into paragraphs
        paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]

        segments = []
        figure_mentions: Dict[int, List[int]] = {}  # figure_number -> segment indices

        for idx, para in enumerate(paragraphs):
            # Parse "Figure N" and "Table N" mentions
            figure_pattern = r"(?:Figure|Table|Fig\.)\s+(\d+)"
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

            # Extract key concepts (capitalized multi-word phrases + technical terms)
            key_concepts = cls._extract_key_concepts(para)

            segments.append(ScriptSegment(
                idx=idx,
                text=para,
                intent=intent,
                figure_refs=figure_refs,
                key_concepts=key_concepts,
                estimated_duration_sec=estimated_duration,
                importance_score=importance,
            ))

        # Build figure inventory
        figure_inventory = {}
        if kb_figures:
            for fig_num, fig_data in kb_figures.items():
                # Support both legacy (str) and new (dict) formats
                if isinstance(fig_data, str):
                    # Legacy: kb_figures is Dict[int, str] (path only)
                    figure_inventory[fig_num] = FigureInventory(
                        figure_number=fig_num,
                        kb_path=fig_data,
                        discussed_in_segments=figure_mentions.get(fig_num, []),
                    )
                else:
                    # New: kb_figures is Dict[int, dict] with full metadata
                    figure_inventory[fig_num] = FigureInventory(
                        figure_number=fig_num,
                        kb_path=fig_data.get("kb_path", ""),
                        caption=fig_data.get("caption", ""),
                        description=fig_data.get("description", ""),
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
    def _extract_key_concepts(text: str) -> List[str]:
        """Extract key concepts from paragraph text via heuristics.

        Finds capitalized multi-word phrases (e.g., 'Kalman Filter', 'Particle Filter'),
        quoted terms, and technical terms that are likely to be meaningful search queries.
        """
        concepts = []
        seen = set()

        # Sentence starters and common words to skip
        skip = {
            'the', 'this', 'that', 'these', 'those', 'but', 'and', 'now', 'so',
            'well', 'let', 'here', 'what', 'how', 'when', 'where', 'why', 'who',
            'think', 'consider', 'imagine', 'look', 'hey', 'welcome', 'take',
            'you', 'we', 'they', 'our', 'their', 'its', 'for', 'from', 'with',
            'not', 'don', 'doesn', 'didn', 'can', 'could', 'would', 'should',
            'may', 'might', 'will', 'shall', 'has', 'have', 'had', 'are', 'is',
            'was', 'were', 'been', 'being', 'into', 'about', 'just', 'like',
            'sure', 'say', 'said', 'get', 'got', 'know', 'knew', 'see', 'seen',
            'one', 'two', 'first', 'second', 'each', 'every', 'some', 'any',
            'it', 'do', 'does', 'did', 'if', 'then', 'than', 'or', 'nor',
            'both', 'either', 'neither', 'also', 'too', 'yet', 'still',
        }

        # 1. Multi-word capitalized phrases (e.g., "Kalman Filter", "Monte Carlo")
        multi_cap = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text)
        for phrase in multi_cap:
            lower = phrase.lower()
            if lower not in seen and phrase.split()[0].lower() not in skip:
                seen.add(lower)
                concepts.append(phrase)

        # 2. Single capitalized words mid-sentence
        mid_caps = re.findall(r'(?<=[a-z,;:]\s)([A-Z][a-z]{3,})\b', text)
        for word in mid_caps:
            lower = word.lower()
            if lower not in seen and lower not in skip:
                seen.add(lower)
                concepts.append(word)

        # 3. Quoted terms
        quoted = re.findall(r'"([^"]{3,40})"', text)
        for q in quoted:
            lower = q.lower()
            if lower not in seen:
                seen.add(lower)
                concepts.append(q)

        # 4. Technical compound terms (lowercase but meaningful)
        tech_patterns = re.findall(
            r'\b((?:computational|matrix|neural|machine|deep|artificial|quantum|'
            r'statistical|mathematical|transformer|language|attention|gradient|'
            r'reinforcement|unsupervised|supervised|probabilistic|stochastic|'
            r'adversarial|generative|convolutional|recurrent)\s+'
            r'[a-z]+(?:\s+[a-z]+)?)\b',
            text, re.IGNORECASE
        )
        for term in tech_patterns:
            lower = term.lower()
            if lower not in seen:
                seen.add(lower)
                concepts.append(term)

        # 5. Acronyms (2+ uppercase letters, not common ones)
        acronyms = re.findall(r'\b([A-Z]{2,}[a-z]?)\b', text)
        skip_acronyms = {'OK', 'US', 'UK', 'EU', 'AM', 'PM', 'IT', 'OR', 'AN', 'DO'}
        for acr in acronyms:
            if acr not in seen and acr not in skip_acronyms and len(acr) >= 2:
                seen.add(acr)
                concepts.append(acr)

        return concepts[:5]

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
        3. Has figure references -> FIGURE_REFERENCE
        4. Keyword-based classification (content-agnostic vocabulary)
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
            return SegmentIntent.FIGURE_REFERENCE

        # === Evidence & Data ===
        # Claims and findings
        if any(word in text_lower for word in ["claim", "argue", "assert", "contend", "propose"]):
            return SegmentIntent.CLAIM
        if any(word in text_lower for word in ["results", "finding", "found", "shows", "demonstrates", "evidence"]):
            return SegmentIntent.CLAIM
        # Supporting evidence
        if any(word in text_lower for word in ["according to", "study shows", "research indicates", "data from"]):
            return SegmentIntent.EVIDENCE
        # Data walkthrough
        if any(word in text_lower for word in ["data", "dataset", "statistics", "metrics", "numbers", "percent"]):
            return SegmentIntent.DATA_WALKTHROUGH

        # === Analysis & Perspective ===
        # Comparison
        if any(word in text_lower for word in ["compared", "versus", "comparison", "better than", "outperforms", "contrast"]):
            return SegmentIntent.COMPARISON
        # Counterpoint
        if any(word in text_lower for word in ["however", "but", "on the other hand", "critics", "opposing", "challenge"]):
            return SegmentIntent.COUNTERPOINT
        # Analysis
        if any(word in text_lower for word in ["suggests", "implies", "means", "indicates", "analysis"]):
            return SegmentIntent.ANALYSIS
        # Synthesis
        if any(word in text_lower for word in ["together", "combining", "synthesis", "overall", "taken together"]):
            return SegmentIntent.SYNTHESIS

        # === Exposition ===
        # Explanation (methodology, how things work)
        if any(word in text_lower for word in ["methodology", "approach", "method", "algorithm", "technique", "works by", "process"]):
            return SegmentIntent.EXPLANATION
        # Definition
        if any(word in text_lower for word in ["defined as", "means", "refers to", "is called", "known as"]):
            return SegmentIntent.DEFINITION
        # Narrative
        if any(word in text_lower for word in ["story", "happened", "began", "started", "timeline", "history of"]):
            return SegmentIntent.NARRATIVE
        # Context (background)
        if any(word in text_lower for word in ["context", "background", "traditionally", "historically", "previously"]):
            return SegmentIntent.CONTEXT

        # === Editorial ===
        # Commentary
        if any(word in text_lower for word in ["i think", "in my view", "importantly", "notably", "fascinating"]):
            return SegmentIntent.COMMENTARY
        # Question
        if "?" in text and any(word in text_lower for word in ["what", "why", "how", "could", "should"]):
            return SegmentIntent.QUESTION
        # Speculation
        if any(word in text_lower for word in ["might", "could", "future", "imagine", "what if", "potentially"]):
            return SegmentIntent.SPECULATION

        # === Structural ===
        # Transition
        if any(word in text_lower for word in ["let's", "now", "moving", "turning", "next", "shifting"]):
            return SegmentIntent.TRANSITION

        # Position-based fallback: second-to-last with no other match
        if idx == total - 2:
            return SegmentIntent.RECAP

        return SegmentIntent.CONTEXT

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

        # Intent-based scoring (content-agnostic vocabulary)
        intent_scores = {
            # Structural
            SegmentIntent.INTRO: 0.8,
            SegmentIntent.TRANSITION: 0.2,
            SegmentIntent.RECAP: 0.5,
            SegmentIntent.OUTRO: 0.6,
            # Exposition
            SegmentIntent.CONTEXT: 0.4,
            SegmentIntent.EXPLANATION: 0.7,
            SegmentIntent.DEFINITION: 0.5,
            SegmentIntent.NARRATIVE: 0.6,
            # Evidence & Data
            SegmentIntent.CLAIM: 0.9,
            SegmentIntent.EVIDENCE: 0.7,
            SegmentIntent.DATA_WALKTHROUGH: 0.6,
            SegmentIntent.FIGURE_REFERENCE: 1.0,  # Highest - will use KB figure
            # Analysis & Perspective
            SegmentIntent.ANALYSIS: 0.7,
            SegmentIntent.COMPARISON: 0.7,
            SegmentIntent.COUNTERPOINT: 0.6,
            SegmentIntent.SYNTHESIS: 0.8,
            # Editorial
            SegmentIntent.COMMENTARY: 0.5,
            SegmentIntent.QUESTION: 0.4,
            SegmentIntent.SPECULATION: 0.6,
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

    @staticmethod
    def _extract_key_concepts(text: str, max_concepts: int = 3) -> List[str]:
        """
        Extract key noun phrases from paragraph text using heuristics.

        Looks for capitalized multi-word phrases, technical terms, and
        quoted phrases. Returns up to max_concepts items.
        """
        concepts = []

        # 1. Quoted phrases (e.g., "Extended Kalman Filter")
        quoted = re.findall(r'"([^"]{3,40})"', text)
        concepts.extend(quoted)

        # 2. Capitalized multi-word phrases (e.g., "Global Positioning System")
        #    Match 2-5 consecutive capitalized words with 3+ chars each, not at sentence start
        cap_pattern = r'(?<=[.!?]\s|, )([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+)'
        skip_starts = {"and", "but", "the", "for", "with", "from", "into", "that", "this",
                        "what", "when", "where", "which", "while", "also", "then", "just"}
        for match in re.findall(cap_pattern, text):
            first_word = match.split()[0].lower()
            if first_word not in skip_starts:
                concepts.append(match)

        # 3. Technical terms with common patterns (acronyms + expansions)
        #    e.g., "UAV", "GPS", "GNSS", "EKF"
        acronyms = re.findall(r'\b([A-Z]{2,6})\b', text)
        # Filter common English words that happen to be uppercase
        stopwords = {"THE", "AND", "BUT", "FOR", "NOT", "YOU", "ALL", "CAN", "HER",
                     "WAS", "ONE", "OUR", "OUT", "ARE", "HAS", "HIS", "HOW", "ITS",
                     "MAY", "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "DID", "GET",
                     "LET", "SAY", "SHE", "TOO", "USE"}
        acronyms = [a for a in acronyms if a not in stopwords]
        concepts.extend(acronyms[:2])

        # 4. Phrases after signal words like "called", "known as", "termed"
        signal = re.findall(r'(?:called|known as|termed|referred to as)\s+["\']?([A-Z][^,."\']{2,35})', text, re.IGNORECASE)
        # Clean trailing whitespace and incomplete words
        concepts.extend(s.rsplit(' ', 1)[0] if len(s) > 30 else s for s in signal)

        # Deduplicate while preserving order, limit to max_concepts
        seen = set()
        unique = []
        for c in concepts:
            cleaned = c.strip()
            # Strip leading articles/prepositions
            for prefix in ("a ", "an ", "the "):
                if cleaned.lower().startswith(prefix):
                    cleaned = cleaned[len(prefix):]
            c_lower = cleaned.lower()
            if c_lower not in seen and len(cleaned) >= 2:
                seen.add(c_lower)
                unique.append(cleaned)
        return unique[:max_concepts]
