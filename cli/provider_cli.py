"""
Provider CLI Commands

Commands for managing providers:
- Onboard new providers from documentation
- Analyze existing stubs
- Test provider implementations
- List and manage provider learnings
"""

import asyncio
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from pathlib import Path
import json

console = Console()


@click.group()
def provider():
    """Provider management and onboarding commands"""
    pass


# =============================================================================
# ONBOARD COMMAND
# =============================================================================

@provider.command("onboard")
@click.option("--name", "-n", required=True, help="Provider name (e.g., 'inworld', 'luma')")
@click.option("--type", "-t", "provider_type",
              type=click.Choice(["video", "audio", "stt", "image"]),
              required=True, help="Provider type")
@click.option("--docs-url", "-d", multiple=True, help="Documentation URL(s) to analyze")
@click.option("--stub", "-s", type=click.Path(exists=True), help="Existing stub file to complete")
@click.option("--output", "-o", help="Output path for implementation")
@click.option("--interactive/--batch", default=True, help="Interactive mode with questions")
@click.option("--skip-tests", is_flag=True, help="Skip test generation")
def onboard(name: str, provider_type: str, docs_url: tuple, stub: str, output: str, interactive: bool, skip_tests: bool):
    """
    Onboard a new provider from documentation or stub.
    
    Examples:
    
        # From documentation
        claude-studio provider onboard -n inworld -t audio -d https://docs.inworld.ai/docs/tts/tts
        
        # From existing stub
        claude-studio provider onboard -n runway -t video -s core/providers/video/runway_stub.py
        
        # Both (docs + stub)
        claude-studio provider onboard -n luma -t video \\
            -d https://docs.lumalabs.ai/api \\
            -s core/providers/video/luma_stub.py
    """
    
    console.print(Panel.fit(
        f"[bold]Provider Onboarding[/bold]\n\n"
        f"Name: [cyan]{name}[/cyan]\n"
        f"Type: [yellow]{provider_type}[/yellow]\n"
        f"Docs: {len(docs_url)} URL(s)\n"
        f"Stub: {stub or 'None'}",
        title="🚀 Starting Onboarding"
    ))
    
    async def run():
        from agents.provider_onboarding import (
            ProviderOnboardingAgent,
            ProviderType,
        )
        from core.claude_client import ClaudeClient
        
        claude = ClaudeClient()
        agent = ProviderOnboardingAgent(claude)
        
        # Start onboarding
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing documentation...", total=None)
            
            session = await agent.start_onboarding(
                provider_name=name,
                provider_type=ProviderType(provider_type),
                docs_url=docs_url[0] if docs_url else None,
                stub_path=stub,
            )
            
            progress.update(task, description="Analysis complete")
        
        # Show initial summary
        console.print(Panel(agent.get_session_summary(), title="📊 Analysis Results"))
        
        # Handle clarifying questions
        if session.questions and interactive:
            console.print("\n[yellow]📝 Clarifying Questions[/yellow]\n")
            
            for q in session.questions:
                importance_color = {
                    "critical": "red",
                    "important": "yellow",
                    "nice_to_have": "dim",
                }.get(q.get("importance", ""), "white")
                
                console.print(f"[{importance_color}]{q['question']}[/{importance_color}]")
                console.print(f"[dim]Category: {q.get('category', 'unknown')}[/dim]")
                
                default = q.get("default_value", "")
                answer = Prompt.ask("Your answer", default=default)
                
                await agent.answer_question(q["id"], answer)
                console.print()
        
        # Show spec details
        if session.spec:
            _show_spec_details(session.spec)
        
        # Generate implementation
        if interactive:
            generate = Confirm.ask("\n[cyan]Generate implementation?[/cyan]")
        else:
            generate = True
        
        if generate:
            output_path = output or f"core/providers/{provider_type}/{name.lower()}.py"
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating implementation...", total=None)
                implementation = await agent.generate_implementation(output_path)
            
            console.print(f"\n[green]✓ Implementation saved to {output_path}[/green]")
            
            # Preview
            if interactive and Confirm.ask("Preview implementation?"):
                console.print(Syntax(implementation[:2000], "python", theme="monokai"))
                if len(implementation) > 2000:
                    console.print("[dim]... (truncated)[/dim]")
        
        # Generate tests
        if not skip_tests:
            if interactive:
                run_tests = Confirm.ask("\n[cyan]Generate and run tests?[/cyan]")
            else:
                run_tests = True
            
            if run_tests:
                results = await agent.run_tests(interactive=interactive)
                _show_test_results(results)
        
        # Record learnings
        if interactive:
            record = Confirm.ask("\n[cyan]Record learnings to memory?[/cyan]")
        else:
            record = True
        
        if record:
            try:
                await agent.record_learnings()
                console.print("[green]✓ Learnings recorded to memory[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ Could not record learnings: {e}[/yellow]")
        
        # Final summary
        console.print(Panel(agent.get_session_summary(), title="✅ Onboarding Complete"))
    
    asyncio.run(run())


def _show_spec_details(spec):
    """Show detailed spec information"""
    
    # Models table
    if spec.models:
        table = Table(title="📦 Available Models")
        table.add_column("Model ID", style="cyan")
        table.add_column("Description")
        table.add_column("Inputs")
        table.add_column("Outputs")
        
        for model in spec.models:
            table.add_row(
                model.model_id,
                model.description[:40] + "..." if len(model.description) > 40 else model.description,
                ", ".join(model.input_types),
                ", ".join(model.output_types),
            )
        
        console.print(table)
    
    # Endpoints table
    if spec.endpoints:
        table = Table(title="🔌 API Endpoints")
        table.add_column("Method", style="green")
        table.add_column("Path")
        table.add_column("Description")
        table.add_column("Async", style="yellow")
        
        for ep in spec.endpoints:
            table.add_row(
                ep.method,
                ep.path,
                ep.description[:40] + "..." if len(ep.description) > 40 else ep.description,
                "✓" if ep.is_async else "-",
            )
        
        console.print(table)
    
    # Tips and gotchas
    if spec.tips:
        console.print("\n[green]💡 Tips:[/green]")
        for tip in spec.tips:
            console.print(f"  • {tip}")
    
    if spec.gotchas:
        console.print("\n[yellow]⚠ Gotchas:[/yellow]")
        for gotcha in spec.gotchas:
            console.print(f"  • {gotcha}")


def _show_test_results(results):
    """Show test results"""
    
    table = Table(title="🧪 Test Results")
    table.add_column("Test", style="cyan")
    table.add_column("Status")
    table.add_column("Duration")
    table.add_column("Notes")
    
    for result in results:
        status_style = {
            "passed": "[green]PASS[/green]",
            "failed": "[red]FAIL[/red]",
            "skipped": "[dim]SKIP[/dim]",
            "recorded": "[yellow]RECORDED[/yellow]",
        }.get(result["status"], result["status"])
        
        table.add_row(
            result["name"],
            status_style,
            f"{result.get('duration_ms', 0)}ms",
            result.get("error", "")[:30] if result.get("error") else "-",
        )
    
    console.print(table)


# =============================================================================
# ANALYZE COMMAND
# =============================================================================

@provider.command("analyze")
@click.argument("path", type=click.Path(exists=True))
@click.option("--format", "-f", type=click.Choice(["rich", "json"]), default="rich")
def analyze(path: str, format: str):
    """
    Analyze an existing provider file (stub or implementation).
    
    Example:
        claude-studio provider analyze core/providers/video/luma.py
    """
    
    async def run():
        from agents.provider_onboarding import StubAnalyzer
        from core.claude_client import ClaudeClient
        
        claude = ClaudeClient()
        analyzer = StubAnalyzer(claude)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Analyzing...", total=None)
            result = await analyzer.analyze_stub(path)
        
        if format == "json":
            console.print_json(data=result)
        else:
            _show_analysis_results(result, path)
    
    asyncio.run(run())


def _show_analysis_results(analysis: dict, path: str):
    """Show analysis results in rich format"""
    
    console.print(Panel.fit(
        f"[bold]Provider Analysis[/bold]\n\n"
        f"File: [cyan]{path}[/cyan]\n"
        f"Provider: [yellow]{analysis.get('provider_name', 'Unknown')}[/yellow]\n"
        f"Type: {analysis.get('provider_type', 'Unknown')}\n"
        f"Base Class: {analysis.get('base_class', 'Unknown')}",
        title="📄 Stub Analysis"
    ))
    
    # Methods table
    methods = analysis.get("required_methods", [])
    if methods:
        table = Table(title="Methods")
        table.add_column("Method", style="cyan")
        table.add_column("Status")
        table.add_column("Signature")
        
        for method in methods:
            status_style = {
                "complete": "[green]✓ Complete[/green]",
                "partial": "[yellow]◐ Partial[/yellow]",
                "stub": "[red]○ Stub[/red]",
                "not_implemented": "[red]✗ Missing[/red]",
            }.get(method.get("current_status", ""), method.get("current_status", ""))
            
            table.add_row(
                method["name"],
                status_style,
                method.get("signature", "")[:50],
            )
        
        console.print(table)
    
    # Notes
    notes = analysis.get("notes", [])
    if notes:
        console.print("\n[dim]Notes:[/dim]")
        for note in notes:
            console.print(f"  • {note}")


# =============================================================================
# LIST COMMAND
# =============================================================================

@provider.command("list")
@click.option("--type", "-t", "provider_type",
              type=click.Choice(["video", "audio", "image", "music", "storage", "all"]),
              default="all", help="Filter by type")
def list_providers(provider_type: str):
    """List all available providers"""

    # Scan provider directories
    provider_dirs = {
        "video": Path("core/providers/video"),
        "audio": Path("core/providers/audio"),
        "image": Path("core/providers/image"),
        "music": Path("core/providers/music"),
        "storage": Path("core/providers/storage"),
    }
    
    table = Table(title="📦 Available Providers")
    table.add_column("Type", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("File")
    
    for ptype, pdir in provider_dirs.items():
        if provider_type != "all" and ptype != provider_type:
            continue
        
        if not pdir.exists():
            continue
        
        for py_file in pdir.glob("*.py"):
            if py_file.name.startswith("_") or py_file.name == "base.py":
                continue
            
            # Quick status check
            content = py_file.read_text()
            if "raise NotImplementedError" in content or "# TODO" in content:
                status = "[yellow]Stub[/yellow]"
            elif "async def generate" in content or "async def synthesize" in content:
                status = "[green]Ready[/green]"
            else:
                status = "[dim]Unknown[/dim]"
            
            table.add_row(
                ptype,
                py_file.stem,
                status,
                str(py_file),
            )
    
    console.print(table)


# =============================================================================
# TEST COMMAND
# =============================================================================

@provider.command("test")
@click.argument("provider_name")
@click.option("--type", "-t", "provider_type",
              type=click.Choice(["video", "audio", "image", "music", "storage"]),
              help="Provider type (auto-detected if not specified)")
@click.option("--prompt", "-p", default="Test generation", help="Test prompt")
@click.option("--live", is_flag=True, help="Use live API (costs money)")
def test_provider(provider_name: str, provider_type: str, prompt: str, live: bool):
    """
    Test a provider with a simple generation.

    Example:
        claude-studio provider test luma -t video -p "A sunset" --live
    """

    if not live:
        console.print("[yellow]⚠ Running in mock mode. Use --live for real API calls.[/yellow]")

    async def run():
        # Dynamic import based on type
        module_path = f"core.providers.{provider_type}.{provider_name}" if provider_type else None
        if not module_path:
            console.print("[red]Please specify --type[/red]")
            return
        
        try:
            import importlib
            module = importlib.import_module(module_path)
            
            # Find provider class (convention: CapitalizedProvider)
            class_name = f"{provider_name.capitalize()}Provider"
            provider_class = getattr(module, class_name)
            
            provider = provider_class()
            
            console.print(f"\n[cyan]Testing {class_name}...[/cyan]")
            console.print(f"Prompt: {prompt}")
            console.print()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating...", total=None)
                
                result = await provider.generate(
                    prompt=prompt,
                    duration=5.0 if provider_type == "video" else None,
                )
                
                progress.update(task, description="Complete!")
            
            console.print(Panel.fit(
                f"[green]✓ Generation successful![/green]\n\n"
                f"Result: {result}",
                title="Test Result"
            ))
            
        except ImportError as e:
            console.print(f"[red]Could not import provider: {e}[/red]")
        except Exception as e:
            console.print(f"[red]Test failed: {e}[/red]")
    
    asyncio.run(run())


# =============================================================================
# SCAFFOLD COMMAND
# =============================================================================

@provider.command("scaffold")
@click.option("--name", "-n", required=True, help="Provider name")
@click.option("--type", "-t", "provider_type",
              type=click.Choice(["video", "audio", "image", "music", "storage"]),
              required=True, help="Provider type")
@click.option("--output", "-o", help="Output path")
def scaffold(name: str, provider_type: str, output: str):
    """
    Create a new provider stub file.

    Example:
        claude-studio provider scaffold -n runway -t video
    """

    output_path = output or f"core/providers/{provider_type}/{name.lower()}.py"

    # Select template based on type
    templates = {
        "video": _VIDEO_PROVIDER_TEMPLATE,
        "audio": _AUDIO_PROVIDER_TEMPLATE,
        "image": _IMAGE_PROVIDER_TEMPLATE,
        "music": _MUSIC_PROVIDER_TEMPLATE,
        "storage": _STORAGE_PROVIDER_TEMPLATE,
    }
    
    template = templates.get(provider_type, _VIDEO_PROVIDER_TEMPLATE)
    
    # Fill in template
    content = template.format(
        provider_name=name.capitalize(),
        provider_name_lower=name.lower(),
        provider_name_upper=name.upper(),
    )
    
    # Write file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content)
    
    console.print(f"[green]✓ Created stub at {output_path}[/green]")
    console.print(f"\nNext steps:")
    console.print(f"  1. Add {name.upper()}_API_KEY to your .env file")
    console.print(f"  2. Run: claude-studio provider onboard -n {name} -t {provider_type} -s {output_path}")


# =============================================================================
# TEMPLATES
# =============================================================================

_VIDEO_PROVIDER_TEMPLATE = '''"""
{provider_name} Video Provider

Auto-generated stub. Complete the implementation using:
    claude-studio provider onboard -n {provider_name_lower} -t video -s <this_file>
"""

import os
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx

from .base import VideoProvider, GenerationResult


@dataclass
class {provider_name}Config:
    """Configuration for {provider_name} provider"""
    api_key: str
    base_url: str = "https://api.{provider_name_lower}.ai/v1"
    model: str = "default"
    timeout: int = 600


class {provider_name}Provider(VideoProvider):
    """
    {provider_name} video generation provider.
    
    Environment Variables:
        {provider_name_upper}_API_KEY: API key for authentication
    
    Usage:
        from core.providers.provider_config import VideoProviderConfig, ProviderType
        from core.providers.{provider_name_lower} import {provider_name}Provider
        
        config = VideoProviderConfig(provider_type=ProviderType.{provider_name_upper})
        provider = {provider_name}Provider(config)
        result = await provider.generate_video("A sunset over mountains", duration=5.0)
    """
    
    def __init__(self, config):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url="https://api.{provider_name_lower}.ai/v1",
            headers={{
                "Authorization": f"Bearer {{os.environ.get('{provider_name_upper}_API_KEY')}}",
                "Content-Type": "application/json",
            }},
            timeout=self.config.timeout,
        )
    
    async def generate_video(
        self,
        prompt: str,
        duration: float = 5.0,
        aspect_ratio: str = "16:9",
        **kwargs
    ) -> GenerationResult:
        """
        Generate a video from a text prompt.
        """
        # TODO: Implement video generation
        # 1. Submit generation request
        # 2. Poll for completion (if async)
        # 3. Return video URL and metadata
        
        raise NotImplementedError("Video generation not yet implemented")
    
    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """Check status of async video generation job."""
        # TODO: Implement status checking
        raise NotImplementedError()
    
    async def download_video(self, video_url: str, output_path: str) -> bool:
        """Download generated video to local filesystem."""
        # TODO: Implement video download
        raise NotImplementedError()
    
    async def close(self):
        """Clean up resources"""
        await self.client.aclose()
'''

_AUDIO_PROVIDER_TEMPLATE = '''"""
{provider_name} Audio Provider

Auto-generated stub. Complete the implementation using:
    claude-studio provider onboard -n {provider_name_lower} -t audio -s <this_file>
"""

import os
from dataclasses import dataclass
from typing import Optional, List

import httpx

from .base import AudioProvider, GeneratedAudio


@dataclass
class {provider_name}Config:
    """Configuration for {provider_name} audio provider"""
    api_key: str
    base_url: str = "https://api.{provider_name_lower}.ai/v1"
    timeout: int = 120


class {provider_name}Provider(AudioProvider):
    """
    {provider_name} audio generation provider.
    
    Environment Variables:
        {provider_name_upper}_API_KEY: API key for authentication
    """
    
    def __init__(self, config: Optional[{provider_name}Config] = None):
        self.config = config or {provider_name}Config(
            api_key=os.environ.get("{provider_name_upper}_API_KEY", "")
        )
        
        if not self.config.api_key:
            raise ValueError("{provider_name_upper}_API_KEY environment variable not set")
        
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={{
                "Authorization": f"Bearer {{self.config.api_key}}",
                "Content-Type": "application/json",
            }},
            timeout=self.config.timeout,
        )
    
    @property
    def name(self) -> str:
        return "{provider_name_lower}"
    
    async def generate(
        self,
        prompt: str,
        duration: float = 30.0,
        **kwargs
    ) -> GeneratedAudio:
        """Generate audio from a prompt"""
        # TODO: Implement audio generation
        raise NotImplementedError()
    
    async def close(self):
        await self.client.aclose()
'''

_IMAGE_PROVIDER_TEMPLATE = '''"""
{provider_name} Image Provider

Auto-generated stub. Complete the implementation using:
    claude-studio provider onboard -n {provider_name_lower} -t image -s <this_file>
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx

from ..base import ImageProvider, ImageProviderConfig, ImageGenerationResult


@dataclass
class {provider_name}Config:
    """Configuration for {provider_name} image provider"""
    api_key: str
    base_url: str = "https://api.{provider_name_lower}.ai/v1"
    timeout: int = 120


class {provider_name}Provider(ImageProvider):
    """
    {provider_name} image generation provider.

    Environment Variables:
        {provider_name_upper}_API_KEY: API key for authentication
    """

    _is_stub = True

    def __init__(self, config: Optional[ImageProviderConfig] = None):
        super().__init__(config or ImageProviderConfig(
            api_key=os.environ.get("{provider_name_upper}_API_KEY", "")
        ))

        if not self.config.api_key:
            raise ValueError("{provider_name_upper}_API_KEY environment variable not set")

        self.client = httpx.AsyncClient(
            base_url="https://api.{provider_name_lower}.ai/v1",
            headers={{
                "Authorization": f"Bearer {{self.config.api_key}}",
                "Content-Type": "application/json",
            }},
            timeout=self.config.timeout,
        )

    @property
    def name(self) -> str:
        return "{provider_name_lower}"

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        **kwargs
    ) -> ImageGenerationResult:
        """Generate an image from a prompt"""
        # TODO: Implement image generation
        raise NotImplementedError()

    def estimate_cost(self, size: str = "1024x1024", **kwargs) -> float:
        """Estimate cost for image generation"""
        # TODO: Update with actual pricing
        return 0.04  # Placeholder

    async def validate_credentials(self) -> bool:
        """Validate API credentials"""
        # TODO: Implement credential validation
        raise NotImplementedError()

    async def close(self):
        await self.client.aclose()
'''

_MUSIC_PROVIDER_TEMPLATE = '''"""
{provider_name} Music Provider

Auto-generated stub. Complete the implementation using:
    claude-studio provider onboard -n {provider_name_lower} -t music -s <this_file>
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx

from ..base import MusicProvider, MusicProviderConfig, MusicGenerationResult


@dataclass
class {provider_name}Config:
    """Configuration for {provider_name} music provider"""
    api_key: str
    base_url: str = "https://api.{provider_name_lower}.ai/v1"
    timeout: int = 300  # Music generation can be slow


class {provider_name}Provider(MusicProvider):
    """
    {provider_name} music generation provider.

    Environment Variables:
        {provider_name_upper}_API_KEY: API key for authentication
    """

    _is_stub = True

    def __init__(self, config: Optional[MusicProviderConfig] = None):
        super().__init__(config or MusicProviderConfig(
            api_key=os.environ.get("{provider_name_upper}_API_KEY", "")
        ))

        if not self.config.api_key:
            raise ValueError("{provider_name_upper}_API_KEY environment variable not set")

        self.client = httpx.AsyncClient(
            base_url="https://api.{provider_name_lower}.ai/v1",
            headers={{
                "Authorization": f"Bearer {{self.config.api_key}}",
                "Content-Type": "application/json",
            }},
            timeout=self.config.timeout,
        )

    @property
    def name(self) -> str:
        return "{provider_name_lower}"

    async def generate_music(
        self,
        prompt: str,
        duration: float = 30.0,
        **kwargs
    ) -> MusicGenerationResult:
        """Generate music from a prompt"""
        # TODO: Implement music generation
        raise NotImplementedError()

    def estimate_cost(self, duration: float = 30.0, **kwargs) -> float:
        """Estimate cost for music generation"""
        # TODO: Update with actual pricing
        return 0.10  # Placeholder

    async def validate_credentials(self) -> bool:
        """Validate API credentials"""
        # TODO: Implement credential validation
        raise NotImplementedError()

    async def close(self):
        await self.client.aclose()
'''

_STORAGE_PROVIDER_TEMPLATE = '''"""
{provider_name} Storage Provider

Auto-generated stub. Complete the implementation using:
    claude-studio provider onboard -n {provider_name_lower} -t storage -s <this_file>
"""

import os
from dataclasses import dataclass
from typing import Optional, BinaryIO
from pathlib import Path


@dataclass
class {provider_name}Config:
    """Configuration for {provider_name} storage provider"""
    api_key: str = ""
    base_path: str = ""
    bucket: str = ""


class {provider_name}Provider:
    """
    {provider_name} storage provider.

    Environment Variables:
        {provider_name_upper}_API_KEY: API key for authentication (if applicable)
    """

    _is_stub = True

    def __init__(self, config: Optional[{provider_name}Config] = None):
        self.config = config or {provider_name}Config()

    @property
    def name(self) -> str:
        return "{provider_name_lower}"

    async def upload(
        self,
        file_path: str,
        destination: str,
        **kwargs
    ) -> str:
        """Upload a file and return its URL/path"""
        # TODO: Implement file upload
        raise NotImplementedError()

    async def download(
        self,
        source: str,
        destination: str,
        **kwargs
    ) -> str:
        """Download a file and return local path"""
        # TODO: Implement file download
        raise NotImplementedError()

    async def delete(self, path: str, **kwargs) -> bool:
        """Delete a file"""
        # TODO: Implement file deletion
        raise NotImplementedError()

    async def list_files(self, prefix: str = "", **kwargs) -> list:
        """List files with optional prefix filter"""
        # TODO: Implement file listing
        raise NotImplementedError()

    async def close(self):
        pass
'''


# =============================================================================
# REGISTER
# =============================================================================

def register_provider_commands(cli):
    """Register provider commands with main CLI"""
    cli.add_command(provider)


if __name__ == "__main__":
    provider()
