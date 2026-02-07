"""Unit tests for StructuredScript models"""

import json
import pytest
from pathlib import Path
import tempfile

from core.models.structured_script import (
    SegmentIntent,
    FigureInventory,
    ScriptSegment,
    StructuredScript,
)


class TestSegmentIntent:
    """Test SegmentIntent enum"""

    def test_segment_intent_values(self):
        """Test that SegmentIntent has expected values"""
        assert SegmentIntent.INTRO.value == "intro"
        assert SegmentIntent.BACKGROUND.value == "background"
        assert SegmentIntent.METHODOLOGY.value == "methodology"
        assert SegmentIntent.KEY_FINDING.value == "key_finding"
        assert SegmentIntent.FIGURE_WALKTHROUGH.value == "figure_walkthrough"
        assert SegmentIntent.DATA_DISCUSSION.value == "data_discussion"
        assert SegmentIntent.COMPARISON.value == "comparison"
        assert SegmentIntent.TRANSITION.value == "transition"
        assert SegmentIntent.RECAP.value == "recap"
        assert SegmentIntent.OUTRO.value == "outro"

    def test_segment_intent_count(self):
        """Test that we have the expected number of intents"""
        assert len(SegmentIntent) == 10


class TestScriptSegment:
    """Test ScriptSegment dataclass"""

    def test_segment_creation(self):
        """Test creating a segment with minimal fields"""
        seg = ScriptSegment(idx=0, text="Hello world")
        assert seg.idx == 0
        assert seg.text == "Hello world"
        assert seg.intent == SegmentIntent.BACKGROUND
        assert seg.figure_refs == []
        assert seg.importance_score == 0.5

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
