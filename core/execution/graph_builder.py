"""
ExecutionGraphBuilder - Builds execution graphs from scenes based on continuity requirements.

Strategies:
- AUTO: Analyze scenes and group by continuity needs
- MANUAL: Use explicit continuity_group from scenes
- ALL_PARALLEL: Everything parallel (fastest, no continuity)
- ALL_SEQUENTIAL: Everything sequential (slowest, max continuity)
"""

from typing import List, Dict, Optional, Set
from collections import defaultdict
import re

from core.models.execution import ExecutionGraph, SceneGroup, ExecutionMode


class ExecutionGraphBuilder:
    """
    Builds execution graph from scenes based on continuity requirements.
    """

    # Keywords that suggest scenes should be parallel (independent)
    PARALLEL_KEYWORDS = [
        "b-roll", "broll", "establishing", "cutaway", "montage",
        "insert", "overlay", "transition", "title", "logo",
        "product shot", "detail shot", "ambient", "background"
    ]

    # Keywords that suggest scenes need continuity
    CONTINUITY_KEYWORDS = [
        "continues", "continuous", "same", "character", "person",
        "protagonist", "hero", "actor", "follow", "tracking",
        "interview", "conversation", "dialogue", "reaction"
    ]

    @staticmethod
    def from_scenes(
        scenes: List,  # List[Scene] - using Any to avoid circular import
        strategy: str = "auto"
    ) -> ExecutionGraph:
        """
        Build execution graph from scenes.

        Args:
            scenes: List of Scene objects
            strategy: One of "auto", "manual", "all_parallel", "all_sequential"

        Returns:
            ExecutionGraph defining execution order and dependencies
        """
        if strategy == "all_parallel":
            return ExecutionGraphBuilder._all_parallel(scenes)
        elif strategy == "all_sequential":
            return ExecutionGraphBuilder._all_sequential(scenes)
        elif strategy == "manual":
            return ExecutionGraphBuilder._from_scene_groups(scenes)
        else:  # auto
            return ExecutionGraphBuilder._auto_detect(scenes)

    @staticmethod
    def _all_parallel(scenes: List) -> ExecutionGraph:
        """All scenes run in parallel - fastest, no continuity"""
        return ExecutionGraph(groups=[
            SceneGroup(
                group_id="all_parallel",
                scene_ids=[s.scene_id for s in scenes],
                mode=ExecutionMode.PARALLEL,
                description="All scenes parallel (no continuity)"
            )
        ])

    @staticmethod
    def _all_sequential(scenes: List) -> ExecutionGraph:
        """All scenes run sequentially - slowest, maximum continuity"""
        return ExecutionGraph(groups=[
            SceneGroup(
                group_id="all_sequential",
                scene_ids=[s.scene_id for s in scenes],
                mode=ExecutionMode.SEQUENTIAL,
                description="All scenes sequential (maximum continuity)"
            )
        ])

    @staticmethod
    def _from_scene_groups(scenes: List) -> ExecutionGraph:
        """
        Build from explicit continuity_group assignments on scenes.

        Key insight: Scenes with the same continuity_group (visual thread) should be
        generated sequentially with chaining, even if they're interleaved with other
        scenes in the final edit order.

        Example: If scene 1 & 3 are "woman_phone" and scene 2 & 4 are "blueprint":
        - Generate woman_phone thread: scene_1 -> scene_3 (chained)
        - Generate blueprint thread: scene_2 -> scene_4 (chained)
        - Both threads can run in PARALLEL to each other
        - Editor reassembles as 1, 2, 3, 4 for final video
        """
        groups_map: Dict[str, List] = defaultdict(list)  # group_id -> list of (scene_id, scene)

        # Collect scenes by continuity group
        for scene in scenes:
            group_id = getattr(scene, 'continuity_group', None) or "default_parallel"
            groups_map[group_id].append((scene.scene_id, scene))

        # Sort scenes within each group by scene_id to preserve visual thread order
        # (scene_1 before scene_3, even if scene_2 is a different group)
        for group_id in groups_map:
            groups_map[group_id].sort(key=lambda x: x[0])

        # Build execution groups
        groups = []
        sequential_groups = []  # Track sequential groups for parallel execution

        for group_id, scene_tuples in groups_map.items():
            scene_ids = [s[0] for s in scene_tuples]

            if group_id == "default_parallel":
                # Default ungrouped scenes run in parallel (no continuity needed)
                groups.append(SceneGroup(
                    group_id=group_id,
                    scene_ids=scene_ids,
                    mode=ExecutionMode.PARALLEL,
                    description="Independent scenes (no continuity group specified)"
                ))
            else:
                # Explicitly grouped scenes run sequentially within group (chained)
                # But different groups can run in parallel with each other
                group = SceneGroup(
                    group_id=group_id,
                    scene_ids=scene_ids,
                    mode=ExecutionMode.SEQUENTIAL,
                    description=f"Visual thread: {group_id}"
                )
                groups.append(group)
                sequential_groups.append(group_id)

        # Note: Different sequential groups do NOT chain from each other
        # They run independently (in parallel at the group level)
        # Only scenes WITHIN a group chain from each other

        return ExecutionGraph(groups=groups)

    @staticmethod
    def _auto_detect(scenes: List) -> ExecutionGraph:
        """
        Auto-detect continuity needs based on scene content.

        First checks for explicit continuity_group assignments from ScriptWriter.
        If any scene has a continuity_group, uses manual grouping strategy.

        Otherwise falls back to heuristics:
        - Same character/person mentioned -> sequential
        - Same location mentioned -> sequential
        - "continues from" or "same" in description -> sequential
        - B-roll, establishing shots, inserts -> parallel
        - Product shots, logos -> parallel
        """
        # First check if any scenes have explicit continuity_group assignments
        has_explicit_groups = any(
            hasattr(scene, 'continuity_group') and scene.continuity_group
            for scene in scenes
        )
        if has_explicit_groups:
            # Use manual grouping when explicit groups are provided
            return ExecutionGraphBuilder._from_scene_groups(scenes)

        # Analyze each scene
        scene_analysis: Dict[str, Dict] = {}

        for scene in scenes:
            analysis = ExecutionGraphBuilder._analyze_scene(scene)
            scene_analysis[scene.scene_id] = analysis

        # Group scenes by detected continuity needs
        groups: List[SceneGroup] = []
        current_sequential_group: Optional[List[str]] = None
        current_group_id = 0

        parallel_scenes: List[str] = []

        for scene in scenes:
            analysis = scene_analysis[scene.scene_id]

            if analysis["is_parallel"]:
                # This is independent content
                if current_sequential_group:
                    # Finish current sequential group
                    groups.append(SceneGroup(
                        group_id=f"continuity_{current_group_id}",
                        scene_ids=current_sequential_group,
                        mode=ExecutionMode.SEQUENTIAL,
                        description=f"Auto-detected continuity group"
                    ))
                    current_sequential_group = None
                    current_group_id += 1

                parallel_scenes.append(scene.scene_id)

            elif analysis["needs_continuity"]:
                # Check if this should continue previous group or start new one
                if current_sequential_group:
                    # Check if this scene relates to the previous one
                    prev_scene_id = current_sequential_group[-1]
                    prev_analysis = scene_analysis[prev_scene_id]

                    if ExecutionGraphBuilder._scenes_related(prev_analysis, analysis):
                        # Continue current group
                        current_sequential_group.append(scene.scene_id)
                    else:
                        # Start new group
                        groups.append(SceneGroup(
                            group_id=f"continuity_{current_group_id}",
                            scene_ids=current_sequential_group,
                            mode=ExecutionMode.SEQUENTIAL,
                            description="Auto-detected continuity group"
                        ))
                        current_group_id += 1
                        current_sequential_group = [scene.scene_id]
                else:
                    # Start new sequential group
                    current_sequential_group = [scene.scene_id]
            else:
                # Ambiguous - default to continuing pattern
                if current_sequential_group:
                    current_sequential_group.append(scene.scene_id)
                else:
                    parallel_scenes.append(scene.scene_id)

        # Finish any remaining groups
        if current_sequential_group:
            groups.append(SceneGroup(
                group_id=f"continuity_{current_group_id}",
                scene_ids=current_sequential_group,
                mode=ExecutionMode.SEQUENTIAL,
                description="Auto-detected continuity group"
            ))

        if parallel_scenes:
            groups.insert(0, SceneGroup(
                group_id="parallel_independent",
                scene_ids=parallel_scenes,
                mode=ExecutionMode.PARALLEL,
                description="Independent scenes (b-roll, inserts, etc.)"
            ))

        # If no groups created, default to sequential for safety
        if not groups:
            return ExecutionGraphBuilder._all_sequential(scenes)

        return ExecutionGraph(groups=groups)

    @staticmethod
    def _analyze_scene(scene) -> Dict:
        """Analyze a scene for continuity indicators"""
        text = f"{scene.title} {scene.description} {' '.join(scene.visual_elements)}"
        text_lower = text.lower()

        # Check for parallel indicators
        is_parallel = any(kw in text_lower for kw in ExecutionGraphBuilder.PARALLEL_KEYWORDS)

        # Check for continuity indicators
        needs_continuity = any(kw in text_lower for kw in ExecutionGraphBuilder.CONTINUITY_KEYWORDS)

        # Check for explicit continuity settings on scene
        if hasattr(scene, 'continuity_group') and scene.continuity_group:
            needs_continuity = True
        if hasattr(scene, 'requires_continuity_from') and scene.requires_continuity_from:
            needs_continuity = True
        if hasattr(scene, 'continuity_elements') and scene.continuity_elements:
            needs_continuity = True

        # Extract key elements for comparison
        characters = ExecutionGraphBuilder._extract_characters(text)
        locations = ExecutionGraphBuilder._extract_locations(text)

        return {
            "is_parallel": is_parallel and not needs_continuity,
            "needs_continuity": needs_continuity,
            "characters": characters,
            "locations": locations,
            "text_lower": text_lower
        }

    @staticmethod
    def _extract_characters(text: str) -> Set[str]:
        """Extract character references from text"""
        # Simple heuristic - look for capitalized words that might be names
        # or common character references
        characters = set()

        # Common character references
        char_patterns = [
            r'\b(protagonist|hero|character|person|man|woman|user|developer|customer)\b',
            r'\b(they|their|them|he|she|his|her)\b',
        ]

        for pattern in char_patterns:
            matches = re.findall(pattern, text.lower())
            characters.update(matches)

        return characters

    @staticmethod
    def _extract_locations(text: str) -> Set[str]:
        """Extract location references from text"""
        locations = set()

        # Common location patterns
        location_patterns = [
            r'\b(office|room|desk|studio|kitchen|bedroom|living room|outdoor|indoor)\b',
            r'\b(background|environment|setting|scene|space)\b',
        ]

        for pattern in location_patterns:
            matches = re.findall(pattern, text.lower())
            locations.update(matches)

        return locations

    @staticmethod
    def _scenes_related(prev_analysis: Dict, curr_analysis: Dict) -> bool:
        """Check if two scenes are related (should be in same continuity group)"""
        # Check for shared characters
        shared_chars = prev_analysis["characters"] & curr_analysis["characters"]
        if shared_chars:
            return True

        # Check for shared locations
        shared_locs = prev_analysis["locations"] & curr_analysis["locations"]
        if shared_locs:
            return True

        # Check for explicit continuity keywords
        if "continues" in curr_analysis["text_lower"]:
            return True
        if "same" in curr_analysis["text_lower"]:
            return True

        return False

    @staticmethod
    def print_graph_summary(graph: ExecutionGraph):
        """Print a human-readable summary of the execution graph"""
        print("\n" + "=" * 60)
        print("EXECUTION GRAPH")
        print("=" * 60)

        errors = graph.validate()
        if errors:
            print("\n[VALIDATION ERRORS]")
            for error in errors:
                print(f"  - {error}")

        print(f"\nTotal Groups: {len(graph.groups)}")
        print(f"Total Scenes: {len(graph.get_all_scene_ids())}")

        for group in graph.groups:
            mode_icon = "||" if group.mode == ExecutionMode.PARALLEL else "->"
            print(f"\n[{group.group_id}] ({group.mode.value})")
            if group.description:
                print(f"  {group.description}")
            print(f"  Scenes: {' {mode_icon} '.join(group.scene_ids)}")
            if group.chain_from_group:
                print(f"  Chains from: {group.chain_from_group}")
            if group.chain_from_scene:
                print(f"  Chains from scene: {group.chain_from_scene}")

        print("\n[EXECUTION WAVES]")
        waves = graph.get_execution_waves()
        for i, wave in enumerate(waves, 1):
            print(f"  Wave {i}: {', '.join(wave)}")

        print("\n" + "=" * 60)
