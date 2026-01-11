"""Scene execution graph models for mixed parallel/sequential generation"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
from enum import Enum


class ExecutionMode(Enum):
    PARALLEL = "parallel"      # Independent scenes, run simultaneously
    SEQUENTIAL = "sequential"  # Chained scenes, each depends on previous


@dataclass
class SceneGroup:
    """A group of scenes with shared execution mode"""
    group_id: str
    scene_ids: List[str]  # References to Scene.scene_id
    mode: ExecutionMode

    # For sequential groups: which generation to chain from
    chain_from_group: Optional[str] = None  # Previous group's last scene
    chain_from_scene: Optional[str] = None  # Specific scene ID

    # Metadata
    description: Optional[str] = None  # "Hero's journey - must be continuous"


@dataclass
class ExecutionGraph:
    """
    Defines execution order and dependencies for scene generation.

    Example:
        graph = ExecutionGraph(groups=[
            SceneGroup("intro", ["scene_1", "scene_2"], PARALLEL),
            SceneGroup("hero_arc", ["scene_3", "scene_4", "scene_5"], SEQUENTIAL),
            SceneGroup("b_roll", ["scene_6", "scene_7"], PARALLEL),
            SceneGroup("finale", ["scene_8"], SEQUENTIAL, chain_from_group="hero_arc"),
        ])

    This means:
    - scene_1 and scene_2 run in parallel (no continuity needed)
    - scene_3 -> scene_4 -> scene_5 run sequentially (chained for continuity)
    - scene_6 and scene_7 run in parallel (b-roll, independent)
    - scene_8 chains from the end of scene_5 (hero_arc group)

    Visual:
        [scene_1]─────┐
                      ├──> [scene_3] -> [scene_4] -> [scene_5]──> [scene_8]
        [scene_2]─────┘                                    │
                                                           │
        [scene_6]──────────────────────────────────────────┘
        [scene_7]──────────────────────────────────────────┘
    """
    groups: List[SceneGroup] = field(default_factory=list)

    def get_group(self, group_id: str) -> Optional[SceneGroup]:
        """Get a group by ID"""
        return next((g for g in self.groups if g.group_id == group_id), None)

    def get_scene_group(self, scene_id: str) -> Optional[SceneGroup]:
        """Find which group a scene belongs to"""
        for group in self.groups:
            if scene_id in group.scene_ids:
                return group
        return None

    def get_all_scene_ids(self) -> List[str]:
        """Get all scene IDs in graph order"""
        result = []
        for group in self.groups:
            result.extend(group.scene_ids)
        return result

    def get_execution_waves(self) -> List[List[str]]:
        """
        Returns execution waves - scenes in each wave can run in parallel.
        Respects group dependencies and sequential ordering.

        Returns:
            List of waves, where each wave is a list of scene_ids that can run in parallel
        """
        waves = []
        completed_groups: Set[str] = set()
        completed_scenes: Set[str] = set()

        # Build dependency map
        group_deps: Dict[str, Set[str]] = {}
        for group in self.groups:
            deps = set()
            if group.chain_from_group:
                deps.add(group.chain_from_group)
            if group.chain_from_scene:
                # Find which group contains this scene
                for g in self.groups:
                    if group.chain_from_scene in g.scene_ids:
                        deps.add(g.group_id)
                        break
            group_deps[group.group_id] = deps

        # Process groups in dependency order
        remaining_groups = list(self.groups)

        while remaining_groups:
            # Find groups whose dependencies are satisfied
            ready_groups = []
            for group in remaining_groups:
                deps = group_deps[group.group_id]
                if deps.issubset(completed_groups):
                    ready_groups.append(group)

            if not ready_groups:
                # Circular dependency or error - break out
                break

            # Process ready groups
            for group in ready_groups:
                if group.mode == ExecutionMode.PARALLEL:
                    # All scenes in parallel group can run in same wave
                    # (or merge with existing parallel wave)
                    if waves and all(
                        self.get_scene_group(s).mode == ExecutionMode.PARALLEL
                        for s in waves[-1]
                        if self.get_scene_group(s)
                    ):
                        # Extend last parallel wave
                        waves[-1].extend(group.scene_ids)
                    else:
                        waves.append(list(group.scene_ids))
                    completed_scenes.update(group.scene_ids)
                else:
                    # Sequential group - each scene is its own wave
                    for scene_id in group.scene_ids:
                        waves.append([scene_id])
                        completed_scenes.add(scene_id)

                completed_groups.add(group.group_id)
                remaining_groups.remove(group)

        return waves

    def validate(self) -> List[str]:
        """
        Validate the execution graph.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check for duplicate scene IDs
        all_scenes = []
        for group in self.groups:
            all_scenes.extend(group.scene_ids)

        seen = set()
        for scene_id in all_scenes:
            if scene_id in seen:
                errors.append(f"Duplicate scene_id: {scene_id}")
            seen.add(scene_id)

        # Check chain references
        for group in self.groups:
            if group.chain_from_group:
                if not self.get_group(group.chain_from_group):
                    errors.append(
                        f"Group '{group.group_id}' references unknown group '{group.chain_from_group}'"
                    )

            if group.chain_from_scene:
                if group.chain_from_scene not in all_scenes:
                    errors.append(
                        f"Group '{group.group_id}' references unknown scene '{group.chain_from_scene}'"
                    )

        # Check for circular dependencies
        def has_cycle(group_id: str, visited: Set[str], path: Set[str]) -> bool:
            visited.add(group_id)
            path.add(group_id)

            group = self.get_group(group_id)
            if group and group.chain_from_group:
                dep = group.chain_from_group
                if dep in path:
                    return True
                if dep not in visited and has_cycle(dep, visited, path):
                    return True

            path.remove(group_id)
            return False

        visited: Set[str] = set()
        for group in self.groups:
            if group.group_id not in visited:
                if has_cycle(group.group_id, visited, set()):
                    errors.append(f"Circular dependency detected involving group '{group.group_id}'")

        return errors


@dataclass
class GenerationDependency:
    """Tracks what a scene generation depends on"""
    scene_id: str
    depends_on_scene_id: Optional[str] = None
    depends_on_generation_id: Optional[str] = None  # Luma generation UUID

    # The actual keyframe to chain from
    keyframe_url: Optional[str] = None  # URL to last frame image
    keyframe_type: str = "generation"  # "generation" or "image"
