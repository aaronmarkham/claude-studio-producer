"""Unit tests for StructuredScript models"""

import json
import pytest
from pathlib import Path
import tempfile

from core.models.structured_script import (
    SegmentIntent,
    SourceType,
    SourceAttribution,
    FigureInventory,
    ScriptSegment,
    StructuredScript,
)


class TestSegmentIntent:
    """Test SegmentIntent enum"""

    def test_segment_intent_values(self):
        """Test that SegmentIntent has expected values (content-agnostic vocabulary)"""
        # Structural
        assert SegmentIntent.INTRO.value == "intro"
        assert SegmentIntent.TRANSITION.value == "transition"
        assert SegmentIntent.RECAP.value == "recap"
        assert SegmentIntent.OUTRO.value == "outro"
        # Exposition
        assert SegmentIntent.CONTEXT.value == "context"
        assert SegmentIntent.EXPLANATION.value == "explanation"
        assert SegmentIntent.DEFINITION.value == "definition"
        assert SegmentIntent.NARRATIVE.value == "narrative"
        # Evidence & Data
        assert SegmentIntent.CLAIM.value == "claim"
        assert SegmentIntent.EVIDENCE.value == "evidence"
        assert SegmentIntent.DATA_WALKTHROUGH.value == "data_walkthrough"
        assert SegmentIntent.FIGURE_REFERENCE.value == "figure_reference"
        # Analysis & Perspective
        assert SegmentIntent.ANALYSIS.value == "analysis"
        assert SegmentIntent.COMPARISON.value == "comparison"
        assert SegmentIntent.COUNTERPOINT.value == "counterpoint"
        assert SegmentIntent.SYNTHESIS.value == "synthesis"
        # Editorial
        assert SegmentIntent.COMMENTARY.value == "commentary"
        assert SegmentIntent.QUESTION.value == "question"
        assert SegmentIntent.SPECULATION.value == "speculation"

    def test_segment_intent_compatibility_aliases(self):
        """Test backward compatibility aliases map to new intents"""
        # Old names should work and map to new vocabulary
        assert SegmentIntent.BACKGROUND == SegmentIntent.CONTEXT
        assert SegmentIntent.METHODOLOGY == SegmentIntent.EXPLANATION
        assert SegmentIntent.KEY_FINDING == SegmentIntent.CLAIM
        assert SegmentIntent.FIGURE_WALKTHROUGH == SegmentIntent.FIGURE_REFERENCE
        assert SegmentIntent.DATA_DISCUSSION == SegmentIntent.DATA_WALKTHROUGH

    def test_segment_intent_count(self):
        """Test that we have the expected number of intents (19 in content-agnostic vocabulary)"""
        assert len(SegmentIntent) == 19


class TestScriptSegment:
    """Test ScriptSegment dataclass"""

    def test_segment_creation(self):
        """Test creating a segment with minimal fields"""
        seg = ScriptSegment(idx=0, text="Hello world")
        assert seg.idx == 0
        assert seg.text == "Hello world"
        assert seg.intent == SegmentIntent.CONTEXT  # Default is now CONTEXT
        assert seg.figure_refs == []
        assert seg.importance_score == 0.5
        # New fields have defaults
        assert seg.source_attributions == []
        assert seg.perspective is None
        assert seg.content_type_hint is None

    def test_segment_with_all_fields(self):
        """Test creating a segment with all fields"""
        seg = ScriptSegment(
            idx=5,
            text="Figure 6 shows the results",
            intent=SegmentIntent.FIGURE_WALKTHROUGH,
            figure_refs=[6],
            key_concepts=["error compensation", "IMU"],
            visual_direction="Show the figure prominently",
            estimated_duration_sec=30.0,
            importance_score=0.9,
            audio_file="audio_005.mp3",
            actual_duration_sec=28.5,
            visual_asset_id="img_0005",
            display_mode="figure_sync",
        )
        assert seg.idx == 5
        assert seg.figure_refs == [6]
        assert seg.display_mode == "figure_sync"
        assert seg.audio_file == "audio_005.mp3"

    def test_segment_serialization_roundtrip(self):
        """Test that segments serialize and deserialize correctly"""
        original = ScriptSegment(
            idx=3,
            text="Test segment",
            intent=SegmentIntent.KEY_FINDING,
            figure_refs=[1, 2],
            importance_score=0.8,
        )
        data = original.to_dict()
        restored = ScriptSegment.from_dict(data)

        assert restored.idx == original.idx
        assert restored.text == original.text
        assert restored.intent == original.intent
        assert restored.figure_refs == original.figure_refs
        assert restored.importance_score == original.importance_score


class TestFigureInventory:
    """Test FigureInventory dataclass"""

    def test_figure_inventory_creation(self):
        """Test creating a figure inventory entry"""
        fig = FigureInventory(
            figure_number=6,
            kb_path="figures/fig_005.png",
            caption="Error compensation comparison",
            description="A bar chart showing error rates",
            discussed_in_segments=[22, 23],
        )
        assert fig.figure_number == 6
        assert fig.kb_path == "figures/fig_005.png"
        assert 22 in fig.discussed_in_segments


class TestStructuredScript:
    """Test StructuredScript dataclass"""

    def test_empty_script(self):
        """Test creating an empty script"""
        script = StructuredScript(
            script_id="trial_000_v1",
            trial_id="trial_000",
        )
        assert script.script_id == "trial_000_v1"
        assert script.segments == []
        assert script.total_segments == 0

    def test_script_with_segments(self):
        """Test script with multiple segments"""
        segments = [
            ScriptSegment(idx=0, text="Welcome", intent=SegmentIntent.INTRO),
            ScriptSegment(idx=1, text="Background info", intent=SegmentIntent.BACKGROUND),
            ScriptSegment(idx=2, text="Figure 1 shows", intent=SegmentIntent.FIGURE_WALKTHROUGH, figure_refs=[1]),
            ScriptSegment(idx=3, text="Thanks for watching", intent=SegmentIntent.OUTRO),
        ]

        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
            total_segments=4,
        )

        assert len(script.segments) == 4
        assert script.get_segment(0).text == "Welcome"
        assert script.get_segment(2).figure_refs == [1]

    def test_get_figure_segments(self):
        """Test filtering segments that reference figures"""
        segments = [
            ScriptSegment(idx=0, text="Intro"),
            ScriptSegment(idx=1, text="Figure 6 shows", figure_refs=[6]),
            ScriptSegment(idx=2, text="More text"),
            ScriptSegment(idx=3, text="Figure 9 shows", figure_refs=[9]),
        ]
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        figure_segs = script.get_figure_segments()
        assert len(figure_segs) == 2
        assert figure_segs[0].idx == 1
        assert figure_segs[1].idx == 3

    def test_get_segments_by_intent(self):
        """Test filtering segments by intent"""
        segments = [
            ScriptSegment(idx=0, text="Intro", intent=SegmentIntent.INTRO),
            ScriptSegment(idx=1, text="Background", intent=SegmentIntent.BACKGROUND),
            ScriptSegment(idx=2, text="Finding 1", intent=SegmentIntent.KEY_FINDING),
            ScriptSegment(idx=3, text="Finding 2", intent=SegmentIntent.KEY_FINDING),
        ]
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        findings = script.get_segments_by_intent(SegmentIntent.KEY_FINDING)
        assert len(findings) == 2

    def test_update_segment(self):
        """Test updating segment fields"""
        segments = [ScriptSegment(idx=0, text="Test")]
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        result = script.update_segment(0, audio_file="audio_000.mp3", actual_duration_sec=30.0)
        assert result is True
        assert script.get_segment(0).audio_file == "audio_000.mp3"

    def test_serialization_roundtrip(self):
        """Test full script serialization and deserialization"""
        segments = [
            ScriptSegment(idx=0, text="Welcome", intent=SegmentIntent.INTRO),
            ScriptSegment(idx=1, text="Figure 6 shows", intent=SegmentIntent.FIGURE_WALKTHROUGH, figure_refs=[6]),
        ]
        figure_inventory = {
            6: FigureInventory(
                figure_number=6,
                kb_path="figures/fig_005.png",
                caption="Test caption",
                discussed_in_segments=[1],
            )
        }

        original = StructuredScript(
            script_id="trial_000_v1",
            trial_id="trial_000",
            version=1,
            segments=segments,
            figure_inventory=figure_inventory,
            total_segments=2,
            source_document="test.pdf",
        )

        # Roundtrip via dict
        data = original.to_dict()
        restored = StructuredScript.from_dict(data)

        assert restored.script_id == original.script_id
        assert len(restored.segments) == 2
        assert restored.segments[1].figure_refs == [6]
        assert 6 in restored.figure_inventory
        assert restored.figure_inventory[6].kb_path == "figures/fig_005.png"

    def test_json_roundtrip(self):
        """Test JSON string serialization"""
        original = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[ScriptSegment(idx=0, text="Hello")],
        )

        json_str = original.to_json()
        restored = StructuredScript.from_json(json_str)

        assert restored.script_id == original.script_id
        assert restored.segments[0].text == "Hello"

    def test_file_save_and_load(self):
        """Test saving and loading from file"""
        original = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[ScriptSegment(idx=0, text="Hello")],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "script.json"
            original.save(path)

            assert path.exists()

            restored = StructuredScript.load(path)
            assert restored.script_id == original.script_id

    def test_to_flat_text(self):
        """Test exporting as flat text for backward compatibility"""
        segments = [
            ScriptSegment(idx=0, text="Paragraph one"),
            ScriptSegment(idx=1, text="Paragraph two"),
            ScriptSegment(idx=2, text="Paragraph three"),
        ]
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        flat = script.to_flat_text()
        assert "Paragraph one\n\nParagraph two\n\nParagraph three" == flat


class TestFromScriptText:
    """Test the from_script_text migration method"""

    def test_parse_simple_script(self):
        """Test parsing a simple script"""
        script_text = """Welcome to the show.

This is the background section.

Here are the key findings.

Thanks for listening."""

        result = StructuredScript.from_script_text(script_text, "trial_000")

        assert result.trial_id == "trial_000"
        assert result.total_segments == 4
        assert result.segments[0].text == "Welcome to the show."
        assert result.segments[0].intent == SegmentIntent.INTRO
        assert result.segments[3].intent == SegmentIntent.OUTRO

    def test_parse_figure_references(self):
        """Test parsing figure references from script"""
        script_text = """Welcome to the show.

Let me explain the background.

Figure 6 shows the comparison results.

Figure 9 addresses the runtime issue.

Thanks for listening."""

        result = StructuredScript.from_script_text(script_text, "trial_000")

        # Check figure detection
        assert result.segments[2].figure_refs == [6]
        assert result.segments[3].figure_refs == [9]

        # Check intent classification
        assert result.segments[2].intent == SegmentIntent.FIGURE_WALKTHROUGH
        assert result.segments[3].intent == SegmentIntent.FIGURE_WALKTHROUGH

        # Check figure inventory
        assert 6 in result.figure_inventory
        assert 9 in result.figure_inventory
        assert 2 in result.figure_inventory[6].discussed_in_segments
        assert 3 in result.figure_inventory[9].discussed_in_segments

    def test_parse_with_kb_figures(self):
        """Test parsing with KB figure paths provided"""
        script_text = """Intro paragraph.

Figure 6 shows the results."""

        kb_figures = {
            6: "figures/fig_005.png",
            9: "figures/fig_008.png",
        }

        result = StructuredScript.from_script_text(script_text, "trial_000", kb_figures)

        assert result.figure_inventory[6].kb_path == "figures/fig_005.png"

    def test_parse_with_rich_kb_figures(self):
        """Test parsing with rich KB figure metadata (path + caption + description)"""
        script_text = """Intro paragraph.

Figure 6 shows the neural network architecture."""

        # New format: Dict[int, dict] with full metadata
        kb_figures = {
            6: {
                "kb_path": "figures/fig_005.png",
                "caption": "Neural network architecture diagram",
                "description": "Shows the encoder-decoder structure with attention layers",
            },
        }

        result = StructuredScript.from_script_text(script_text, "trial_000", kb_figures)

        fig = result.figure_inventory[6]
        assert fig.kb_path == "figures/fig_005.png"
        assert fig.caption == "Neural network architecture diagram"
        assert fig.description == "Shows the encoder-decoder structure with attention layers"
        assert 1 in fig.discussed_in_segments

    def test_duration_estimation(self):
        """Test that duration is estimated from word count"""
        # ~150 words per minute, so 150 words = 60 seconds
        words = " ".join(["word"] * 150)
        script_text = f"Intro.\n\n{words}"

        result = StructuredScript.from_script_text(script_text, "trial_000")

        # Second paragraph should be ~60 seconds
        assert result.segments[1].estimated_duration_sec is not None
        assert 55 < result.segments[1].estimated_duration_sec < 65

    def test_importance_scoring(self):
        """Test that importance scores are assigned correctly"""
        script_text = """Welcome to the show.

Background information here.

Figure 6 shows the key results.

Thanks for listening."""

        result = StructuredScript.from_script_text(script_text, "trial_000")

        # Intro should have high importance
        assert result.segments[0].importance_score >= 0.7

        # Figure walkthrough should have highest importance
        assert result.segments[2].importance_score >= 0.9

        # Outro moderate
        assert 0.5 <= result.segments[3].importance_score <= 0.7

    def test_parse_methodology_intent(self):
        """Test that methodology keywords are detected"""
        script_text = """Intro.

The methodology uses a Kalman filter approach.

Outro."""

        result = StructuredScript.from_script_text(script_text, "trial_000")
        assert result.segments[1].intent == SegmentIntent.METHODOLOGY

    def test_parse_comparison_intent(self):
        """Test that comparison keywords are detected"""
        script_text = """Intro.

Compared to previous work, this outperforms the baseline.

Outro."""

        result = StructuredScript.from_script_text(script_text, "trial_000")
        assert result.segments[1].intent == SegmentIntent.COMPARISON

    def test_parse_real_script_excerpt(self):
        """Test parsing a real script excerpt with figure mentions"""
        script_text = """Welcome back to another deep dive into cutting-edge research.

You've probably seen those incredible drone videos flying through warehouses.

Figure 6 shows the comparison results of error compensation effects between different models on low-cost IMUs, and the performance improvements are significant.

Figure 9 addresses this directly by showing the comparison of runtime in NLOS environments across different sample sizes.

Thanks for joining me on this deep dive into adaptive multi-sensor fusion for UAV positioning."""

        result = StructuredScript.from_script_text(script_text, "trial_000")

        assert result.total_segments == 5
        assert result.segments[0].intent == SegmentIntent.INTRO
        assert result.segments[2].figure_refs == [6]
        assert result.segments[3].figure_refs == [9]
        assert result.segments[4].intent == SegmentIntent.OUTRO

        # Check figure inventory was built
        assert 6 in result.figure_inventory
        assert 9 in result.figure_inventory


# ============================================================================
# NEW CONTENT MODEL EXPANSION TESTS
# ============================================================================


class TestSourceType:
    """Test the new SourceType enum"""

    def test_source_type_values(self):
        """Test all 8 SourceType values exist"""
        assert SourceType.PAPER.value == "paper"
        assert SourceType.NEWS.value == "news"
        assert SourceType.DATASET.value == "dataset"
        assert SourceType.GOVERNMENT.value == "government"
        assert SourceType.TRANSCRIPT.value == "transcript"
        assert SourceType.NOTE.value == "note"
        assert SourceType.ARTIFACT.value == "artifact"
        assert SourceType.URL.value == "url"

    def test_source_type_count(self):
        """Test that we have exactly 8 source types"""
        assert len(SourceType) == 8


class TestSourceAttribution:
    """Test the new SourceAttribution dataclass"""

    def test_source_attribution_creation(self):
        """Test creating a source attribution with minimal fields"""
        attr = SourceAttribution(
            source_id="src_001",
            source_type=SourceType.PAPER,
        )
        assert attr.source_id == "src_001"
        assert attr.source_type == SourceType.PAPER
        assert attr.atoms_used == []
        assert attr.confidence == 1.0
        assert attr.label is None

    def test_source_attribution_with_all_fields(self):
        """Test creating a source attribution with all fields"""
        attr = SourceAttribution(
            source_id="paper_001",
            source_type=SourceType.PAPER,
            atoms_used=["atom_1", "atom_2", "atom_3"],
            confidence=0.95,
            label="Smith et al. 2024",
        )
        assert attr.source_id == "paper_001"
        assert attr.source_type == SourceType.PAPER
        assert attr.atoms_used == ["atom_1", "atom_2", "atom_3"]
        assert attr.confidence == 0.95
        assert attr.label == "Smith et al. 2024"

    def test_source_attribution_to_dict(self):
        """Test serializing source attribution to dict"""
        attr = SourceAttribution(
            source_id="src_001",
            source_type=SourceType.NEWS,
            atoms_used=["atom_1"],
            confidence=0.85,
            label="Breaking News",
        )
        data = attr.to_dict()

        assert data["source_id"] == "src_001"
        assert data["source_type"] == "news"
        assert data["atoms_used"] == ["atom_1"]
        assert data["confidence"] == 0.85
        assert data["label"] == "Breaking News"

    def test_source_attribution_from_dict(self):
        """Test deserializing source attribution from dict"""
        data = {
            "source_id": "src_002",
            "source_type": "dataset",
            "atoms_used": ["atom_a", "atom_b"],
            "confidence": 0.9,
            "label": "UCI ML Repo",
        }
        attr = SourceAttribution.from_dict(data)

        assert attr.source_id == "src_002"
        assert attr.source_type == SourceType.DATASET
        assert attr.atoms_used == ["atom_a", "atom_b"]
        assert attr.confidence == 0.9
        assert attr.label == "UCI ML Repo"

    def test_source_attribution_roundtrip(self):
        """Test serialization roundtrip for source attribution"""
        original = SourceAttribution(
            source_id="paper_123",
            source_type=SourceType.PAPER,
            atoms_used=["fig_1", "sec_2"],
            confidence=0.88,
            label="Key Reference",
        )

        data = original.to_dict()
        restored = SourceAttribution.from_dict(data)

        assert restored.source_id == original.source_id
        assert restored.source_type == original.source_type
        assert restored.atoms_used == original.atoms_used
        assert restored.confidence == original.confidence
        assert restored.label == original.label

    def test_source_attribution_from_dict_with_defaults(self):
        """Test deserializing with missing optional fields"""
        data = {
            "source_id": "src_min",
            "source_type": "note",
        }
        attr = SourceAttribution.from_dict(data)

        assert attr.source_id == "src_min"
        assert attr.source_type == SourceType.NOTE
        assert attr.atoms_used == []
        assert attr.confidence == 1.0
        assert attr.label is None


class TestScriptSegmentNewFields:
    """Test new fields in ScriptSegment"""

    def test_segment_with_source_attributions(self):
        """Test segment with source attributions"""
        attr1 = SourceAttribution(
            source_id="paper_001",
            source_type=SourceType.PAPER,
            label="Smith et al.",
        )
        attr2 = SourceAttribution(
            source_id="dataset_001",
            source_type=SourceType.DATASET,
        )
        seg = ScriptSegment(
            idx=0,
            text="This segment uses multiple sources",
            source_attributions=[attr1, attr2],
        )

        assert len(seg.source_attributions) == 2
        assert seg.source_attributions[0].source_id == "paper_001"
        assert seg.source_attributions[1].source_type == SourceType.DATASET

    def test_segment_with_perspective(self):
        """Test segment with perspective field"""
        seg = ScriptSegment(
            idx=0,
            text="This is a biased view",
            perspective="left_0.3",
        )
        assert seg.perspective == "left_0.3"

    def test_segment_with_content_type_hint(self):
        """Test segment with content type hint"""
        seg = ScriptSegment(
            idx=0,
            text="News content",
            content_type_hint="news",
        )
        assert seg.content_type_hint == "news"

    def test_segment_serialization_with_new_fields(self):
        """Test serialization of segment with new fields"""
        attr = SourceAttribution(
            source_id="src_1",
            source_type=SourceType.PAPER,
            atoms_used=["atom_1"],
            confidence=0.9,
        )
        seg = ScriptSegment(
            idx=5,
            text="Complex segment",
            intent=SegmentIntent.ANALYSIS,
            source_attributions=[attr],
            perspective="neutral",
            content_type_hint="research",
        )

        data = seg.to_dict()
        assert len(data["source_attributions"]) == 1
        assert data["source_attributions"][0]["source_id"] == "src_1"
        assert data["perspective"] == "neutral"
        assert data["content_type_hint"] == "research"

    def test_segment_deserialization_with_new_fields(self):
        """Test deserialization of segment with new fields"""
        data = {
            "idx": 3,
            "text": "Test content",
            "intent": "analysis",
            "source_attributions": [
                {
                    "source_id": "src_001",
                    "source_type": "paper",
                    "atoms_used": ["a1", "a2"],
                    "confidence": 0.95,
                    "label": "Ref",
                }
            ],
            "perspective": "left_0.5",
            "content_type_hint": "policy",
        }

        seg = ScriptSegment.from_dict(data)
        assert seg.idx == 3
        assert len(seg.source_attributions) == 1
        assert seg.source_attributions[0].label == "Ref"
        assert seg.perspective == "left_0.5"
        assert seg.content_type_hint == "policy"

    def test_segment_backward_compatibility_without_source_attributions(self):
        """Test that segments without source attributions still work"""
        data = {
            "idx": 0,
            "text": "Old format segment",
        }
        seg = ScriptSegment.from_dict(data)

        assert seg.source_attributions == []
        assert seg.perspective is None
        assert seg.content_type_hint is None


class TestStructuredScriptNewFields:
    """Test new fields in StructuredScript"""

    def test_script_with_sources_used(self):
        """Test script with sources_used field"""
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            sources_used=["paper_001", "paper_002", "dataset_001"],
        )
        assert script.sources_used == ["paper_001", "paper_002", "dataset_001"]

    def test_script_with_content_type(self):
        """Test script with content_type field"""
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            content_type="news",
        )
        assert script.content_type == "news"

    def test_script_with_production_style(self):
        """Test script with production_style field"""
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            production_style="news_analysis",
        )
        assert script.production_style == "news_analysis"

    def test_script_with_perspective(self):
        """Test script with perspective field"""
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            perspective="right_0.4",
        )
        assert script.perspective == "right_0.4"

    def test_script_with_variant_of(self):
        """Test script with variant_of field (for bias variants)"""
        script = StructuredScript(
            script_id="test_v1_left",
            trial_id="test",
            variant_of="test_v1_base",
        )
        assert script.variant_of == "test_v1_base"

    def test_script_default_values(self):
        """Test that new fields have sensible defaults"""
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
        )
        assert script.sources_used == []
        assert script.content_type == "research"
        assert script.production_style == "explainer"
        assert script.perspective is None
        assert script.variant_of is None

    def test_script_serialization_with_new_fields(self):
        """Test serialization of script with new fields"""
        script = StructuredScript(
            script_id="trial_001_v1",
            trial_id="trial_001",
            sources_used=["src_1", "src_2"],
            content_type="policy",
            production_style="debate",
            perspective="neutral",
            variant_of="trial_001_base",
        )

        data = script.to_dict()
        assert data["sources_used"] == ["src_1", "src_2"]
        assert data["content_type"] == "policy"
        assert data["production_style"] == "debate"
        assert data["perspective"] == "neutral"
        assert data["variant_of"] == "trial_001_base"

    def test_script_deserialization_with_new_fields(self):
        """Test deserialization of script with new fields"""
        data = {
            "script_id": "trial_002_v1",
            "trial_id": "trial_002",
            "sources_used": ["paper_a", "paper_b", "dataset_c"],
            "content_type": "mixed",
            "production_style": "narrative",
            "perspective": "left_0.6",
            "variant_of": "trial_002_baseline",
        }

        script = StructuredScript.from_dict(data)
        assert script.sources_used == ["paper_a", "paper_b", "dataset_c"]
        assert script.content_type == "mixed"
        assert script.production_style == "narrative"
        assert script.perspective == "left_0.6"
        assert script.variant_of == "trial_002_baseline"


class TestGetSegmentsBySource:
    """Test the new get_segments_by_source() method"""

    def test_get_segments_by_source_single_source(self):
        """Test retrieving segments from a single source"""
        attr1 = SourceAttribution(source_id="paper_001", source_type=SourceType.PAPER)
        attr2 = SourceAttribution(source_id="paper_002", source_type=SourceType.PAPER)

        segments = [
            ScriptSegment(idx=0, text="From paper 1", source_attributions=[attr1]),
            ScriptSegment(idx=1, text="From paper 2", source_attributions=[attr2]),
            ScriptSegment(idx=2, text="Also from paper 1", source_attributions=[attr1]),
        ]

        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        paper1_segs = script.get_segments_by_source("paper_001")
        assert len(paper1_segs) == 2
        assert paper1_segs[0].idx == 0
        assert paper1_segs[1].idx == 2

    def test_get_segments_by_source_not_found(self):
        """Test querying for a source that doesn't exist"""
        attr = SourceAttribution(source_id="paper_001", source_type=SourceType.PAPER)
        segments = [
            ScriptSegment(idx=0, text="Content", source_attributions=[attr]),
        ]

        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        result = script.get_segments_by_source("nonexistent")
        assert result == []

    def test_get_segments_by_source_multiple_sources_per_segment(self):
        """Test segments that draw from multiple sources"""
        attr1 = SourceAttribution(source_id="paper_001", source_type=SourceType.PAPER)
        attr2 = SourceAttribution(source_id="news_001", source_type=SourceType.NEWS)

        segments = [
            ScriptSegment(
                idx=0,
                text="Multi-source content",
                source_attributions=[attr1, attr2],
            ),
        ]

        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        # Both sources should return this segment
        paper_segs = script.get_segments_by_source("paper_001")
        news_segs = script.get_segments_by_source("news_001")

        assert len(paper_segs) == 1
        assert len(news_segs) == 1
        assert paper_segs[0].idx == news_segs[0].idx


class TestGetSourcesSummary:
    """Test the new get_sources_summary() method"""

    def test_get_sources_summary_single_source(self):
        """Test sources summary with single source"""
        attr = SourceAttribution(source_id="paper_001", source_type=SourceType.PAPER)
        segments = [
            ScriptSegment(idx=0, text="Content 1", source_attributions=[attr]),
            ScriptSegment(idx=1, text="Content 2", source_attributions=[attr]),
        ]

        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        summary = script.get_sources_summary()
        assert summary == {"paper_001": 2}

    def test_get_sources_summary_multiple_sources(self):
        """Test sources summary with multiple sources"""
        attr1 = SourceAttribution(source_id="paper_001", source_type=SourceType.PAPER)
        attr2 = SourceAttribution(source_id="paper_002", source_type=SourceType.PAPER)
        attr3 = SourceAttribution(source_id="dataset_001", source_type=SourceType.DATASET)

        segments = [
            ScriptSegment(idx=0, text="Content 1", source_attributions=[attr1]),
            ScriptSegment(idx=1, text="Content 2", source_attributions=[attr2]),
            ScriptSegment(idx=2, text="Content 3", source_attributions=[attr1, attr3]),
            ScriptSegment(idx=3, text="Content 4", source_attributions=[attr2]),
        ]

        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        summary = script.get_sources_summary()
        assert summary["paper_001"] == 2
        assert summary["paper_002"] == 2
        assert summary["dataset_001"] == 1

    def test_get_sources_summary_empty_script(self):
        """Test sources summary on empty script"""
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
        )

        summary = script.get_sources_summary()
        assert summary == {}

    def test_get_sources_summary_segments_without_sources(self):
        """Test sources summary when segments have no source attributions"""
        segments = [
            ScriptSegment(idx=0, text="Content 1"),
            ScriptSegment(idx=1, text="Content 2"),
        ]

        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
        )

        summary = script.get_sources_summary()
        assert summary == {}


class TestIntentClassificationNewVocabulary:
    """Test _classify_intent() with new vocabulary"""

    def test_classify_context_from_keywords(self):
        """Test CONTEXT intent classification"""
        text = "The background and context of this problem are important."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.CONTEXT

    def test_classify_explanation_from_keywords(self):
        """Test EXPLANATION intent classification"""
        text = "The methodology employs a novel algorithm that works by..."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.EXPLANATION

    def test_classify_definition_from_keywords(self):
        """Test DEFINITION intent classification"""
        text = "Resilience is defined as the ability to recover quickly."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.DEFINITION

    def test_classify_narrative_from_keywords(self):
        """Test NARRATIVE intent classification"""
        text = "The story began when researchers started investigating this problem."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.NARRATIVE

    def test_classify_claim_from_keywords(self):
        """Test CLAIM intent classification"""
        text = "Our results demonstrate that this approach is superior."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.CLAIM

    def test_classify_evidence_from_keywords(self):
        """Test EVIDENCE intent classification"""
        text = "According to recent studies, research indicates that..."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.EVIDENCE

    def test_classify_data_walkthrough_from_keywords(self):
        """Test DATA_WALKTHROUGH intent classification"""
        text = "Looking at the dataset, we see metrics across different samples."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.DATA_WALKTHROUGH

    def test_classify_figure_reference_from_presence(self):
        """Test FIGURE_REFERENCE intent classification"""
        intent = StructuredScript._classify_intent("Text", 1, 5, [1])
        assert intent == SegmentIntent.FIGURE_REFERENCE

    def test_classify_analysis_from_keywords(self):
        """Test ANALYSIS intent classification"""
        text = "This means that our interpretation of the patterns is valid."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.ANALYSIS

    def test_classify_comparison_from_keywords(self):
        """Test COMPARISON intent classification"""
        text = "Compared to previous methods, our approach outperforms in speed."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.COMPARISON

    def test_classify_counterpoint_from_keywords(self):
        """Test COUNTERPOINT intent classification"""
        text = "On the other hand, opposing views suggest a different approach."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.COUNTERPOINT

    def test_classify_synthesis_from_keywords(self):
        """Test SYNTHESIS intent classification"""
        text = "Overall, when taking these elements together, we see a synthesis."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.SYNTHESIS

    def test_classify_commentary_from_keywords(self):
        """Test COMMENTARY intent classification"""
        text = "What's notably fascinating is how this connects to earlier work."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.COMMENTARY

    def test_classify_question_from_keywords(self):
        """Test QUESTION intent classification"""
        text = "Why does this phenomenon occur? What are the mechanisms involved?"
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.QUESTION

    def test_classify_speculation_from_keywords(self):
        """Test SPECULATION intent classification"""
        text = "In the future, this might enable new applications."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.SPECULATION

    def test_classify_transition_from_keywords(self):
        """Test TRANSITION intent classification"""
        text = "Now let's move to the next phase of this research."
        intent = StructuredScript._classify_intent(text, 1, 5, [])
        assert intent == SegmentIntent.TRANSITION


class TestImportanceScoreNewIntents:
    """Test _calculate_importance() with new intent vocabulary"""

    def test_importance_intro_high(self):
        """Test INTRO has high importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.INTRO, [])
        assert score >= 0.7

    def test_importance_figure_reference_highest(self):
        """Test FIGURE_REFERENCE has highest importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.FIGURE_REFERENCE, [1])
        assert score == 1.0

    def test_importance_claim_high(self):
        """Test CLAIM has high importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.CLAIM, [])
        assert score >= 0.8

    def test_importance_transition_low(self):
        """Test TRANSITION has low importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.TRANSITION, [])
        assert score <= 0.3

    def test_importance_context_moderate(self):
        """Test CONTEXT has moderate importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.CONTEXT, [])
        assert 0.3 <= score <= 0.5

    def test_importance_explanation_medium_high(self):
        """Test EXPLANATION has medium-high importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.EXPLANATION, [])
        assert score >= 0.6

    def test_importance_analysis_medium_high(self):
        """Test ANALYSIS has medium-high importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.ANALYSIS, [])
        assert score >= 0.6

    def test_importance_question_low(self):
        """Test QUESTION has low importance"""
        score = StructuredScript._calculate_importance("Text", SegmentIntent.QUESTION, [])
        assert score <= 0.5

    def test_importance_word_count_boost(self):
        """Test that longer content gets importance boost"""
        short_text = "Short text"
        long_text = " ".join(["word"] * 200)  # Over 150 words

        short_score = StructuredScript._calculate_importance(short_text, SegmentIntent.ANALYSIS, [])
        long_score = StructuredScript._calculate_importance(long_text, SegmentIntent.ANALYSIS, [])

        # Longer text should have higher importance
        assert long_score > short_score

    def test_importance_figure_boost(self):
        """Test that figure references boost importance"""
        no_fig_score = StructuredScript._calculate_importance("Text", SegmentIntent.EVIDENCE, [])
        fig_score = StructuredScript._calculate_importance("Text", SegmentIntent.EVIDENCE, [1])

        # With figure should be higher
        assert fig_score > no_fig_score

    def test_importance_capped_at_one(self):
        """Test that importance score never exceeds 1.0"""
        # Figure reference alone is already 1.0, can't go higher
        score = StructuredScript._calculate_importance(
            " ".join(["word"] * 500),  # Very long
            SegmentIntent.FIGURE_REFERENCE,
            [1, 2, 3],  # Multiple figures
        )
        assert score <= 1.0


class TestComprehensiveScriptWithNewModel:
    """Integration tests for complete scripts using new model"""

    def test_build_script_with_multiple_sources(self):
        """Test building a complete script with multiple source attributions"""
        paper_attr = SourceAttribution(
            source_id="paper_001",
            source_type=SourceType.PAPER,
            atoms_used=["fig_1"],
            confidence=0.95,
            label="Smith et al. 2024",
        )
        dataset_attr = SourceAttribution(
            source_id="dataset_001",
            source_type=SourceType.DATASET,
            atoms_used=["subset_a"],
            confidence=0.88,
        )

        segments = [
            ScriptSegment(
                idx=0,
                text="Welcome to this analysis.",
                intent=SegmentIntent.INTRO,
            ),
            ScriptSegment(
                idx=1,
                text="We analyzed data from multiple sources.",
                intent=SegmentIntent.CONTEXT,
                source_attributions=[paper_attr, dataset_attr],
            ),
            ScriptSegment(
                idx=2,
                text="Figure 1 shows the comparison.",
                intent=SegmentIntent.FIGURE_REFERENCE,
                figure_refs=[1],
                source_attributions=[paper_attr],
            ),
            ScriptSegment(
                idx=3,
                text="Concluding remarks.",
                intent=SegmentIntent.OUTRO,
            ),
        ]

        script = StructuredScript(
            script_id="comprehensive_test_v1",
            trial_id="comprehensive_test",
            segments=segments,
            sources_used=["paper_001", "dataset_001"],
            content_type="research",
            production_style="explainer",
            perspective="neutral",
        )

        # Verify structure
        assert len(script.segments) == 4
        assert script.get_segments_by_source("paper_001") == [segments[1], segments[2]]
        assert script.get_segments_by_source("dataset_001") == [segments[1]]

        summary = script.get_sources_summary()
        assert summary["paper_001"] == 2
        assert summary["dataset_001"] == 1

    def test_roundtrip_comprehensive_script(self):
        """Test serialization roundtrip for comprehensive script"""
        attr = SourceAttribution(
            source_id="src_001",
            source_type=SourceType.PAPER,
            atoms_used=["atom_1"],
            confidence=0.9,
            label="Reference",
        )

        original = StructuredScript(
            script_id="trip_test_v1",
            trial_id="trip_test",
            segments=[
                ScriptSegment(
                    idx=0,
                    text="Content",
                    intent=SegmentIntent.EXPLANATION,
                    source_attributions=[attr],
                    perspective="neutral",
                    content_type_hint="research",
                ),
            ],
            sources_used=["src_001"],
            content_type="mixed",
            production_style="narrative",
            perspective="academic",
            variant_of="base_version",
        )

        # JSON roundtrip
        json_str = original.to_json()
        restored = StructuredScript.from_json(json_str)

        # Verify all new fields survived
        assert restored.sources_used == original.sources_used
        assert restored.content_type == original.content_type
        assert restored.production_style == original.production_style
        assert restored.perspective == original.perspective
        assert restored.variant_of == original.variant_of
        assert len(restored.segments[0].source_attributions) == 1
        assert restored.segments[0].source_attributions[0].label == "Reference"

    def test_script_from_text_with_intent_classification(self):
        """Test parsing text that exercises multiple intent classifications"""
        script_text = """Welcome to the analysis.

The background and context of this problem are important.

Our methodology employs advanced techniques.

Figure 1 demonstrates the key finding compared to previous approaches.

On the other hand, there are opposing views to consider.

Combining these elements together creates a synthesis of approaches.

Thank you for your attention."""

        result = StructuredScript.from_script_text(script_text, "intent_test")

        # Verify intents were classified with new vocabulary
        assert result.segments[0].intent == SegmentIntent.INTRO
        assert result.segments[1].intent == SegmentIntent.CONTEXT
        assert result.segments[2].intent == SegmentIntent.EXPLANATION
        assert result.segments[3].intent == SegmentIntent.FIGURE_REFERENCE
        assert result.segments[4].intent == SegmentIntent.COUNTERPOINT
        assert result.segments[5].intent == SegmentIntent.SYNTHESIS
        assert result.segments[6].intent == SegmentIntent.OUTRO
