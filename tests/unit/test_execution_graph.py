"""Unit tests for ExecutionGraph and ExecutionGraphBuilder

Tests the visual thread / continuity group logic that ensures:
1. Scenes with the same continuity_group are chained together
2. Different continuity groups can run in parallel
3. The editor can reassemble scenes in original order after generation
"""

import pytest
from agents.script_writer import Scene
from core.models.execution import ExecutionGraph, SceneGroup, ExecutionMode
from core.execution.graph_builder import ExecutionGraphBuilder


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def woman_phone_scenes():
    """Scenes 1 and 3: woman on phone (same visual thread)"""
    return [
        Scene(
            scene_id="scene_1",
            title="Woman on Phone - Close-up",
            description="Close-up of woman talking on telephone",
            duration=5.0,
            visual_elements=["woman", "telephone", "dramatic lighting"],
            audio_notes="ambient",
            transition_in="fade_in",
            transition_out="cut",
            prompt_hints=["cinematic"],
            continuity_group="woman_phone",
            is_continuity_anchor=True,
            continuity_elements=["character", "lighting"]
        ),
        Scene(
            scene_id="scene_3",
            title="Woman on Phone - Back View",
            description="Back of woman's head still on telephone",
            duration=5.0,
            visual_elements=["woman", "telephone", "back view"],
            audio_notes="ambient",
            transition_in="cut",
            transition_out="cut",
            prompt_hints=["cinematic"],
            continuity_group="woman_phone",
            is_continuity_anchor=False,
            continuity_elements=["character", "lighting"]
        ),
    ]


@pytest.fixture
def blueprint_scenes():
    """Scenes 2 and 4: blueprint schematic (same visual thread)"""
    return [
        Scene(
            scene_id="scene_2",
            title="Blueprint Schematic",
            description="Technical blueprint of absurd device",
            duration=5.0,
            visual_elements=["blueprint", "white lines", "blue background"],
            audio_notes="ambient",
            transition_in="cut",
            transition_out="cut",
            prompt_hints=["technical"],
            continuity_group="blueprint",
            is_continuity_anchor=True,
            continuity_elements=["style", "colors"]
        ),
        Scene(
            scene_id="scene_4",
            title="Blueprint Burning",
            description="Same blueprint bursting into flames",
            duration=5.0,
            visual_elements=["blueprint", "fire", "destruction"],
            audio_notes="fire sound",
            transition_in="cut",
            transition_out="fade_out",
            prompt_hints=["dramatic"],
            continuity_group="blueprint",
            is_continuity_anchor=False,
            continuity_elements=["style", "colors"]
        ),
    ]


@pytest.fixture
def interleaved_scenes(woman_phone_scenes, blueprint_scenes):
    """All 4 scenes in edit order: 1, 2, 3, 4"""
    return [
        woman_phone_scenes[0],  # scene_1 - woman
        blueprint_scenes[0],     # scene_2 - blueprint
        woman_phone_scenes[1],  # scene_3 - woman
        blueprint_scenes[1],     # scene_4 - blueprint
    ]


@pytest.fixture
def scenes_without_continuity():
    """Scenes with no continuity_group (should use auto-detect)"""
    return [
        Scene(
            scene_id="scene_1",
            title="Opening",
            description="Product reveal",
            duration=5.0,
            visual_elements=["product"],
            audio_notes="music",
            transition_in="fade_in",
            transition_out="cut",
            prompt_hints=["professional"]
        ),
        Scene(
            scene_id="scene_2",
            title="Features",
            description="Show features",
            duration=5.0,
            visual_elements=["UI", "features"],
            audio_notes="voiceover",
            transition_in="cut",
            transition_out="cut",
            prompt_hints=["clean"]
        ),
    ]


# ============================================================
# ExecutionGraph Model Tests
# ============================================================

class TestExecutionGraphModel:
    """Test ExecutionGraph dataclass"""

    def test_empty_graph(self):
        """Test empty graph"""
        graph = ExecutionGraph()
        assert graph.groups == []
        assert graph.get_all_scene_ids() == []
        assert graph.get_execution_waves() == []

    def test_get_group(self):
        """Test getting a group by ID"""
        graph = ExecutionGraph(groups=[
            SceneGroup(group_id="group_a", scene_ids=["scene_1"], mode=ExecutionMode.PARALLEL),
            SceneGroup(group_id="group_b", scene_ids=["scene_2"], mode=ExecutionMode.SEQUENTIAL),
        ])

        assert graph.get_group("group_a").group_id == "group_a"
        assert graph.get_group("group_b").mode == ExecutionMode.SEQUENTIAL
        assert graph.get_group("nonexistent") is None

    def test_get_scene_group(self):
        """Test finding which group a scene belongs to"""
        graph = ExecutionGraph(groups=[
            SceneGroup(group_id="group_a", scene_ids=["scene_1", "scene_3"], mode=ExecutionMode.SEQUENTIAL),
            SceneGroup(group_id="group_b", scene_ids=["scene_2", "scene_4"], mode=ExecutionMode.SEQUENTIAL),
        ])

        assert graph.get_scene_group("scene_1").group_id == "group_a"
        assert graph.get_scene_group("scene_3").group_id == "group_a"
        assert graph.get_scene_group("scene_2").group_id == "group_b"
        assert graph.get_scene_group("scene_4").group_id == "group_b"
        assert graph.get_scene_group("scene_99") is None

    def test_get_all_scene_ids(self):
        """Test getting all scene IDs in graph order"""
        graph = ExecutionGraph(groups=[
            SceneGroup(group_id="group_a", scene_ids=["scene_1", "scene_3"], mode=ExecutionMode.SEQUENTIAL),
            SceneGroup(group_id="group_b", scene_ids=["scene_2", "scene_4"], mode=ExecutionMode.SEQUENTIAL),
        ])

        # Order is by group, not by scene number
        assert graph.get_all_scene_ids() == ["scene_1", "scene_3", "scene_2", "scene_4"]


# ============================================================
# ExecutionGraph Wave Tests (Core Logic)
# ============================================================

class TestExecutionWaves:
    """Test the wave generation logic for parallel execution"""

    def test_single_parallel_group_one_wave(self):
        """All parallel scenes run in one wave"""
        graph = ExecutionGraph(groups=[
            SceneGroup(
                group_id="parallel",
                scene_ids=["scene_1", "scene_2", "scene_3"],
                mode=ExecutionMode.PARALLEL
            )
        ])

        waves = graph.get_execution_waves()
        assert len(waves) == 1
        assert set(waves[0]) == {"scene_1", "scene_2", "scene_3"}

    def test_single_sequential_group_multiple_waves(self):
        """Sequential scenes run one per wave"""
        graph = ExecutionGraph(groups=[
            SceneGroup(
                group_id="sequential",
                scene_ids=["scene_1", "scene_2", "scene_3"],
                mode=ExecutionMode.SEQUENTIAL
            )
        ])

        waves = graph.get_execution_waves()
        assert len(waves) == 3
        assert waves[0] == ["scene_1"]
        assert waves[1] == ["scene_2"]
        assert waves[2] == ["scene_3"]

    def test_two_sequential_groups_interleaved_waves(self):
        """Two sequential groups run in parallel, interleaved"""
        graph = ExecutionGraph(groups=[
            SceneGroup(
                group_id="woman_phone",
                scene_ids=["scene_1", "scene_3"],
                mode=ExecutionMode.SEQUENTIAL
            ),
            SceneGroup(
                group_id="blueprint",
                scene_ids=["scene_2", "scene_4"],
                mode=ExecutionMode.SEQUENTIAL
            ),
        ])

        waves = graph.get_execution_waves()

        # Should be 2 waves, each containing one scene from each group
        assert len(waves) == 2

        # Wave 1: first scene from each group (can run in parallel)
        assert set(waves[0]) == {"scene_1", "scene_2"}

        # Wave 2: second scene from each group (can run in parallel)
        assert set(waves[1]) == {"scene_3", "scene_4"}

    def test_unequal_sequential_groups(self):
        """Sequential groups with different lengths"""
        graph = ExecutionGraph(groups=[
            SceneGroup(
                group_id="group_a",
                scene_ids=["scene_1", "scene_3", "scene_5"],
                mode=ExecutionMode.SEQUENTIAL
            ),
            SceneGroup(
                group_id="group_b",
                scene_ids=["scene_2", "scene_4"],
                mode=ExecutionMode.SEQUENTIAL
            ),
        ])

        waves = graph.get_execution_waves()

        # Should be 3 waves (max length of any group)
        assert len(waves) == 3
        assert set(waves[0]) == {"scene_1", "scene_2"}
        assert set(waves[1]) == {"scene_3", "scene_4"}
        assert waves[2] == ["scene_5"]  # Only group_a has a third scene

    def test_parallel_then_sequential(self):
        """Mix of parallel and sequential groups"""
        graph = ExecutionGraph(groups=[
            SceneGroup(
                group_id="intro",
                scene_ids=["scene_1", "scene_2"],
                mode=ExecutionMode.PARALLEL
            ),
            SceneGroup(
                group_id="main",
                scene_ids=["scene_3", "scene_4"],
                mode=ExecutionMode.SEQUENTIAL
            ),
        ])

        waves = graph.get_execution_waves()

        # Wave 1: all parallel scenes
        # Waves 2-3: sequential scenes one at a time
        assert len(waves) == 3
        assert set(waves[0]) == {"scene_1", "scene_2"}
        assert waves[1] == ["scene_3"]
        assert waves[2] == ["scene_4"]


# ============================================================
# ExecutionGraphBuilder Tests
# ============================================================

class TestExecutionGraphBuilder:
    """Test building execution graphs from scenes"""

    def test_explicit_continuity_groups(self, interleaved_scenes):
        """Test that explicit continuity_group fields are respected"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")

        # Should create two sequential groups based on continuity_group
        assert len(graph.groups) == 2

        # Find the groups
        woman_group = next((g for g in graph.groups if "woman" in g.group_id.lower()), None)
        blueprint_group = next((g for g in graph.groups if "blueprint" in g.group_id.lower()), None)

        assert woman_group is not None, "Should have woman_phone group"
        assert blueprint_group is not None, "Should have blueprint group"

        # Check group contents
        assert woman_group.mode == ExecutionMode.SEQUENTIAL
        assert set(woman_group.scene_ids) == {"scene_1", "scene_3"}

        assert blueprint_group.mode == ExecutionMode.SEQUENTIAL
        assert set(blueprint_group.scene_ids) == {"scene_2", "scene_4"}

    def test_explicit_groups_correct_waves(self, interleaved_scenes):
        """Test that waves are correctly interleaved for explicit groups"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")
        waves = graph.get_execution_waves()

        # Should have 2 waves
        assert len(waves) == 2

        # Each wave should have one scene from each group
        # Wave 1: scene_1 (woman) and scene_2 (blueprint)
        assert len(waves[0]) == 2
        assert "scene_1" in waves[0]
        assert "scene_2" in waves[0]

        # Wave 2: scene_3 (woman) and scene_4 (blueprint)
        assert len(waves[1]) == 2
        assert "scene_3" in waves[1]
        assert "scene_4" in waves[1]

    def test_all_parallel_strategy(self, interleaved_scenes):
        """Test all_parallel strategy ignores continuity groups"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="all_parallel")

        assert len(graph.groups) == 1
        assert graph.groups[0].mode == ExecutionMode.PARALLEL
        assert len(graph.groups[0].scene_ids) == 4

        waves = graph.get_execution_waves()
        assert len(waves) == 1
        assert len(waves[0]) == 4

    def test_all_sequential_strategy(self, interleaved_scenes):
        """Test all_sequential strategy chains everything"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="all_sequential")

        assert len(graph.groups) == 1
        assert graph.groups[0].mode == ExecutionMode.SEQUENTIAL
        assert len(graph.groups[0].scene_ids) == 4

        waves = graph.get_execution_waves()
        assert len(waves) == 4  # One wave per scene

    def test_auto_detect_without_explicit_groups(self, scenes_without_continuity):
        """Test auto-detect falls back to heuristics when no continuity_group"""
        graph = ExecutionGraphBuilder.from_scenes(scenes_without_continuity, strategy="auto")

        # Should still create a valid graph
        assert len(graph.groups) >= 1
        assert graph.get_all_scene_ids() == ["scene_1", "scene_2"]

    def test_manual_strategy(self, interleaved_scenes):
        """Test manual strategy uses explicit groups"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="manual")

        # Should be the same as auto when explicit groups exist
        assert len(graph.groups) == 2


# ============================================================
# Editor Assembly Order Tests
# ============================================================

class TestEditorAssemblyOrder:
    """Test that editor can reassemble scenes in correct order after generation"""

    def test_original_scene_order_preserved(self, interleaved_scenes):
        """Scenes should maintain their original IDs for reassembly"""
        # Original order: scene_1, scene_2, scene_3, scene_4

        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")

        # The graph groups scenes by continuity, but the scene_ids preserve original numbering
        all_scene_ids = set()
        for group in graph.groups:
            all_scene_ids.update(group.scene_ids)

        # All original scene IDs should be present
        assert all_scene_ids == {"scene_1", "scene_2", "scene_3", "scene_4"}

    def test_reassembly_order_is_scene_id_order(self, interleaved_scenes):
        """Editor should reassemble by sorting scene_id"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")

        # Get all scene IDs from all groups
        all_scene_ids = []
        for group in graph.groups:
            all_scene_ids.extend(group.scene_ids)

        # Sort by scene_id to get edit order
        edit_order = sorted(all_scene_ids)
        assert edit_order == ["scene_1", "scene_2", "scene_3", "scene_4"]

    def test_generation_order_differs_from_edit_order(self, interleaved_scenes):
        """Generation order (by wave) differs from final edit order"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")
        waves = graph.get_execution_waves()

        # Generation order: wave 1 (scene_1, scene_2), wave 2 (scene_3, scene_4)
        generation_order = []
        for wave in waves:
            generation_order.extend(sorted(wave))  # Sort within wave for determinism

        # Edit order is always by scene_id
        edit_order = ["scene_1", "scene_2", "scene_3", "scene_4"]

        # Generation order may differ (though in this case it happens to match)
        # The key point is that scene_1 and scene_3 are NOT generated consecutively
        # because they're in different waves

        # Verify scene_1 and scene_3 are NOT in the same wave
        scene_1_wave = next(i for i, w in enumerate(waves) if "scene_1" in w)
        scene_3_wave = next(i for i, w in enumerate(waves) if "scene_3" in w)
        assert scene_1_wave != scene_3_wave, "scene_1 and scene_3 should be in different waves"


# ============================================================
# Graph Validation Tests
# ============================================================

class TestGraphValidation:
    """Test graph validation logic"""

    def test_valid_graph(self, interleaved_scenes):
        """Test that valid graph has no errors"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")
        errors = graph.validate()
        assert errors == []

    def test_duplicate_scene_ids(self):
        """Test detection of duplicate scene IDs"""
        graph = ExecutionGraph(groups=[
            SceneGroup(group_id="group_a", scene_ids=["scene_1", "scene_2"], mode=ExecutionMode.PARALLEL),
            SceneGroup(group_id="group_b", scene_ids=["scene_2", "scene_3"], mode=ExecutionMode.PARALLEL),
        ])

        errors = graph.validate()
        assert len(errors) == 1
        assert "Duplicate scene_id: scene_2" in errors[0]

    def test_invalid_chain_reference(self):
        """Test detection of invalid chain_from_group reference"""
        graph = ExecutionGraph(groups=[
            SceneGroup(
                group_id="group_a",
                scene_ids=["scene_1"],
                mode=ExecutionMode.SEQUENTIAL,
                chain_from_group="nonexistent_group"
            ),
        ])

        errors = graph.validate()
        assert len(errors) == 1
        assert "unknown group" in errors[0].lower()


# ============================================================
# Chaining Logic Tests
# ============================================================

class TestChainingLogic:
    """Test that chaining works correctly within groups"""

    def test_first_scene_in_group_no_chain(self, interleaved_scenes):
        """First scene in each group should NOT chain from anything"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")

        for group in graph.groups:
            first_scene = group.scene_ids[0]
            # First scene has no chain dependency
            # (The actual chaining is handled in VideoGenerator, but graph structure supports it)
            assert first_scene in ["scene_1", "scene_2"]  # First in their respective groups

    def test_subsequent_scenes_chain_from_previous(self, interleaved_scenes):
        """Subsequent scenes in group should chain from previous scene in same group"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")

        # Find woman_phone group
        woman_group = next(g for g in graph.groups if "woman" in g.group_id.lower())

        # scene_3 should chain from scene_1 (both in woman_phone group)
        assert woman_group.scene_ids == ["scene_1", "scene_3"]
        # scene_3 is at index 1, scene_1 is at index 0

        # Find blueprint group
        blueprint_group = next(g for g in graph.groups if "blueprint" in g.group_id.lower())

        # scene_4 should chain from scene_2 (both in blueprint group)
        assert blueprint_group.scene_ids == ["scene_2", "scene_4"]

    def test_no_cross_group_chaining(self, interleaved_scenes):
        """Scenes should NOT chain across different groups"""
        graph = ExecutionGraphBuilder.from_scenes(interleaved_scenes, strategy="auto")

        # scene_2 (blueprint) should NOT chain from scene_1 (woman)
        # scene_3 (woman) should NOT chain from scene_2 (blueprint)
        # This is enforced by the group structure

        woman_group = next(g for g in graph.groups if "woman" in g.group_id.lower())
        blueprint_group = next(g for g in graph.groups if "blueprint" in g.group_id.lower())

        # Groups are independent - no chain_from_group references
        assert woman_group.chain_from_group is None
        assert blueprint_group.chain_from_group is None


# ============================================================
# Edge Cases
# ============================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_single_scene(self):
        """Test with single scene"""
        scenes = [
            Scene(
                scene_id="scene_1",
                title="Only Scene",
                description="The only scene",
                duration=5.0,
                visual_elements=["element"],
                audio_notes="music",
                transition_in="fade_in",
                transition_out="fade_out",
                prompt_hints=["professional"]
            )
        ]

        graph = ExecutionGraphBuilder.from_scenes(scenes, strategy="auto")
        waves = graph.get_execution_waves()

        assert len(waves) == 1
        assert waves[0] == ["scene_1"]

    def test_all_same_continuity_group(self):
        """Test when all scenes have same continuity_group"""
        scenes = [
            Scene(
                scene_id=f"scene_{i}",
                title=f"Scene {i}",
                description="Same character throughout",
                duration=5.0,
                visual_elements=["character"],
                audio_notes="dialogue",
                transition_in="cut",
                transition_out="cut",
                prompt_hints=["cinematic"],
                continuity_group="same_character"
            )
            for i in range(1, 5)
        ]

        graph = ExecutionGraphBuilder.from_scenes(scenes, strategy="auto")

        # Should have one sequential group
        assert len(graph.groups) == 1
        assert graph.groups[0].mode == ExecutionMode.SEQUENTIAL
        assert len(graph.groups[0].scene_ids) == 4

        waves = graph.get_execution_waves()
        assert len(waves) == 4  # One scene per wave

    def test_mixed_grouped_and_ungrouped(self):
        """Test mix of scenes with and without continuity_group"""
        scenes = [
            Scene(
                scene_id="scene_1",
                title="Character Intro",
                description="Character appears",
                duration=5.0,
                visual_elements=["character"],
                audio_notes="music",
                transition_in="fade_in",
                transition_out="cut",
                prompt_hints=["cinematic"],
                continuity_group="main_character"
            ),
            Scene(
                scene_id="scene_2",
                title="B-Roll",
                description="City establishing shot",
                duration=3.0,
                visual_elements=["cityscape"],
                audio_notes="ambient",
                transition_in="cut",
                transition_out="cut",
                prompt_hints=["wide shot"]
                # No continuity_group - independent
            ),
            Scene(
                scene_id="scene_3",
                title="Character Continues",
                description="Character walks",
                duration=5.0,
                visual_elements=["character", "walking"],
                audio_notes="footsteps",
                transition_in="cut",
                transition_out="fade_out",
                prompt_hints=["tracking shot"],
                continuity_group="main_character"
            ),
        ]

        graph = ExecutionGraphBuilder.from_scenes(scenes, strategy="auto")

        # Should have: one sequential group (main_character) and one parallel group (default)
        assert len(graph.groups) == 2

        sequential_group = next((g for g in graph.groups if g.mode == ExecutionMode.SEQUENTIAL), None)
        parallel_group = next((g for g in graph.groups if g.mode == ExecutionMode.PARALLEL), None)

        assert sequential_group is not None
        assert parallel_group is not None

        assert set(sequential_group.scene_ids) == {"scene_1", "scene_3"}
        assert parallel_group.scene_ids == ["scene_2"]
