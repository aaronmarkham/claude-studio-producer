"""Figure matching and distribution for video scenes.

Matches KB-extracted figures to scenes by keyword, with fallback distribution.
"""

from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

def _get_theme():
    from cli.theme import get_theme
    return get_theme()

def _match_scene_to_figure(scene, kb_figure_paths: dict, knowledge_graph) -> Optional[str]:
    """
    Match a scene to a KB figure by keyword matching.

    Searches figure atoms in the knowledge graph for matches with scene concepts.
    Returns the path to the best matching figure, or None.
    """
    if not knowledge_graph or not kb_figure_paths:
        return None

    # Build search terms from scene
    search_terms = set()
    for term in scene.key_concepts + scene.technical_terms:
        search_terms.add(term.lower())
        for word in term.lower().split():
            if len(word) > 3:
                search_terms.add(word)

    if not search_terms:
        return None

    # Get atoms dict
    atoms = getattr(knowledge_graph, 'atoms', {})

    best_match_id = None
    best_score = 0

    for atom_id, atom in atoms.items():
        # Check if it's a figure atom
        atom_type = getattr(atom, 'atom_type', None)
        if atom_type is None and isinstance(atom, dict):
            atom_type = atom.get('atom_type')

        type_str = atom_type.value if hasattr(atom_type, 'value') else str(atom_type)
        if type_str != 'figure':
            continue

        # Get caption for matching
        caption = getattr(atom, 'caption', None)
        if caption is None and isinstance(atom, dict):
            caption = atom.get('caption')
        if not caption:
            continue

        # Score by keyword match
        caption_lower = caption.lower()
        score = sum(1 for term in search_terms if term in caption_lower)

        if score > best_score:
            best_score = score
            best_match_id = atom_id

    # Need at least 2 matching terms and the figure must exist in KB
    if best_score >= 2 and best_match_id:
        # Try to find the figure file - atom IDs might differ between training and KB
        # Try exact match first
        if best_match_id in kb_figure_paths:
            return kb_figure_paths[best_match_id]

        # Try matching by figure number suffix (e.g., fig_005)
        suffix = best_match_id.split('_')[-1] if '_' in best_match_id else None
        if suffix:
            for kb_atom_id, path in kb_figure_paths.items():
                if kb_atom_id.endswith(f"_{suffix}"):
                    return path

    return None


def distribute_figures_to_scenes(
    scenes: list,
    visual_plans: list,
    kb_figure_paths: dict,
    allocation: dict = None
) -> int:
    """
    Distribute KB figures to scenes when keyword matching fails.

    Assigns figures to high-importance primary scenes in order.
    Returns count of figures assigned.
    """
    if not kb_figure_paths:
        return 0

    # Sort figures by their index for consistent ordering
    sorted_figures = sorted(kb_figure_paths.items(), key=lambda x: x[0])

    # Find primary scenes (scenes that will generate DALL-E) and score them
    from core.video_production import score_scene_importance

    scene_scores = []
    for i, (scene, plan) in enumerate(zip(scenes, visual_plans)):
        # Skip scenes that already have a figure
        if getattr(plan, 'kb_figure_path', None):
            continue

        # Skip non-primary scenes if budget allocation exists
        if allocation:
            budget_mode = getattr(plan, 'budget_mode', None)
            if budget_mode in ['text_only', 'shared']:
                continue

        # Skip scenes with empty DALL-E prompt (won't be rendered)
        if not plan.dalle_prompt:
            continue

        score = score_scene_importance(scene)
        scene_scores.append((i, scene, plan, score))

    # Sort by importance score (highest first)
    scene_scores.sort(key=lambda x: x[3], reverse=True)

    # Assign figures to top scenes
    figures_assigned = 0
    figure_idx = 0

    for scene_idx, scene, plan, score in scene_scores:
        if figure_idx >= len(sorted_figures):
            break

        # Assign figure to this scene
        fig_id, fig_path = sorted_figures[figure_idx]
        plan.kb_figure_path = fig_path
        figure_idx += 1
        figures_assigned += 1

    return figures_assigned


def load_kb_figures(project_name: str) -> dict:
    """Load figure paths from a KB project."""
    from cli.kb import _resolve_project, _load_project

    project_dir = _resolve_project(project_name)
    if not project_dir:
        raise click.ClickException(f"KB project not found: {project_name}")

    project = _load_project(project_dir)

    # Build figure path mapping: atom_id -> file path
    figure_paths = {}
    sources_dir = project_dir / "sources"

    if sources_dir.exists():
        for source_dir in sources_dir.iterdir():
            if source_dir.is_dir():
                figures_dir = source_dir / "figures"
                if figures_dir.exists():
                    for fig_file in figures_dir.glob("*.png"):
                        atom_id = fig_file.stem  # filename without extension
                        figure_paths[atom_id] = str(fig_file)

    return {
        "project": project,
        "project_dir": project_dir,
        "figure_paths": figure_paths
    }
