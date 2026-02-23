"""Script generation from knowledge base content.

Loads KB atoms, builds a concept string, and generates a scene-by-scene
script using the ScriptWriterAgent. Also handles figure discovery and
interactive figure selection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.models.run_manifest import (
    RunManifest, SceneManifest, SceneStatus,
)


LANGUAGE_NAMES = {
    "en": "English", "cs": "Czech", "es": "Spanish", "fr": "French",
    "de": "German", "it": "Italian", "pt": "Portuguese", "ja": "Japanese",
    "ko": "Korean", "zh": "Chinese", "ru": "Russian", "ar": "Arabic",
    "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "da": "Danish",
    "fi": "Finnish", "no": "Norwegian", "tr": "Turkish", "hi": "Hindi",
    "uk": "Ukrainian", "el": "Greek", "ro": "Romanian", "hu": "Hungarian",
    "sk": "Slovak", "bg": "Bulgarian", "hr": "Croatian", "sr": "Serbian",
    "sl": "Slovenian", "th": "Thai", "vi": "Vietnamese", "id": "Indonesian",
    "ms": "Malay", "tl": "Filipino", "he": "Hebrew",
}


def _language_name(code: str) -> str:
    """Convert ISO 639-1 code to full language name."""
    return LANGUAGE_NAMES.get(code, code)


def load_kb_context(kb_project: str) -> dict:
    """Load a KB project and return structured context.

    Returns dict with:
        concept: str — assembled context for script generation
        figures: dict — figure_id → path mapping
        project: KnowledgeProject
        kg: KnowledgeGraph
    """
    from cli.kb import _resolve_project, _load_project, _build_concept_from_kb
    from core.models.knowledge import KnowledgeGraph

    project_dir = _resolve_project(kb_project)
    if not project_dir:
        raise ValueError(f"KB project not found: {kb_project}")

    proj = _load_project(project_dir)

    # Load knowledge graph
    kg_path = project_dir / "knowledge_graph.json"
    if not kg_path.exists():
        raise ValueError(f"No knowledge graph for project: {kb_project}")

    with open(kg_path, encoding="utf-8") as f:
        kg_data = json.load(f)
    kg = KnowledgeGraph.from_dict(kg_data)

    # Build concept
    concept = _build_concept_from_kb(proj, kg, "Create an explainer video", None)

    # Collect figures
    figures = {}
    from core.models.document import AtomType
    for atom_id, atom in kg.atoms.items():
        if atom.atom_type in (AtomType.FIGURE, AtomType.CHART, AtomType.DIAGRAM):
            if hasattr(atom, 'figure_path') and atom.figure_path:
                fig_path = project_dir / atom.figure_path
                if fig_path.exists():
                    desc = atom.caption or atom.content or f"Figure {atom.figure_number}"
                    figures[atom_id] = {
                        "path": str(fig_path),
                        "description": desc[:200],
                        "type": atom.atom_type.value,
                    }

    return {
        "concept": concept,
        "figures": figures,
        "project_dir": str(project_dir),
    }


async def generate_script_from_kb(
    manifest: RunManifest,
    prompt: Optional[str] = None,
    duration: float = 60.0,
    style: str = "explainer",
) -> list[SceneManifest]:
    """Generate scenes from KB content.

    Uses a two-tier approach:
    1. Fast path: extract scene structure directly from KB atoms (no LLM call)
    2. Full path: use ScriptWriterAgent for richer scripts (requires nohup)

    The fast path creates scenes from KB themes, figures, and key content,
    which is good enough for pre-production planning and figure selection.
    """
    # Load KB
    kb_data = load_kb_context(manifest.kb_project)
    concept = kb_data["concept"]
    figures = kb_data.get("figures", {})
    figure_list = list(figures.values())

    # Save concept for potential full script gen later
    if manifest.run_dir:
        concept_path = Path(manifest.run_dir) / "concept.txt"
        full_concept = concept
        if prompt:
            full_concept = f"PRODUCTION DIRECTION: {prompt}\n\n{concept}"
        # Add language directive if non-English
        if manifest.language and manifest.language != "en":
            lang_directive = f"LANGUAGE: Write the entire script (narration, titles, descriptions) in {_language_name(manifest.language)}. All voiceover text must be in {_language_name(manifest.language)}.\n\n"
            full_concept = lang_directive + full_concept
        concept_path.write_text(full_concept, encoding="utf-8")

    # Fast path: build scenes from KB structure
    scene_manifests = _scenes_from_kb_structure(concept, figures, duration)

    # Match figures to scenes
    for sm in scene_manifests:
        if figure_list:
            best_match = _match_figure_to_manifest_scene(sm, figure_list)
            if best_match:
                sm.asset_path = best_match["path"]
                sm.asset_type = "figure"
                sm.provider = "local_asset"
                sm.options.append({
                    "label": "KB Figure",
                    "type": "figure",
                    "path": best_match["path"],
                    "description": best_match["description"],
                })

        # Always add AI generation as an option
        sm.options.append({
            "label": "AI Generated",
            "type": "video",
            "prompt": sm.video_prompt,
        })

    return scene_manifests


def _scenes_from_kb_structure(concept: str, figures: dict, duration: float) -> list[SceneManifest]:
    """Build scene plan directly from KB concept structure.

    Parses the concept string to find themes, figures, and content sections,
    then creates a scene for each major topic.
    """
    scenes = []
    lines = concept.split("\n")

    # Extract key themes
    themes = []
    content_blocks = []
    figure_descs = []
    current_section = None

    for line in lines:
        if line.startswith("KEY THEMES:"):
            themes = [t.strip() for t in line.replace("KEY THEMES:", "").split(",") if t.strip()]
        elif line.startswith("FIGURES AVAILABLE:"):
            current_section = "figures"
        elif line.startswith("CONTENT TO COVER:"):
            current_section = "content"
        elif line.startswith("PRODUCTION DIRECTION:"):
            current_section = None
        elif current_section == "figures" and line.strip().startswith("-"):
            figure_descs.append(line.strip().lstrip("- "))
        elif current_section == "content" and line.strip():
            content_blocks.append(line.strip())

    # Build scenes from themes (primary) or content blocks (fallback)
    sources = themes if themes else content_blocks[:8]
    if not sources:
        sources = [f"Section {i+1}" for i in range(6)]

    # Cap at reasonable scene count
    sources = sources[:8]
    scene_duration = duration / len(sources)

    for i, source in enumerate(sources):
        title = source[:60].strip()
        # Generate a description from the title
        desc = f"Visual explanation of: {title}"
        if i < len(content_blocks):
            desc = content_blocks[i][:200]

        scenes.append(SceneManifest(
            scene_id=f"scene_{i+1:03d}",
            title=title,
            status=SceneStatus.PENDING,
            duration=scene_duration,
            provider="auto",
            video_prompt=desc,
        ))

    return scenes


def _match_figure_to_manifest_scene(scene: SceneManifest, figures: list[dict]) -> Optional[dict]:
    """Match a SceneManifest to available figures by keyword overlap."""
    scene_words = set(scene.title.lower().split())
    if scene.video_prompt:
        scene_words |= set(scene.video_prompt.lower().split())

    stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                 "to", "for", "of", "with", "and", "or", "but", "this", "that"}
    scene_words -= stopwords

    best_score = 0
    best_fig = None

    for fig in figures:
        fig_words = set(fig["description"].lower().split()) - stopwords
        overlap = len(scene_words & fig_words)
        if overlap > best_score and overlap >= 2:
            best_score = overlap
            best_fig = fig

    return best_fig


def _match_figure_to_scene(scene, figures: list[dict]) -> Optional[dict]:
    """Simple keyword matching between a scene and available figures."""
    scene_words = set(scene.title.lower().split() + scene.description.lower().split())
    # Remove stopwords
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                 "to", "for", "of", "with", "and", "or", "but", "this", "that"}
    scene_words -= stopwords

    best_score = 0
    best_fig = None

    for fig in figures:
        fig_words = set(fig["description"].lower().split()) - stopwords
        overlap = len(scene_words & fig_words)
        if overlap > best_score and overlap >= 2:
            best_score = overlap
            best_fig = fig

    return best_fig


def present_figure_options(manifest: RunManifest) -> None:
    """Interactive figure selection — present options for each scene.

    Prints scene-by-scene with lettered options. User selects per scene.
    """
    print("\n🎨 Interactive Figure Selection\n")
    print("For each scene, pick a visual source:\n")

    for scene in manifest.scenes:
        if not scene.options:
            continue

        print(f"  Scene: {scene.title}")
        print(f"  Prompt: {scene.video_prompt[:80]}..." if len(scene.video_prompt) > 80
              else f"  Prompt: {scene.video_prompt}")

        for j, opt in enumerate(scene.options):
            letter = chr(65 + j)  # A, B, C...
            if opt["type"] == "figure":
                print(f"    [{letter}] 📄 {opt['label']}: {opt['description'][:60]}")
            elif opt["type"] == "video":
                print(f"    [{letter}] 🎬 {opt['label']}: AI-generated video")
            elif opt["type"] == "diagram":
                print(f"    [{letter}] 📊 {opt['label']}: Mermaid diagram")
            else:
                print(f"    [{letter}] {opt['label']}")

        # For now, auto-select first option (interactive input requires TTY)
        if scene.options:
            selected = scene.options[0]
            scene.selected_option = "A"
            if selected.get("path"):
                scene.asset_path = selected["path"]
                scene.provider = "local_asset"
                scene.asset_type = selected.get("type", "figure")
            print(f"    → Auto-selected: [A] {selected['label']}")
        print()
