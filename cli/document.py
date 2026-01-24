"""Document ingestion CLI - Ingest documents for video production"""

import sys
import json
import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import box

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

console = Console()

PROJECTS_DIR = Path("artifacts") / "projects"


@click.group()
def document_cmd():
    """Document ingestion and management

    \b
    Ingest documents (PDFs) into knowledge graphs for video production.

    \b
    Examples:
      claude-studio document ingest paper.pdf
      claude-studio document ingest paper.pdf --mock
      claude-studio document show <project_id>
      claude-studio document list
    """
    pass


@document_cmd.command("ingest")
@click.argument("source", type=click.Path(exists=True))
@click.option("--mock", is_flag=True, help="Use mock analysis (no LLM calls)")
@click.option("--project-name", "-n", help="Project name (defaults to filename)")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory (default: artifacts/projects/)")
def ingest_cmd(source: str, mock: bool, project_name: str, output_dir: str):
    """Ingest a document and extract knowledge atoms.

    Extracts text, figures, and structure from a PDF using PyMuPDF,
    then uses LLM to classify atoms and generate summaries.
    """
    source_path = Path(source).resolve()

    if source_path.suffix.lower() != ".pdf":
        console.print(f"[red]Unsupported format:[/red] {source_path.suffix}")
        console.print("[dim]Currently only PDF files are supported.[/dim]")
        return

    if not project_name:
        project_name = source_path.stem

    console.print(Panel.fit(
        f"[bold]Document Ingestion[/bold]\n"
        f"[dim]Source: {source_path.name}[/dim]\n"
        f"[dim]Mode: {'mock' if mock else 'live (LLM)'}[/dim]",
        border_style="blue"
    ))

    # Run the async ingestion
    asyncio.run(_run_ingest(source_path, project_name, mock, output_dir))


async def _run_ingest(source_path: Path, project_name: str, mock: bool, output_dir: str):
    """Run document ingestion asynchronously"""
    from core.claude_client import ClaudeClient
    from agents.document_ingestor import DocumentIngestorAgent

    console.print("\n[cyan]Phase 1:[/cyan] Extracting content with PyMuPDF...")

    client = ClaudeClient() if not mock else None
    agent = DocumentIngestorAgent(claude_client=client, mock_mode=mock)

    try:
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

    # Print results
    console.print(f"[green]Extraction complete![/green]\n")

    _print_graph_summary(graph)

    # Save project
    out_dir = Path(output_dir) if output_dir else PROJECTS_DIR
    project_dir = out_dir / graph.document_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Save graph as JSON
    graph_path = project_dir / "document_graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph.to_dict(), f, indent=2, ensure_ascii=False)

    # Save figures separately
    figures_dir = project_dir / "figures"
    figure_count = 0
    for atom_id in graph.figures:
        atom = graph.get_atom(atom_id)
        if atom and atom.raw_data:
            figures_dir.mkdir(exist_ok=True)
            ext = "png"  # Default extension
            fig_path = figures_dir / f"{atom_id}.{ext}"
            with open(fig_path, "wb") as f:
                f.write(atom.raw_data)
            figure_count += 1

    # Save metadata
    meta_path = project_dir / "project.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "project_name": project_name,
            "document_id": graph.document_id,
            "source_path": str(source_path),
            "title": graph.title,
            "authors": graph.authors,
            "page_count": graph.page_count,
            "atom_count": graph.atom_count,
            "figure_count": figure_count,
            "mock_mode": mock,
        }, f, indent=2)

    console.print(f"\n[green]Project saved:[/green] {project_dir}")
    console.print(f"  Graph: {graph_path.name}")
    if figure_count:
        console.print(f"  Figures: {figure_count} saved to figures/")


def _print_graph_summary(graph):
    """Print a summary of the extracted document graph"""
    from core.models.document import AtomType

    # Title and metadata
    if graph.title:
        console.print(f"[bold]{graph.title}[/bold]")
    if graph.authors:
        console.print(f"[dim]Authors: {', '.join(graph.authors)}[/dim]")
    console.print(f"[dim]Pages: {graph.page_count} | Atoms: {graph.atom_count}[/dim]")
    console.print()

    # Atom type breakdown
    table = Table(box=box.SIMPLE, title="Atom Breakdown")
    table.add_column("Type", style="cyan", width=16)
    table.add_column("Count", justify="right", width=6)
    table.add_column("Sample", width=50)

    type_counts: dict = {}
    type_samples: dict = {}
    for atom in graph.atoms.values():
        t = atom.atom_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
        if t not in type_samples:
            type_samples[t] = atom.content[:50].replace("\n", " ")

    for atom_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        sample = type_samples.get(atom_type, "")
        table.add_row(atom_type, str(count), f"[dim]{sample}...[/dim]" if sample else "")

    console.print(table)

    # Hierarchy tree (first few sections)
    if graph.hierarchy:
        console.print()
        tree = Tree("[bold]Document Structure[/bold]")
        sections_shown = 0
        for section_id, children in graph.hierarchy.items():
            if sections_shown >= 5:
                tree.add(f"[dim]... and {len(graph.hierarchy) - 5} more sections[/dim]")
                break
            section_atom = graph.get_atom(section_id)
            if section_atom:
                label = section_atom.content[:60].replace("\n", " ")
                branch = tree.add(f"[cyan]{label}[/cyan]")
                for child_id in children[:3]:
                    child = graph.get_atom(child_id)
                    if child:
                        child_text = child.content[:40].replace("\n", " ")
                        branch.add(f"[dim]{child_text}...[/dim]")
                if len(children) > 3:
                    branch.add(f"[dim]... +{len(children) - 3} more[/dim]")
                sections_shown += 1
        console.print(tree)

    # Summaries
    if graph.one_sentence:
        console.print()
        console.print(Panel(
            graph.one_sentence,
            title="Summary",
            border_style="green",
            width=70
        ))


@document_cmd.command("show")
@click.argument("project_id")
@click.option("--atoms", "-a", is_flag=True, help="Show all atoms")
@click.option("--figures", "-f", is_flag=True, help="Show figures only")
def show_cmd(project_id: str, atoms: bool, figures: bool):
    """Show details of an ingested document project."""
    project_dir = PROJECTS_DIR / project_id

    if not project_dir.exists():
        console.print(f"[red]Project not found:[/red] {project_id}")
        console.print(f"[dim]Looked in: {project_dir}[/dim]")
        return

    graph_path = project_dir / "document_graph.json"
    if not graph_path.exists():
        console.print(f"[red]No document graph found in project {project_id}[/red]")
        return

    with open(graph_path, encoding="utf-8") as f:
        data = json.load(f)

    # Reconstruct minimal info for display
    console.print(Panel.fit(
        f"[bold]{data.get('title', 'Untitled')}[/bold]\n"
        f"[dim]ID: {data['document_id']}[/dim]\n"
        f"[dim]Source: {Path(data['source_path']).name}[/dim]\n"
        f"[dim]Pages: {data.get('page_count', '?')} | Atoms: {len(data.get('atoms', {}))}[/dim]",
        border_style="blue"
    ))

    if data.get("one_sentence"):
        console.print(f"\n[green]Summary:[/green] {data['one_sentence']}")

    if atoms:
        console.print()
        table = Table(box=box.ROUNDED, title="All Atoms")
        table.add_column("ID", style="dim", width=20)
        table.add_column("Type", style="cyan", width=14)
        table.add_column("Page", justify="right", width=5)
        table.add_column("Content", width=50)
        table.add_column("Score", justify="right", width=5)

        for atom_id, atom_data in data.get("atoms", {}).items():
            content = atom_data.get("content", "")[:50].replace("\n", " ")
            table.add_row(
                atom_id[-10:],
                atom_data.get("atom_type", "?"),
                str(atom_data.get("source_page", "?")),
                content,
                f"{atom_data.get('importance_score', 0):.1f}",
            )
        console.print(table)

    if figures:
        console.print()
        fig_atoms = {k: v for k, v in data.get("atoms", {}).items()
                     if v.get("atom_type") in ("figure", "chart", "diagram")}
        if fig_atoms:
            for atom_id, atom_data in fig_atoms.items():
                console.print(f"[cyan]{atom_id}[/cyan] (page {atom_data.get('source_page', '?')})")
                if atom_data.get("caption"):
                    console.print(f"  Caption: {atom_data['caption']}")
                if atom_data.get("data_summary"):
                    console.print(f"  Summary: {atom_data['data_summary']}")
                console.print()
        else:
            console.print("[yellow]No figures found in this document.[/yellow]")


@document_cmd.command("list")
def list_cmd():
    """List all ingested document projects."""
    if not PROJECTS_DIR.exists():
        console.print("[yellow]No projects found.[/yellow]")
        console.print(f"[dim]Run 'claude-studio document ingest <file.pdf>' to create one.[/dim]")
        return

    table = Table(box=box.ROUNDED, title="Document Projects")
    table.add_column("Project ID", style="cyan", width=16)
    table.add_column("Title", width=40)
    table.add_column("Pages", justify="right", width=6)
    table.add_column("Atoms", justify="right", width=6)

    projects = sorted(PROJECTS_DIR.iterdir())
    if not projects:
        console.print("[yellow]No projects found.[/yellow]")
        return

    for proj_dir in projects:
        if not proj_dir.is_dir():
            continue
        meta_path = proj_dir / "project.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            table.add_row(
                meta.get("document_id", proj_dir.name)[-16:],
                meta.get("title", "Untitled")[:40],
                str(meta.get("page_count", "?")),
                str(meta.get("atom_count", "?")),
            )
        else:
            table.add_row(proj_dir.name[:16], "[dim]No metadata[/dim]", "?", "?")

    console.print(table)
