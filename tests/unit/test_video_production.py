"""Unit tests for core.video_production scene conversion functions."""

import pytest

from core.models.structured_script import (
    ScriptSegment,
    SegmentIntent,
    StructuredScript,
)
from core.training.models import SegmentType
from core.video_production import (
    INTENT_TO_SEGMENT_TYPE,
    INTENT_TO_VISUAL_KEY,
    SEGMENT_VISUAL_MAPPING,
    structured_script_to_scenes,
)


def _make_script(segments):
    """Helper to create a StructuredScript from segment dicts."""
    script_segments = []
    for s in segments:
        script_segments.append(ScriptSegment(
            idx=s["idx"],
            text=s.get("text", "Some default text for testing purposes."),
            intent=s.get("intent", SegmentIntent.CONTEXT),
            key_concepts=s.get("key_concepts", []),
            figure_refs=s.get("figure_refs", []),
            actual_duration_sec=s.get("actual_duration_sec"),
            estimated_duration_sec=s.get("estimated_duration_sec"),
        ))
    return StructuredScript(
        script_id="test_script",
        trial_id="trial_000",
        segments=script_segments,
    )


class TestStructuredScriptToScenes:
    """Tests for structured_script_to_scenes."""

    def test_basic_conversion(self):
        """Should create one scene per non-transition segment."""
        script = _make_script([
            {"idx": 0, "text": "Welcome to the podcast", "intent": SegmentIntent.INTRO},
            {"idx": 1, "text": "Some background context here", "intent": SegmentIntent.CONTEXT},
            {"idx": 2, "text": "The key finding is important", "intent": SegmentIntent.CLAIM},
        ])
        scenes = structured_script_to_scenes(script)
        assert len(scenes) == 3

    def test_skips_transitions(self):
        """TRANSITION segments should not create scenes."""
        script = _make_script([
            {"idx": 0, "text": "Welcome to the podcast", "intent": SegmentIntent.INTRO},
            {"idx": 1, "text": "Moving on to the next topic", "intent": SegmentIntent.TRANSITION},
            {"idx": 2, "text": "The key finding is important", "intent": SegmentIntent.CLAIM},
        ])
        scenes = structured_script_to_scenes(script)
        assert len(scenes) == 2
        assert scenes[0].scene_id == "scene_000"
        assert scenes[1].scene_id == "scene_002"

    def test_scene_ids_match_segment_idx(self):
        """scene_id should be scene_{seg.idx:03d}, matching DoP visual plan naming."""
        script = _make_script([
            {"idx": 0, "text": "First segment text here"},
            {"idx": 1, "text": "Second segment text here"},
            {"idx": 2, "text": "Third segment text here"},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].scene_id == "scene_000"
        assert scenes[1].scene_id == "scene_001"
        assert scenes[2].scene_id == "scene_002"

    def test_timing_from_actual_duration(self):
        """Should use actual_duration_sec when available."""
        script = _make_script([
            {"idx": 0, "text": "First", "actual_duration_sec": 10.0},
            {"idx": 1, "text": "Second", "actual_duration_sec": 20.0},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].start_time == 0.0
        assert scenes[0].end_time == 10.0
        assert scenes[1].start_time == 10.0
        assert scenes[1].end_time == 30.0

    def test_timing_from_estimated_duration(self):
        """Should fall back to estimated_duration_sec."""
        script = _make_script([
            {"idx": 0, "text": "First", "estimated_duration_sec": 15.0},
            {"idx": 1, "text": "Second", "estimated_duration_sec": 25.0},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].end_time == 15.0
        assert scenes[1].start_time == 15.0
        assert scenes[1].end_time == 40.0

    def test_timing_from_text_length(self):
        """Should estimate duration from word count at ~150 WPM when no duration available."""
        # 30 words at 150 WPM = 12 seconds, but minimum is 5.0
        text = " ".join(["word"] * 30)
        script = _make_script([
            {"idx": 0, "text": text},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].start_time == 0.0
        assert scenes[0].end_time == 12.0  # 30 words / 2.5 WPS

    def test_timing_minimum_duration(self):
        """Short text should get minimum 5s duration."""
        script = _make_script([
            {"idx": 0, "text": "Short"},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].end_time - scenes[0].start_time >= 5.0

    def test_intent_to_segment_type_mapping(self):
        """Each intent should map to a valid SegmentType."""
        script = _make_script([
            {"idx": 0, "text": "Intro text", "intent": SegmentIntent.INTRO},
            {"idx": 1, "text": "Context text", "intent": SegmentIntent.CONTEXT},
            {"idx": 2, "text": "Claim text", "intent": SegmentIntent.CLAIM},
            {"idx": 3, "text": "Figure ref", "intent": SegmentIntent.FIGURE_REFERENCE},
            {"idx": 4, "text": "Outro text", "intent": SegmentIntent.OUTRO},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].segment_type == SegmentType.INTRO
        assert scenes[1].segment_type == SegmentType.BACKGROUND
        assert scenes[2].segment_type == SegmentType.KEY_FINDING
        assert scenes[3].segment_type == SegmentType.FIGURE_DISCUSSION
        assert scenes[4].segment_type == SegmentType.CONCLUSION

    def test_visual_mapping_applied(self):
        """Visual complexity and animation flags should come from mapping."""
        script = _make_script([
            {"idx": 0, "text": "A key finding text", "intent": SegmentIntent.CLAIM},
        ])
        scenes = structured_script_to_scenes(script)
        # KEY_FINDING mapping has visual_complexity="high", animation_candidate=True
        assert scenes[0].visual_complexity == "high"
        assert scenes[0].animation_candidate is True

    def test_key_concepts_preserved(self):
        """key_concepts from segment should be copied to scene."""
        script = _make_script([
            {"idx": 0, "text": "About GPS", "key_concepts": ["GPS positioning", "satellite navigation"]},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].key_concepts == ["GPS positioning", "satellite navigation"]
        assert scenes[0].title == "GPS positioning"

    def test_title_fallback_from_text(self):
        """When no key_concepts, title should come from text snippet."""
        script = _make_script([
            {"idx": 0, "text": "The quick brown fox jumps over the lazy dog today"},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].title_is_fallback is True
        assert "quick brown fox" in scenes[0].title

    def test_figure_refs_converted(self):
        """figure_refs (int list) should become referenced_figures (string list)."""
        script = _make_script([
            {"idx": 0, "text": "See figure 1", "figure_refs": [1, 3]},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].referenced_figures == ["Figure 1", "Figure 3"]

    def test_transcript_segment_is_text(self):
        """transcript_segment should be the segment text."""
        script = _make_script([
            {"idx": 0, "text": "The actual narration text goes here"},
        ])
        scenes = structured_script_to_scenes(script)
        assert scenes[0].transcript_segment == "The actual narration text goes here"


class TestIntentMappings:
    """Tests for intent mapping completeness."""

    def test_all_intents_have_visual_key(self):
        """Every SegmentIntent should have a SEGMENT_VISUAL_MAPPING key."""
        for intent in SegmentIntent:
            key = INTENT_TO_VISUAL_KEY.get(intent.value)
            assert key is not None, f"SegmentIntent.{intent.name} missing from INTENT_TO_VISUAL_KEY"
            assert key in SEGMENT_VISUAL_MAPPING, f"INTENT_TO_VISUAL_KEY[{intent.value}]={key} not in SEGMENT_VISUAL_MAPPING"

    def test_all_intents_have_segment_type(self):
        """Every SegmentIntent should map to a SegmentType."""
        for intent in SegmentIntent:
            seg_type = INTENT_TO_SEGMENT_TYPE.get(intent)
            assert seg_type is not None, f"SegmentIntent.{intent.name} missing from INTENT_TO_SEGMENT_TYPE"
            assert isinstance(seg_type, SegmentType), f"INTENT_TO_SEGMENT_TYPE[{intent.name}] is not a SegmentType"
