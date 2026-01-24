"""Knowledge base CLI - Multi-source knowledge projects for video production"""

import sys
import json
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

console = Console()

KB_DIR = Path("artifacts") / "kb"


def _resolve_project(project: str) -> Optional[Path]:
    """Resolve a project identifier to its directory.

    Tries: exact dir name, prefix match on ID, name match in project.json.
    """
    if not KB_DIR.exists():
        return None

    # Exact match
    exact = KB_DIR / project
    if exact.is_dir():
        return exact

    # Prefix match on directory name
    for d in KB_DIR.iterdir():
        if d.is_dir() and d.name.startswith(project):
            return d

    # Name match (case-insensitive) via project.json
    for d in KB_DIR.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "project.json"
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("name", "").lower() == project.lower():
                    return d
            except (json.JSONDecodeError, OSError):
                continue

    return None


def _load_project(project_dir: Path):
    """Load a KnowledgeProject from its directory"""
    from core.models.knowledge import KnowledgeProject

    meta_path = project_dir / "project.json"
    with open(meta_path, encoding="utf-8") as f:
        data = json.load(f)
    return KnowledgeProject.from_dict(data)


def _save_project(project_dir: Path, project):
    """Save a KnowledgeProject to its directory"""
    meta_path = project_dir / "project.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, indent=2, ensure_ascii=False)


def _rebuild_knowledge_graph(project_dir: Path, project) -> None:
    """Rebuild the unified KnowledgeGraph from all source DocumentGraphs.

    Merges atoms, builds topic/entity indices, detects cross-source links
    by shared entity co-occurrence.
    """
    from core.models.knowledge import KnowledgeGraph, CrossSourceLink
    from core.models.document import DocumentAtom, AtomType

    all_atoms: Dict[str, DocumentAtom] = {}
    atom_sources: Dict[str, str] = {}
    topic_index: Dict[str, List[str]] = {}
    entity_index: Dict[str, List[str]] = {}

    sources_dir = project_dir / "sources"

    for source_id, source in project.sources.items():
        graph_path = sources_dir / source_id / "document_graph.json"
        if not graph_path.exists():
            continue

        with open(graph_path, encoding="utf-8") as f:
            graph_data = json.load(f)

        for atom_id, atom_data in graph_data.get("atoms", {}).items():
            atom = DocumentAtom(
                atom_id=atom_data["atom_id"],
                atom_type=AtomType(atom_data["atom_type"]),
                content=atom_data.get("content", ""),
                source_page=atom_data.get("source_page"),
                source_location=atom_data.get("source_location"),
                topics=atom_data.get("topics", []),
                entities=atom_data.get("entities", []),
                relationships=atom_data.get("relationships", []),
                importance_score=atom_data.get("importance_score", 0.5),
                caption=atom_data.get("caption"),
                figure_number=atom_data.get("figure_number"),
                data_summary=atom_data.get("data_summary"),
            )
            all_atoms[atom_id] = atom
            atom_sources[atom_id] = source_id

            # Build topic index
            for topic in atom.topics:
                if topic not in topic_index:
                    topic_index[topic] = []
                topic_index[topic].append(atom_id)

            # Build entity index
            for entity in atom.entities:
                if entity not in entity_index:
                    entity_index[entity] = []
                entity_index[entity].append(atom_id)

    # Detect cross-source links via shared entities
    cross_links: List[CrossSourceLink] = []
    link_counter = 0

    for entity, atom_ids in entity_index.items():
        # Get unique sources for this entity
        sources_with_entity = {}
        for aid in atom_ids:
            sid = atom_sources.get(aid)
            if sid:
                if sid not in sources_with_entity:
                    sources_with_entity[sid] = []
                sources_with_entity[sid].append(aid)

        # If entity appears in 2+ sources, create cross-links
        source_ids = list(sources_with_entity.keys())
        if len(source_ids) >= 2:
            for i in range(len(source_ids) - 1):
                for j in range(i + 1, len(source_ids)):
                    # Link first atom from each source
                    src_a = source_ids[i]
                    src_b = source_ids[j]
                    atom_a = sources_with_entity[src_a][0]
                    atom_b = sources_with_entity[src_b][0]

                    link_counter += 1
                    cross_links.append(CrossSourceLink(
                        link_id=f"link_{link_counter:04d}",
                        source_atom_id=atom_a,
                        target_atom_id=atom_b,
                        source_source_id=src_a,
                        target_source_id=src_b,
                        relationship="same_topic",
                        confidence=0.6,
                        created_by="auto",
                    ))

    # Identify key themes (topics appearing in most sources, filtering noise)
    source_count = len(project.sources)
    key_themes = []
    # Stopwords that shouldn't be standalone themes
    theme_stopwords = {
        "this", "that", "with", "from", "have", "been", "their", "which",
        "also", "more", "than", "into", "each", "such", "only", "other",
        "some", "these", "those", "over", "many", "most", "both", "does",
        "used", "using", "based", "however", "results", "experimental",
        "international", "introduction", "related", "conclusion", "nature",
        "conference", "proceedings", "references", "abstract", "proposed",
        "machine", "neural", "network", "networks", "learning", "training",
        "computer", "vision", "language", "intelligence", "artificial",
        "analysis", "system", "systems", "performance", "algorithm",
        "knowledge", "information", "processing", "research",
    }
    if source_count > 0:
        for topic, atom_ids in sorted(topic_index.items(), key=lambda x: -len(x[1])):
            # Skip stopwords and short single words (keep multi-word topics)
            if topic.lower() in theme_stopwords:
                continue
            # Single words must be at least 6 chars to be meaningful themes
            if ' ' not in topic and len(topic) < 6:
                continue
            topic_sources = set(atom_sources.get(aid) for aid in atom_ids)
            topic_sources.discard(None)
            if len(topic_sources) >= min(2, source_count):
                key_themes.append(topic)
            if len(key_themes) >= 10:
                break

    graph = KnowledgeGraph(
        project_id=project.project_id,
        atoms=all_atoms,
        atom_sources=atom_sources,
        cross_links=cross_links,
        topic_index=topic_index,
        entity_index=entity_index,
        key_themes=key_themes,
    )

    # Save (exclude raw atom content for large graphs, keep references)
    graph_path = project_dir / "knowledge_graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph.to_dict(), f, indent=2, ensure_ascii=False)

    project.has_knowledge_graph = True


@click.group()
def kb_cmd():
    """Knowledge base management

    \b
    Create and manage multi-source knowledge projects for video production.

    \b
    Examples:
      claude-studio kb create "CRISPR Research"
      claude-studio kb add my-project --paper paper.pdf --mock
      claude-studio kb show my-project
      claude-studio kb sources my-project
      claude-studio kb list
    """
    pass


@kb_cmd.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Project description")
@click.option("--tags", "-t", multiple=True, help="Tags for the project")
def create_cmd(name: str, description: str, tags: tuple):
    """Create a new knowledge project."""
    from core.models.knowledge import KnowledgeProject, generate_id

    now = datetime.now().isoformat()
    project_id = generate_id("kb", f"{name}_{now}")

    project = KnowledgeProject(
        project_id=project_id,
        name=name,
        description=description,
        created_at=now,
        updated_at=now,
        tags=list(tags),
    )

    # Create directory structure
    project_dir = KB_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sources").mkdir(exist_ok=True)
    (project_dir / "notes").mkdir(exist_ok=True)
    (project_dir / "connections").mkdir(exist_ok=True)

    # Save project metadata
    _save_project(project_dir, project)

    # Save empty knowledge graph
    from core.models.knowledge import KnowledgeGraph
    empty_graph = KnowledgeGraph(project_id=project_id)
    with open(project_dir / "knowledge_graph.json", "w", encoding="utf-8") as f:
        json.dump(empty_graph.to_dict(), f, indent=2)

    console.print(Panel.fit(
        f"[bold green]Knowledge Project Created[/bold green]\n"
        f"[dim]ID:[/dim] {project_id}\n"
        f"[dim]Name:[/dim] {name}\n"
        f"[dim]Location:[/dim] {project_dir}",
        border_style="green",
    ))


@kb_cmd.command("add")
@click.argument("project")
@click.option("--paper", type=click.Path(exists=True), help="PDF paper to add")
@click.option("--note", "note_text", help="Add a text note as a source")
@click.option("--title", "-t", help="Override source title")
@click.option("--mock", is_flag=True, help="Use mock analysis (no LLM calls)")
def add_cmd(project: str, paper: str, note_text: str, title: str, mock: bool):
    """Add a source to a knowledge project.

    Currently supports --paper (PDF files) and --note (text notes).
    """
    project_dir = _resolve_project(project)
    if not project_dir:
        console.print(f"[red]Project not found:[/red] {project}")
        console.print("[dim]Use 'claude-studio kb list' to see available projects.[/dim]")
        return

    if not paper and not note_text:
        console.print("[red]Specify a source to add:[/red] --paper <file.pdf> or --note \"text\"")
        return

    proj = _load_project(project_dir)
    console.print(f"[cyan]Adding source to:[/cyan] {proj.name}\n")

    if paper:
        asyncio.run(_add_paper(project_dir, proj, paper, title, mock))
    elif note_text:
        _add_note(project_dir, proj, note_text, title)


async def _add_paper(project_dir: Path, proj, paper_path: str, title: str, mock: bool):
    """Add a PDF paper as a knowledge source"""
    from core.models.knowledge import KnowledgeSource, SourceType, generate_id
    from agents.document_ingestor import DocumentIngestorAgent

    source_path = Path(paper_path).resolve()

    console.print("[cyan]Phase 1:[/cyan] Extracting content with PyMuPDF...")

    try:
        from core.claude_client import ClaudeClient
        client = ClaudeClient() if not mock else None
        agent = DocumentIngestorAgent(claude_client=client, mock_mode=mock)
        graph = await agent.ingest(str(source_path))
    except ImportError as e:
        if "fitz" in str(e) or "pymupdf" in str(e).lower():
            console.print("[red]PyMuPDF not installed.[/red]")
            console.print("Install with: [bold]pip install pymupdf[/bold]")
            return
        raise
    except Exception as e:
        console.print(f"[red]Ingestion failed:[/red] {e}")
        return

    # Generate source ID from file content hash
    file_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()[:12]
    source_id = f"src_{file_hash}"

    # Check for duplicate
    if source_id in proj.sources:
        console.print(f"[yellow]Source already exists:[/yellow] {source_id}")
        console.print(f"[dim]Title: {proj.sources[source_id].title}[/dim]")
        return

    # Save source DocumentGraph and figures
    source_dir = project_dir / "sources" / source_id
    source_dir.mkdir(parents=True, exist_ok=True)

    with open(source_dir / "document_graph.json", "w", encoding="utf-8") as f:
        json.dump(graph.to_dict(), f, indent=2, ensure_ascii=False)

    # Save figures
    figure_count = 0
    for atom_id in graph.figures:
        atom = graph.get_atom(atom_id)
        if atom and atom.raw_data:
            figures_dir = source_dir / "figures"
            figures_dir.mkdir(exist_ok=True)
            fig_path = figures_dir / f"{atom_id}.png"
            with open(fig_path, "wb") as f:
                f.write(atom.raw_data)
            figure_count += 1

    # Create KnowledgeSource
    source_title = title or graph.title or source_path.stem
    source = KnowledgeSource(
        source_id=source_id,
        source_type=SourceType.PAPER,
        title=source_title,
        authors=graph.authors,
        added_at=datetime.now().isoformat(),
        source_path=str(source_path),
        document_id=graph.document_id,
        one_sentence=graph.one_sentence,
        atom_count=graph.atom_count,
        page_count=graph.page_count,
        figure_count=figure_count,
    )

    proj.add_source(source)

    # Rebuild unified knowledge graph
    console.print("[cyan]Rebuilding knowledge graph...[/cyan]")
    _rebuild_knowledge_graph(project_dir, proj)

    # Save updated project
    _save_project(project_dir, proj)

    # Load graph to show stats
    with open(project_dir / "knowledge_graph.json", encoding="utf-8") as f:
        kg_data = json.load(f)
    cross_link_count = len(kg_data.get("cross_links", []))
    shared_entities = {
        e: aids for e, aids in kg_data.get("entity_index", {}).items()
        if len(set(kg_data.get("atom_sources", {}).get(aid, "") for aid in aids)) > 1
    }

    console.print(f"[green]Source added:[/green] {source_id} (paper)")
    console.print(f"  [dim]Title:[/dim] {source_title}")
    console.print(f"  [dim]Atoms:[/dim] {source.atom_count} | [dim]Pages:[/dim] {source.page_count} | [dim]Figures:[/dim] {figure_count}")
    console.print(f"[green]Knowledge graph rebuilt:[/green] {proj.total_atoms} atoms, {cross_link_count} cross-links")
    if shared_entities:
        top_shared = list(shared_entities.keys())[:5]
        console.print(f"  [dim]Shared entities:[/dim] {', '.join(top_shared)}")


def _add_note(project_dir: Path, proj, note_text: str, title: str):
    """Add a text note as a knowledge source"""
    from core.models.knowledge import Note, generate_id

    now = datetime.now().isoformat()
    note_id = generate_id("note", f"{note_text[:50]}_{now}")

    note = Note(
        note_id=note_id,
        title=title or note_text[:50],
        content=note_text,
        created_at=now,
        updated_at=now,
    )

    proj.notes[note_id] = note
    proj.updated_at = now

    # Save note to file
    note_path = project_dir / "notes" / f"{note_id}.json"
    with open(note_path, "w", encoding="utf-8") as f:
        json.dump(note.to_dict(), f, indent=2, ensure_ascii=False)

    # Save updated project
    _save_project(project_dir, proj)

    console.print(f"[green]Note added:[/green] {note_id}")
    console.print(f"  [dim]Title:[/dim] {note.title}")


@kb_cmd.command("show")
@click.argument("project")
@click.option("--graph", "-g", is_flag=True, help="Show knowledge graph stats")
def show_cmd(project: str, graph: bool):
    """Show overview of a knowledge project."""
    project_dir = _resolve_project(project)
    if not project_dir:
        console.print(f"[red]Project not found:[/red] {project}")
        return

    proj = _load_project(project_dir)

    # Header
    lines = [
        f"[bold]{proj.name}[/bold]",
        f"[dim]ID:[/dim] {proj.project_id}",
    ]
    if proj.description:
        lines.append(f"[dim]Description:[/dim] {proj.description}")
    lines.append(f"[dim]Created:[/dim] {proj.created_at[:16] if proj.created_at else 'unknown'}")
    if proj.tags:
        lines.append(f"[dim]Tags:[/dim] {', '.join(proj.tags)}")
    lines.append("")
    lines.append(f"Sources: {proj.source_count} | Atoms: {proj.total_atoms} | Figures: {proj.total_figures} | Pages: {proj.total_pages}")

    console.print(Panel("\n".join(lines), border_style="blue"))

    # Sources summary
    if proj.sources:
        console.print("\n[bold]Sources:[/bold]")
        for i, (sid, src) in enumerate(proj.sources.items(), 1):
            type_badge = f"[cyan]{src.source_type.value}[/cyan]"
            console.print(f"  {i}. {src.title} ({type_badge}, {src.atom_count} atoms)")
            if i >= 10:
                remaining = proj.source_count - 10
                if remaining > 0:
                    console.print(f"  [dim]... and {remaining} more[/dim]")
                break

    # Notes summary
    if proj.notes:
        console.print(f"\n[bold]Notes:[/bold] {len(proj.notes)}")
        for nid, note in list(proj.notes.items())[:3]:
            console.print(f"  - {note.title}")

    # Knowledge graph stats
    if graph and proj.has_knowledge_graph:
        kg_path = project_dir / "knowledge_graph.json"
        if kg_path.exists():
            with open(kg_path, encoding="utf-8") as f:
                kg_data = json.load(f)

            from core.models.knowledge import KnowledgeGraph
            kg = KnowledgeGraph.from_dict(kg_data)

            console.print(f"\n[bold]Knowledge Graph:[/bold]")
            console.print(f"  Atoms: {kg.atom_count}")
            console.print(f"  Cross-links: {kg.cross_link_count}")
            console.print(f"  Topics indexed: {len(kg.topic_index)}")
            console.print(f"  Entities indexed: {len(kg.entity_index)}")

            shared_topics = kg.get_shared_topics()
            if shared_topics:
                console.print(f"  Shared topics: {len(shared_topics)}")
                top = list(shared_topics.keys())[:5]
                console.print(f"    [dim]{', '.join(top)}[/dim]")

            shared_entities = kg.get_shared_entities()
            if shared_entities:
                console.print(f"  Shared entities: {len(shared_entities)}")
                top = list(shared_entities.keys())[:5]
                console.print(f"    [dim]{', '.join(top)}[/dim]")

            if kg.key_themes:
                console.print(f"  Key themes: {', '.join(kg.key_themes[:5])}")


@kb_cmd.command("sources")
@click.argument("project")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed info per source")
def sources_cmd(project: str, verbose: bool):
    """List sources in a knowledge project."""
    project_dir = _resolve_project(project)
    if not project_dir:
        console.print(f"[red]Project not found:[/red] {project}")
        return

    proj = _load_project(project_dir)

    if not proj.sources:
        console.print(f"[dim]No sources in project '{proj.name}'[/dim]")
        console.print("[dim]Add one with: claude-studio kb add <project> --paper <file.pdf>[/dim]")
        return

    table = Table(title=f"Sources: {proj.name}", box=box.SIMPLE)
    table.add_column("ID", style="dim", max_width=16)
    table.add_column("Type", style="cyan")
    table.add_column("Title", max_width=40)
    table.add_column("Atoms", justify="right")
    table.add_column("Pages", justify="right")
    table.add_column("Figures", justify="right")
    if verbose:
        table.add_column("Summary", max_width=50)

    for sid, src in proj.sources.items():
        row = [
            sid[-12:],
            src.source_type.value,
            src.title[:40] if src.title else "(untitled)",
            str(src.atom_count),
            str(src.page_count),
            str(src.figure_count),
        ]
        if verbose:
            row.append(src.one_sentence[:50] if src.one_sentence else "")
        table.add_row(*row)

    console.print(table)


@kb_cmd.command("list")
def list_cmd():
    """List all knowledge projects."""
    if not KB_DIR.exists():
        console.print("[dim]No knowledge projects yet.[/dim]")
        console.print("[dim]Create one with: claude-studio kb create \"Project Name\"[/dim]")
        return

    projects = []
    for d in sorted(KB_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "project.json"
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    data = json.load(f)
                projects.append(data)
            except (json.JSONDecodeError, OSError):
                continue

    if not projects:
        console.print("[dim]No knowledge projects found.[/dim]")
        console.print("[dim]Create one with: claude-studio kb create \"Project Name\"[/dim]")
        return

    table = Table(title="Knowledge Projects", box=box.SIMPLE)
    table.add_column("ID", style="dim", max_width=16)
    table.add_column("Name", style="bold")
    table.add_column("Sources", justify="right")
    table.add_column("Atoms", justify="right")
    table.add_column("Updated", max_width=16)

    for p in projects:
        table.add_row(
            p["project_id"][-12:],
            p["name"],
            str(len(p.get("sources", {}))),
            str(p.get("total_atoms", 0)),
            p.get("updated_at", "")[:16],
        )

    console.print(table)


def _build_concept_from_kb(
    proj: 'KnowledgeProject',
    kg: 'KnowledgeGraph',
    prompt: str,
    source_filter: Optional[List[str]] = None,
) -> str:
    """Build a rich concept string from KB content for the production pipeline.

    Assembles structured context from the knowledge graph that the ScriptWriterAgent
    can use to create an informed, accurate script.
    """
    from core.models.document import AtomType

    sections = []

    # Header
    sections.append(f"KNOWLEDGE BASE: {proj.name}")
    if proj.description:
        sections.append(f"DESCRIPTION: {proj.description}")

    # Sources summary
    source_lines = []
    for sid, src in proj.sources.items():
        if source_filter and sid not in source_filter:
            continue
        line = f"- {src.title} ({src.source_type.value}, {src.atom_count} atoms)"
        if src.one_sentence:
            line += f"\n  Summary: {src.one_sentence}"
        source_lines.append(line)
    if source_lines:
        sections.append("SOURCES:\n" + "\n".join(source_lines))

    # Production direction (user's prompt)
    sections.append(f"PRODUCTION DIRECTION: {prompt}")

    # Key themes from the knowledge graph
    if kg.key_themes:
        sections.append("KEY THEMES: " + ", ".join(kg.key_themes))

    # Collect atoms, filtering by source if needed
    atoms_to_use = []
    for atom_id, atom in kg.atoms.items():
        if source_filter:
            atom_source = kg.atom_sources.get(atom_id, "")
            if atom_source not in source_filter:
                continue
        atoms_to_use.append(atom)

    # Sort by importance (highest first)
    atoms_to_use.sort(key=lambda a: a.importance_score, reverse=True)

    # Build content sections by type priority
    char_budget = 4000
    chars_used = 0

    # 1. Abstracts (full content)
    abstracts = [a for a in atoms_to_use if a.atom_type == AtomType.ABSTRACT]
    if abstracts:
        abstract_lines = []
        for a in abstracts[:3]:
            if chars_used + len(a.content) > char_budget:
                break
            abstract_lines.append(a.content)
            chars_used += len(a.content)
        if abstract_lines:
            sections.append("ABSTRACTS:\n" + "\n\n".join(abstract_lines))

    # 2. Key quotes
    quotes = [a for a in atoms_to_use if a.atom_type == AtomType.QUOTE]
    if quotes:
        quote_lines = []
        for a in quotes[:5]:
            if chars_used + len(a.content) > char_budget:
                break
            quote_lines.append(f'"{a.content}"')
            chars_used += len(a.content)
        if quote_lines:
            sections.append("KEY QUOTES:\n" + "\n".join(quote_lines))

    # 3. Section headers (for structure overview)
    headers = [a for a in atoms_to_use if a.atom_type == AtomType.SECTION_HEADER]
    if headers:
        header_texts = [a.content for a in headers[:15]]
        header_block = ", ".join(header_texts)
        if chars_used + len(header_block) <= char_budget:
            sections.append("DOCUMENT STRUCTURE: " + header_block)
            chars_used += len(header_block)

    # 4. High-importance paragraphs
    paragraphs = [a for a in atoms_to_use if a.atom_type == AtomType.PARAGRAPH]
    if paragraphs:
        para_lines = []
        for a in paragraphs[:10]:
            if chars_used >= char_budget:
                break
            text = a.content[:300]
            if len(a.content) > 300:
                text += "..."
            para_lines.append(text)
            chars_used += len(text)
        if para_lines:
            sections.append("CONTENT TO COVER:\n" + "\n\n".join(para_lines))

    # 5. Figure descriptions
    figures = [a for a in atoms_to_use if a.atom_type in (AtomType.FIGURE, AtomType.CHART, AtomType.DIAGRAM)]
    if figures:
        fig_lines = []
        for a in figures[:8]:
            if chars_used >= char_budget:
                break
            desc = a.caption or a.content or f"Figure {a.figure_number or '?'}"
            fig_lines.append(f"- {desc[:150]}")
            chars_used += len(desc[:150])
        if fig_lines:
            sections.append("FIGURES AVAILABLE:\n" + "\n".join(fig_lines))

    # 6. Entity list for context
    all_entities = set()
    for a in atoms_to_use:
        all_entities.update(a.entities[:3])
    if all_entities:
        entity_str = ", ".join(sorted(all_entities)[:20])
        sections.append(f"KEY ENTITIES: {entity_str}")

    # 7. Cross-source connections
    if kg.cross_links:
        link_descs = []
        for link in kg.cross_links[:5]:
            src_atom = kg.atoms.get(link.source_atom_id)
            tgt_atom = kg.atoms.get(link.target_atom_id)
            if src_atom and tgt_atom:
                link_descs.append(
                    f"- {link.relationship}: "
                    f"{src_atom.content[:60]} <-> {tgt_atom.content[:60]}"
                )
        if link_descs:
            sections.append("CROSS-SOURCE CONNECTIONS:\n" + "\n".join(link_descs))

    return "\n\n".join(sections)


@kb_cmd.command("produce")
@click.argument("project")
@click.option("--prompt", "-p", required=True, help="Production direction/focus")
@click.option("--sources", "-s", multiple=True, help="Limit to specific source IDs")
@click.option("--tier", type=click.Choice(["static", "text", "animated", "broll", "avatar", "full"]), default="static")
@click.option("--duration", "-d", type=float, default=60.0, help="Target duration in seconds")
@click.option("--budget", "-b", type=float, default=10.0, help="Budget in USD")
@click.option("--provider", type=click.Choice(["luma", "runway", "mock"]), default="luma", help="Video provider")
@click.option("--audio-tier", "audio_tier", type=click.Choice(["none", "music_only", "simple_overlay", "time_synced"]), default="simple_overlay")
@click.option("--live", is_flag=True, help="Use live providers (costs money)")
@click.option("--mock", "use_mock", is_flag=True, help="Force mock mode")
@click.option("--debug", is_flag=True, help="Enable debug output")
def produce_cmd_kb(project, prompt, sources, tier, duration, budget, provider, audio_tier, live, use_mock, debug):
    """Produce a video from knowledge base content.

    \b
    Examples:
      claude-studio kb produce "AI Research" -p "Explain the key findings" --mock
      claude-studio kb produce myproject -p "Compare the two papers" --tier animated --live
    """
    import time
    from core.models.audio import AudioTier
    from core.models.knowledge import KnowledgeGraph
    from cli.produce import _run_production

    # Resolve project
    project_dir = _resolve_project(project)
    if not project_dir:
        console.print(f"[red]Project not found:[/red] {project}")
        return

    proj = _load_project(project_dir)
    if not proj.sources:
        console.print(f"[red]No sources in project.[/red] Add sources first with: claude-studio kb add {project} --paper <file.pdf>")
        return

    # Load knowledge graph
    kg_path = project_dir / "knowledge_graph.json"
    if not kg_path.exists():
        console.print("[red]No knowledge graph found.[/red] Add sources to build the graph.")
        return

    with open(kg_path, encoding="utf-8") as f:
        kg_data = json.load(f)
    kg = KnowledgeGraph.from_dict(kg_data)

    # Filter sources if specified
    source_filter = list(sources) if sources else None
    if source_filter:
        invalid = [s for s in source_filter if s not in proj.sources]
        if invalid:
            console.print(f"[red]Unknown source IDs:[/red] {', '.join(invalid)}")
            console.print("[dim]Available sources:[/dim]")
            for sid, src in proj.sources.items():
                console.print(f"  {sid}: {src.title}")
            return

    # Build concept from KB
    concept = _build_concept_from_kb(proj, kg, prompt, source_filter)

    if debug:
        console.print(Panel(concept, title="Generated Concept", border_style="dim"))

    # Setup run
    use_live_mode = live and not use_mock
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path("artifacts/runs") / run_id

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "scenes").mkdir(exist_ok=True)
    (run_dir / "videos").mkdir(exist_ok=True)
    (run_dir / "audio").mkdir(exist_ok=True)
    (run_dir / "edl").mkdir(exist_ok=True)
    (run_dir / "renders").mkdir(exist_ok=True)

    # Parse audio tier
    audio_tier_map = {
        "none": AudioTier.NONE,
        "music_only": AudioTier.MUSIC_ONLY,
        "simple_overlay": AudioTier.SIMPLE_OVERLAY,
        "time_synced": AudioTier.TIME_SYNCED,
    }
    audio_tier_enum = audio_tier_map[audio_tier]

    # Show production header
    source_count = len(source_filter) if source_filter else proj.source_count
    console.print(Panel(
        f"[bold]KB Production[/bold]\n"
        f"Project: {proj.name} ({source_count} sources, {kg.atom_count} atoms)\n"
        f"Prompt: {prompt}\n"
        f"Tier: {tier} | Duration: {duration}s | Provider: {provider}\n"
        f"Mode: {'LIVE' if use_live_mode else 'MOCK'}",
        border_style="green" if use_live_mode else "blue",
    ))

    # Run production pipeline
    start_time = time.time()

    try:
        result = asyncio.run(_run_production(
            concept=concept,
            budget=budget,
            duration=duration,
            audio_tier=audio_tier_enum,
            provider_name=provider,
            use_live=use_live_mode,
            variations=1,
            run_dir=run_dir,
            run_id=run_id,
            debug=debug,
            as_json=False,
        ))

        total_time = time.time() - start_time

        if result.get("success"):
            console.print(f"\n[green]Production complete![/green] Run: {run_id}")
            console.print(f"  Output: {run_dir}")
            console.print(f"  Time: {total_time:.1f}s")
        else:
            console.print(f"\n[red]Production failed.[/red]")
            if debug and result.get("metadata"):
                console.print(f"[dim]{json.dumps(result['metadata'], indent=2)}[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Production cancelled.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Production error:[/red] {e}")
        if debug:
            import traceback
            traceback.print_exc()
