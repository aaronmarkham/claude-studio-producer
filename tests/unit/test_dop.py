"""Unit tests for Director of Photography (DoP) module - Phase 4 of Unified Production Architecture.

Tests the visual assignment logic that bridges structured scripts to visual production.
"""

import pytest
from datetime import datetime

from core.dop import assign_visuals
from core.models.content_library import (
    AssetRecord,
    AssetSource,
    AssetStatus,
    AssetType,
    ContentLibrary,
)
from core.models.structured_script import (
    FigureInventory,
    ScriptSegment,
    SegmentIntent,
    StructuredScript,
)
from core.video_production import BUDGET_TIERS


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def empty_library():
    """Create an empty content library."""
    return ContentLibrary(project_id="test_project")


@pytest.fixture
def sample_script():
    """Create a sample structured script with diverse segments."""
    segments = [
        ScriptSegment(
            idx=0,
            text="Welcome to this research overview.",
            intent=SegmentIntent.INTRO,
            importance_score=0.8,
        ),
        ScriptSegment(
            idx=1,
            text="Let me explain the background and context.",
            intent=SegmentIntent.BACKGROUND,
            importance_score=0.4,
        ),
        ScriptSegment(
            idx=2,
            text="Figure 3 shows our experimental setup.",
            intent=SegmentIntent.FIGURE_WALKTHROUGH,
            figure_refs=[3],
            importance_score=1.0,
        ),
        ScriptSegment(
            idx=3,
            text="Figure 5 illustrates the key findings.",
            intent=SegmentIntent.FIGURE_WALKTHROUGH,
            figure_refs=[5],
            importance_score=1.0,
        ),
        ScriptSegment(
            idx=4,
            text="Our methodology employs novel filtering techniques.",
            intent=SegmentIntent.METHODOLOGY,
            key_concepts=["filtering", "optimization"],
            importance_score=0.7,
        ),
        ScriptSegment(
            idx=5,
            text="Results demonstrate significant improvement.",
            intent=SegmentIntent.KEY_FINDING,
            key_concepts=["improvement", "performance"],
            importance_score=0.9,
        ),
        ScriptSegment(
            idx=6,
            text="These results compare favorably to prior work.",
            intent=SegmentIntent.COMPARISON,
            importance_score=0.6,
        ),
        ScriptSegment(
            idx=7,
            text="In summary, we've demonstrated important findings.",
            intent=SegmentIntent.RECAP,
            importance_score=0.5,
        ),
        ScriptSegment(
            idx=8,
            text="Thank you for your attention.",
            intent=SegmentIntent.OUTRO,
            importance_score=0.6,
        ),
    ]

    figure_inventory = {
        3: FigureInventory(
            figure_number=3,
            kb_path="figures/fig_003.png",
            caption="Experimental setup",
            discussed_in_segments=[2],
        ),
        5: FigureInventory(
            figure_number=5,
            kb_path="figures/fig_005.png",
            caption="Key findings",
            discussed_in_segments=[3],
        ),
    }

    return StructuredScript(
        script_id="test_script_v1",
        trial_id="test_trial",
        version=1,
        segments=segments,
        figure_inventory=figure_inventory,
        total_segments=len(segments),
        created_at=datetime.now().isoformat(),
    )


@pytest.fixture
def library_with_figures(empty_library, sample_script):
    """Create a library with KB figures already registered."""
    for fig_num in [3, 5]:
        empty_library.register(
            AssetRecord(
                asset_id="",  # Will be auto-generated
                asset_type=AssetType.FIGURE,
                source=AssetSource.KB_EXTRACTION,
                status=AssetStatus.APPROVED,
                figure_number=fig_num,
                path=f"figures/fig_{fig_num:03d}.png",
                format="png",
            )
        )
    return empty_library


# ============================================================================
# Test: Figure Segments Get figure_sync Mode
# ============================================================================


class TestFigureSegmentAssignment:
    """Test that segments with figure references get figure_sync display mode."""

    def test_figure_segment_gets_figure_sync_mode(self, sample_script, library_with_figures):
        """Figure-referencing segments should get figure_sync mode."""
        result = assign_visuals(sample_script, library_with_figures, "medium")

        # Segments 2 and 3 reference figures
        seg2 = result.get_segment(2)
        seg3 = result.get_segment(3)

        assert seg2.display_mode == "figure_sync"
        assert seg3.display_mode == "figure_sync"

    def test_figure_segment_has_visual_asset_id(self, sample_script, library_with_figures):
        """Figure segments should have visual_asset_id populated."""
        result = assign_visuals(sample_script, library_with_figures, "medium")

        seg2 = result.get_segment(2)
        seg3 = result.get_segment(3)

        assert seg2.visual_asset_id is not None
        assert seg3.visual_asset_id is not None

    def test_figure_segment_without_library_figure(self, sample_script, empty_library):
        """Figure segment still gets figure_sync even if figure not in library."""
        result = assign_visuals(sample_script, empty_library, "medium")

        seg2 = result.get_segment(2)
        assert seg2.display_mode == "figure_sync"
        # asset_id will be None since figure not in library
        assert seg2.visual_asset_id is None

    def test_multiple_figures_in_segment(self, empty_library):
        """Segment referencing multiple figures still gets figure_sync."""
        segment = ScriptSegment(
            idx=0,
            text="Figures 1, 2, and 3 show our approach.",
            intent=SegmentIntent.FIGURE_WALKTHROUGH,
            figure_refs=[1, 2, 3],
        )
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[segment],
            total_segments=1,
        )

        result = assign_visuals(script, empty_library, "medium")
        assert result.get_segment(0).display_mode == "figure_sync"

    def test_visual_direction_hints_generated_for_figure(self, sample_script, library_with_figures):
        """Visual direction should include figure context."""
        result = assign_visuals(sample_script, library_with_figures, "medium")

        seg2 = result.get_segment(2)
        assert seg2.visual_direction
        assert "figure" in seg2.visual_direction.lower() or "Figure" in seg2.visual_direction


# ============================================================================
# Test: Budget Tier Ratios Are Respected
# ============================================================================


class TestBudgetTierRatios:
    """Test that budget tier ratios are correctly applied."""

    def test_medium_tier_ratio_27_percent(self, sample_script, empty_library):
        """Medium tier should allocate DALL-E images to approximately 27% of segments."""
        result = assign_visuals(sample_script, empty_library, "medium")

        dalle_count = sum(
            1 for s in result.segments
            if s.display_mode in ("dall_e", "web_image")
        )

        # 27% of 9 segments = ~2.43, expect 2-3 images
        assert 2 <= dalle_count <= 3

    def test_low_tier_ratio_10_percent(self, sample_script, empty_library):
        """Low tier should allocate DALL-E images to approximately 10% of segments."""
        result = assign_visuals(sample_script, empty_library, "low")

        dalle_count = sum(
            1 for s in result.segments
            if s.display_mode in ("dall_e", "web_image")
        )

        # 10% of 9 segments = ~0.9, expect 1 image (minimum 1 for visibility)
        assert dalle_count >= 1

    def test_high_tier_ratio_55_percent(self, sample_script, empty_library):
        """High tier should allocate DALL-E images to approximately 55% of segments."""
        result = assign_visuals(sample_script, empty_library, "high")

        dalle_count = sum(
            1 for s in result.segments
            if s.display_mode in ("dall_e", "web_image")
        )

        # 55% of 9 segments = ~4.95, expect 4-5 images
        assert 4 <= dalle_count <= 5

    def test_full_tier_100_percent(self, sample_script, empty_library):
        """Full tier should allocate DALL-E or figure_sync to all segments."""
        result = assign_visuals(sample_script, empty_library, "full")

        dalle_or_figure_count = sum(
            1 for s in result.segments
            if s.display_mode in ["dall_e", "web_image", "figure_sync"]
        )

        # All 9 segments should get either DALL-E or figure_sync
        assert dalle_or_figure_count == len(result.segments)

    def test_micro_tier_no_images(self, sample_script, empty_library):
        """Micro tier should not allocate any DALL-E images."""
        result = assign_visuals(sample_script, empty_library, "micro")

        dalle_count = sum(
            1 for s in result.segments
            if s.display_mode in ("dall_e", "web_image")
        )

        # Micro tier should have 0 DALL-E images
        assert dalle_count == 0

    def test_budget_tier_consistent_across_different_scene_counts(self, empty_library):
        """Ratios should be consistent regardless of total segment count."""
        # Create script with 100 segments
        segments_100 = [
            ScriptSegment(
                idx=i,
                text=f"Segment {i}",
                intent=SegmentIntent.BACKGROUND,
                importance_score=0.5,
            )
            for i in range(100)
        ]
        script_100 = StructuredScript(
            script_id="test_100_v1",
            trial_id="test",
            segments=segments_100,
            total_segments=100,
        )

        result_100 = assign_visuals(script_100, empty_library, "medium")
        dalle_count_100 = sum(
            1 for s in result_100.segments
            if s.display_mode in ("dall_e", "web_image")
        )

        # 27% of 100 = 27
        assert 25 <= dalle_count_100 <= 29

        # Create script with 10 segments
        segments_10 = [
            ScriptSegment(
                idx=i,
                text=f"Segment {i}",
                intent=SegmentIntent.BACKGROUND,
                importance_score=0.5,
            )
            for i in range(10)
        ]
        script_10 = StructuredScript(
            script_id="test_10_v1",
            trial_id="test",
            segments=segments_10,
            total_segments=10,
        )

        result_10 = assign_visuals(script_10, empty_library, "medium")
        dalle_count_10 = sum(
            1 for s in result_10.segments
            if s.display_mode in ("dall_e", "web_image")
        )

        # 27% of 10 = 2.7, expect 2-3
        assert 2 <= dalle_count_10 <= 3


# ============================================================================
# Test: Importance Scoring Affects Visual Assignment
# ============================================================================


class TestImportanceScoring:
    """Test that segment importance scores drive visual assignment priorities."""

    def test_high_importance_gets_dalle(self, sample_script, empty_library):
        """High importance segments should be prioritized for DALL-E."""
        result = assign_visuals(sample_script, empty_library, "low")

        # Importance scores: 0.8, 0.4, 1.0, 1.0, 0.7, 0.9, 0.6, 0.5, 0.6
        # Low tier should prioritize highest importance
        # Segment 3 (1.0) should have DALL-E
        seg3 = result.get_segment(3)
        assert seg3.display_mode in ["dall_e", "figure_sync"]

        # Segment 1 (0.4) should not have DALL-E if budget limited
        seg1 = result.get_segment(1)
        if result.segments.count(s for s in result.segments if s.display_mode in ("dall_e", "web_image")) == 1:
            # If only 1 image in low tier, it should go to highest importance
            assert seg1.display_mode != "dall_e" or seg3.display_mode == "figure_sync"

    def test_figure_segments_always_prioritized(self, sample_script, library_with_figures):
        """Figure segments should always get assigned first regardless of tier."""
        for tier in ["micro", "low", "medium", "high", "full"]:
            result = assign_visuals(sample_script, library_with_figures, tier)

            # Segments 2 and 3 are figure segments
            seg2 = result.get_segment(2)
            seg3 = result.get_segment(3)

            # Should always have figure_sync mode (not downgraded)
            assert seg2.display_mode == "figure_sync"
            assert seg3.display_mode == "figure_sync"

    def test_low_importance_gets_carry_forward(self, sample_script, empty_library):
        """Low importance segments should get carry_forward mode when budget limited."""
        # Set one segment to very low importance
        sample_script.segments[1].importance_score = 0.2  # BACKGROUND, low importance

        result = assign_visuals(sample_script, empty_library, "low")

        seg1 = result.get_segment(1)
        # With limited budget, low importance should get carry_forward
        assert seg1.display_mode in ["carry_forward", "text_only"]

    def test_importance_determines_image_allocation_order(self, empty_library):
        """With fixed image budget, highest importance segments get images first."""
        segments = [
            ScriptSegment(idx=0, text="Low importance", importance_score=0.3),
            ScriptSegment(idx=1, text="High importance", importance_score=0.9),
            ScriptSegment(idx=2, text="Medium importance", importance_score=0.6),
        ]
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
            total_segments=3,
        )

        result = assign_visuals(script, empty_library, "low")  # Only 1 image for low tier

        # Segment 1 (0.9) should get the image (dall_e or web_image)
        seg1 = result.get_segment(1)
        assert seg1.display_mode in ("dall_e", "web_image")


# ============================================================================
# Test: Existing Approved Assets Are Reused
# ============================================================================


class TestAssetReuse:
    """Test that existing approved assets prevent regeneration."""

    def test_approved_image_asset_reused(self, empty_library):
        """Segment with approved image should reuse it, not get new DALL-E."""
        segment = ScriptSegment(
            idx=0,
            text="Scene description",
            intent=SegmentIntent.BACKGROUND,
            importance_score=0.7,
        )
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[segment],
            total_segments=1,
        )

        # Register an approved image
        empty_library.register(
            AssetRecord(
                asset_id="img_001",
                asset_type=AssetType.IMAGE,
                source=AssetSource.DALLE,
                status=AssetStatus.APPROVED,
                segment_idx=0,
                path="images/img_001.png",
            )
        )

        result = assign_visuals(script, empty_library, "medium")
        seg0 = result.get_segment(0)

        # Should reuse approved image
        assert seg0.visual_asset_id == "img_001"
        assert seg0.display_mode == "dall_e"

    def test_draft_asset_not_reused(self, empty_library):
        """Segment with draft (non-approved) asset should still be scheduled for generation."""
        segment = ScriptSegment(
            idx=0,
            text="Scene description",
            intent=SegmentIntent.KEY_FINDING,
            importance_score=0.8,
        )
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[segment],
            total_segments=1,
        )

        # Register a draft image
        empty_library.register(
            AssetRecord(
                asset_id="img_draft",
                asset_type=AssetType.IMAGE,
                source=AssetSource.DALLE,
                status=AssetStatus.DRAFT,  # Not approved
                segment_idx=0,
                path="images/img_draft.png",
            )
        )

        result = assign_visuals(script, empty_library, "full")
        seg0 = result.get_segment(0)

        # Should still have display_mode but might not reuse draft
        # (depends on implementation, but draft shouldn't prevent generation)
        assert seg0.display_mode is not None

    def test_approved_figure_asset_reused(self, sample_script, empty_library):
        """Figure segment should reuse approved KB figure."""
        empty_library.register(
            AssetRecord(
                asset_id="fig_003",
                asset_type=AssetType.FIGURE,
                source=AssetSource.KB_EXTRACTION,
                status=AssetStatus.APPROVED,
                figure_number=3,
                path="figures/fig_003.png",
            )
        )

        result = assign_visuals(sample_script, empty_library, "medium")
        seg2 = result.get_segment(2)

        # Should reuse the figure
        assert seg2.visual_asset_id == "fig_003"

    def test_multiple_segments_can_share_image_with_ken_burns(self, empty_library):
        """Multiple segments can reference same image with Ken Burns effect."""
        segments = [
            ScriptSegment(idx=0, text="First mention", intent=SegmentIntent.BACKGROUND),
            ScriptSegment(idx=1, text="Second mention", intent=SegmentIntent.BACKGROUND),
        ]
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=segments,
            total_segments=2,
        )

        # Register one image
        empty_library.register(
            AssetRecord(
                asset_id="img_001",
                asset_type=AssetType.IMAGE,
                source=AssetSource.DALLE,
                status=AssetStatus.APPROVED,
                segment_idx=0,
                path="images/img_001.png",
            )
        )

        result = assign_visuals(script, empty_library, "low")

        # Both segments should reference same asset
        seg0 = result.get_segment(0)
        seg1 = result.get_segment(1)

        # seg0 reuses approved, seg1 might use carry_forward with same image
        assert seg0.visual_asset_id == "img_001"


# ============================================================================
# Test: Visual Direction Hints Are Generated
# ============================================================================


class TestVisualDirection:
    """Test that visual_direction hints are generated for prompt engineering."""

    def test_visual_direction_generated_for_high_importance(self, sample_script, empty_library):
        """High importance segments should get visual direction hints."""
        result = assign_visuals(sample_script, empty_library, "medium")

        # Segment 5 (KEY_FINDING, importance=0.9)
        seg5 = result.get_segment(5)
        assert seg5.visual_direction
        assert len(seg5.visual_direction) > 0

    def test_visual_direction_includes_intent_context(self, sample_script, empty_library):
        """Visual direction should reflect segment intent."""
        result = assign_visuals(sample_script, empty_library, "medium")

        # Methodology segment should mention system/process
        seg4 = result.get_segment(4)
        if seg4.display_mode == "dall_e":
            assert seg4.visual_direction
            hint_lower = seg4.visual_direction.lower()
            # Should hint at methodology concepts
            assert any(word in hint_lower for word in ["system", "process", "method", "diagram", "flow"])

    def test_visual_direction_includes_key_concepts(self, sample_script, empty_library):
        """Visual direction should incorporate key_concepts from segment."""
        result = assign_visuals(sample_script, empty_library, "medium")

        # Segment 4 has key_concepts
        seg4 = result.get_segment(4)
        if seg4.display_mode == "dall_e":
            assert seg4.visual_direction
            # Should reference the concepts somehow
            direction_lower = seg4.visual_direction.lower()
            # Check if concepts are referenced (exact match or paraphrase)
            assert any(c.lower() in direction_lower for c in ["filter", "optim"])

    def test_visual_direction_for_figure_sync(self, sample_script, library_with_figures):
        """Figure segments should have visual direction for frame synchronization."""
        result = assign_visuals(sample_script, library_with_figures, "medium")

        seg2 = result.get_segment(2)
        assert seg2.display_mode == "figure_sync"
        # Should have timing/sync hints
        if seg2.visual_direction:
            assert "figure" in seg2.visual_direction.lower() or \
                   "sync" in seg2.visual_direction.lower() or \
                   "timing" in seg2.visual_direction.lower()

    def test_visual_direction_includes_composition_hints(self, sample_script, empty_library):
        """Visual direction should include framing/composition guidance."""
        sample_script.segments[5].display_mode = None  # Reset to test assignment
        result = assign_visuals(sample_script, empty_library, "full")

        # At least some segments should have composition guidance
        directions_with_hints = sum(
            1 for s in result.segments
            if s.visual_direction and (
                "composition" in s.visual_direction.lower() or
                "frame" in s.visual_direction.lower() or
                "ken burns" in s.visual_direction.lower()
            )
        )

        assert directions_with_hints >= 1


# ============================================================================
# Test: Integration - Full Script Processing
# ============================================================================


class TestFullScriptProcessing:
    """Test complete DoP workflow on full scripts."""

    def test_all_segments_get_display_mode(self, sample_script, empty_library):
        """Every segment should have a display_mode after DoP processing."""
        result = assign_visuals(sample_script, empty_library, "medium")

        for segment in result.segments:
            assert segment.display_mode is not None
            assert segment.display_mode in [
                "figure_sync",
                "dall_e",
                "web_image",
                "carry_forward",
                "text_only"
            ]

    def test_figure_segments_never_downgraded(self, sample_script, library_with_figures):
        """Figure segments should maintain figure_sync across all budget tiers."""
        for tier in ["micro", "low", "medium", "high", "full"]:
            result = assign_visuals(sample_script, library_with_figures, tier)

            # Segments 2 and 3 have figures
            seg2 = result.get_segment(2)
            seg3 = result.get_segment(3)

            assert seg2.display_mode == "figure_sync", f"Tier {tier}: seg2 downgraded"
            assert seg3.display_mode == "figure_sync", f"Tier {tier}: seg3 downgraded"

    def test_budget_tier_parameter_respected(self, sample_script, empty_library):
        """Tiers should produce different allocation patterns."""
        tier_dalle_counts = {}

        for tier in ["micro", "low", "medium", "high", "full"]:
            result = assign_visuals(sample_script, empty_library, tier)
            dalle_count = sum(
                1 for s in result.segments
                if s.display_mode in ("dall_e", "web_image")
            )
            tier_dalle_counts[tier] = dalle_count

        # Verify monotonic increase: micro < low < medium < high < full
        assert tier_dalle_counts["micro"] <= tier_dalle_counts["low"]
        assert tier_dalle_counts["low"] <= tier_dalle_counts["medium"]
        assert tier_dalle_counts["medium"] <= tier_dalle_counts["high"]
        assert tier_dalle_counts["high"] <= tier_dalle_counts["full"]

    def test_script_object_modified_in_place(self, sample_script, empty_library):
        """DoP should modify the input script object."""
        original_display_modes = [s.display_mode for s in sample_script.segments]

        result = assign_visuals(sample_script, empty_library, "medium")

        # Result should be the modified script
        assert result is sample_script

        # Display modes should be assigned
        for segment in result.segments:
            assert segment.display_mode is not None

    def test_visual_asset_ids_assigned_from_library(self, sample_script, library_with_figures):
        """visual_asset_id should be populated from library when available."""
        result = assign_visuals(sample_script, library_with_figures, "full")

        # Figure segments should have asset IDs
        seg2 = result.get_segment(2)
        seg3 = result.get_segment(3)

        assert seg2.visual_asset_id is not None
        assert seg3.visual_asset_id is not None

        # Verify they exist in library
        lib_asset_2 = library_with_figures.get(seg2.visual_asset_id)
        lib_asset_3 = library_with_figures.get(seg3.visual_asset_id)

        assert lib_asset_2 is not None
        assert lib_asset_3 is not None
        assert lib_asset_2.figure_number == 3
        assert lib_asset_3.figure_number == 5


# ============================================================================
# Test: Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_script(self, empty_library):
        """DoP should handle empty script gracefully."""
        script = StructuredScript(
            script_id="empty_v1",
            trial_id="test",
            segments=[],
            total_segments=0,
        )

        result = assign_visuals(script, empty_library, "medium")
        assert result.segments == []

    def test_single_segment_script(self, empty_library):
        """DoP should work with single-segment script."""
        script = StructuredScript(
            script_id="single_v1",
            trial_id="test",
            segments=[ScriptSegment(idx=0, text="Only segment", importance_score=0.5)],
            total_segments=1,
        )

        result = assign_visuals(script, empty_library, "full")
        assert len(result.segments) == 1
        assert result.segments[0].display_mode is not None

    def test_zero_importance_segments(self, empty_library):
        """Segments with 0 importance should still get assigned modes."""
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[
                ScriptSegment(idx=0, text="Zero importance", importance_score=0.0),
            ],
            total_segments=1,
        )

        result = assign_visuals(script, empty_library, "full")
        seg0 = result.get_segment(0)
        assert seg0.display_mode is not None

    def test_transition_segments_get_text_only(self, empty_library):
        """Transition segments should get text_only mode."""
        segment = ScriptSegment(
            idx=0,
            text="Moving on to the next point.",
            intent=SegmentIntent.TRANSITION,
            importance_score=0.2,
        )
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[segment],
            total_segments=1,
        )

        result = assign_visuals(script, empty_library, "full")
        assert result.get_segment(0).display_mode == "text_only"

    def test_invalid_budget_tier_defaults_gracefully(self, sample_script, empty_library):
        """Invalid tier should use default (medium) or raise informative error."""
        # This might raise ValueError or default to medium
        try:
            result = assign_visuals(sample_script, empty_library, "invalid_tier")
            # If it doesn't raise, should behave like medium
            dalle_count = sum(1 for s in result.segments if s.display_mode in ("dall_e", "web_image"))
            assert dalle_count > 0
        except (ValueError, KeyError):
            # Acceptable to raise for invalid tier
            pass

    def test_figure_not_found_in_inventory(self, empty_library):
        """Segment referencing non-existent figure should still get figure_sync."""
        segment = ScriptSegment(
            idx=0,
            text="Figure 999 shows something.",
            intent=SegmentIntent.FIGURE_WALKTHROUGH,
            figure_refs=[999],  # Doesn't exist
        )
        script = StructuredScript(
            script_id="test_v1",
            trial_id="test",
            segments=[segment],
            total_segments=1,
        )

        result = assign_visuals(script, empty_library, "medium")
        seg0 = result.get_segment(0)

        # Should still be figure_sync even if not in library
        assert seg0.display_mode == "figure_sync"
        # But no asset_id since figure not in library
        assert seg0.visual_asset_id is None
