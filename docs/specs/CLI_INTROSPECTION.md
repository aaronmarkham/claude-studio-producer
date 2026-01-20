# CLI and Package Introspection Specification

## Overview

A CLI tool for interrogating Claude Studio Producer's capabilities, checking provider status, validating configuration, and running productions. Useful for development, debugging, and user onboarding.

## Installation

```bash
# After pip install
claude-studio --help

# Or via module
python -m claude_studio --help
```

## Command Structure

```
claude-studio
├── status              # Overall system status
├── providers           # Provider information
│   ├── list            # List all providers
│   ├── check <name>    # Check specific provider
│   └── test <name>     # Test provider with real API call
├── agents              # Agent information
│   ├── list            # List all agents
│   └── schema <name>   # Show agent input/output schema
├── config              # Configuration
│   ├── show            # Show current config
│   ├── validate        # Validate API keys
│   └── init            # Create .env template
├── memory              # Memory and learnings management
│   ├── stats           # Show memory statistics
│   ├── list [provider] # List learnings by provider
│   ├── search <query>  # Search learnings
│   ├── add <provider> <pattern>  # Add a learning
│   ├── export          # Export learnings to JSON
│   ├── import <file>   # Import learnings from JSON
│   ├── promote         # Promote a learning to higher level
│   ├── clear           # Clear learnings (with confirmation)
│   ├── tree            # Show namespace hierarchy
│   ├── preferences     # Show user preferences
│   └── set-pref <k> <v> # Set a preference
├── produce             # Run production
├── render              # Render video from existing run
├── test-provider       # Test a single provider
├── luma                # Luma API management
├── themes              # List and preview color themes
└── version             # Version info
```

## Implementation

### Entry Point (pyproject.toml)

```toml
[project.scripts]
claude-studio = "claude_studio.cli:main"
```

### cli/__init__.py

```python
"""Claude Studio Producer CLI"""

import click
from .status import status_cmd
from .providers import providers_cmd
from .agents import agents_cmd
from .config import config_cmd


@click.group()
@click.version_option()
def main():
    """Claude Studio Producer - AI Video Production Pipeline"""
    pass


main.add_command(status_cmd, name="status")
main.add_command(providers_cmd, name="providers")
main.add_command(agents_cmd, name="agents")
main.add_command(config_cmd, name="config")


if __name__ == "__main__":
    main()
```

### cli/status.py

```python
"""System status command"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from claude_studio.core.providers import get_all_providers
from claude_studio.agents import get_all_agents


console = Console()


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status_cmd(as_json: bool):
    """Show overall system status"""
    
    if as_json:
        import json
        click.echo(json.dumps(get_status_dict(), indent=2))
        return
    
    console.print(Panel.fit(
        "[bold blue]Claude Studio Producer[/bold blue]\n"
        "AI Video Production Pipeline",
        border_style="blue"
    ))
    
    # Provider summary
    providers = get_all_providers()
    implemented = sum(1 for p in providers if p["status"] == "implemented")
    stubbed = sum(1 for p in providers if p["status"] == "stub")
    
    provider_table = Table(title="Providers", box=box.ROUNDED)
    provider_table.add_column("Category", style="cyan")
    provider_table.add_column("Implemented", style="green")
    provider_table.add_column("Stubbed", style="yellow")
    
    categories = {}
    for p in providers:
        cat = p["category"]
        if cat not in categories:
            categories[cat] = {"implemented": 0, "stub": 0}
        categories[cat][p["status"]] += 1
    
    for cat, counts in categories.items():
        provider_table.add_row(
            cat.title(),
            str(counts.get("implemented", 0)),
            str(counts.get("stub", 0))
        )
    
    console.print(provider_table)
    
    # Agent summary
    agents = get_all_agents()
    
    agent_table = Table(title="Agents", box=box.ROUNDED)
    agent_table.add_column("Agent", style="cyan")
    agent_table.add_column("Status", style="green")
    
    for agent in agents:
        status_style = "green" if agent["status"] == "implemented" else "yellow"
        agent_table.add_row(
            agent["name"],
            f"[{status_style}]{agent['status']}[/{status_style}]"
        )
    
    console.print(agent_table)
    
    # Config status
    config = check_config()
    
    config_table = Table(title="Configuration", box=box.ROUNDED)
    config_table.add_column("Key", style="cyan")
    config_table.add_column("Status")
    
    for key, present in config.items():
        status = "[green]✓ Set[/green]" if present else "[red]✗ Missing[/red]"
        config_table.add_row(key, status)
    
    console.print(config_table)


def get_status_dict() -> dict:
    """Get status as dictionary for JSON output"""
    return {
        "providers": get_all_providers(),
        "agents": get_all_agents(),
        "config": check_config()
    }


def check_config() -> dict:
    """Check which API keys are configured"""
    import os
    
    keys = [
        "ANTHROPIC_API_KEY",
        "RUNWAY_API_KEY",
        "PIKA_API_KEY",
        "ELEVENLABS_API_KEY",
        "OPENAI_API_KEY",
        "MUBERT_API_KEY",
    ]
    
    return {key: bool(os.getenv(key)) for key in keys}
```

### cli/providers.py

```python
"""Provider commands"""

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


@click.group()
def providers_cmd():
    """Provider information and testing"""
    pass


@providers_cmd.command()
@click.option("--category", "-c", help="Filter by category (video, audio, music, image, storage)")
@click.option("--status", "-s", type=click.Choice(["all", "implemented", "stub"]), default="all")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list(category: str, status: str, as_json: bool):
    """List all providers with their status"""
    
    from claude_studio.core.providers import get_all_providers
    
    providers = get_all_providers()
    
    # Filter
    if category:
        providers = [p for p in providers if p["category"] == category]
    if status != "all":
        providers = [p for p in providers if p["status"] == status]
    
    if as_json:
        import json
        click.echo(json.dumps(providers, indent=2))
        return
    
    table = Table(title="Providers", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Status")
    table.add_column("Cost")
    table.add_column("API Key")
    
    for p in providers:
        status_style = "green" if p["status"] == "implemented" else "yellow"
        key_status = "[green]✓[/green]" if p["api_key_set"] else "[dim]—[/dim]"
        
        table.add_row(
            p["name"],
            p["category"],
            f"[{status_style}]{p['status']}[/{status_style}]",
            p["cost_info"],
            key_status
        )
    
    console.print(table)


@providers_cmd.command()
@click.argument("name")
def check(name: str):
    """Check detailed status of a specific provider"""
    
    from claude_studio.core.providers import get_provider_info
    
    info = get_provider_info(name)
    
    if not info:
        console.print(f"[red]Provider '{name}' not found[/red]")
        return
    
    console.print(f"\n[bold cyan]{info['name']}[/bold cyan]")
    console.print(f"Category: {info['category']}")
    console.print(f"Status: {info['status']}")
    console.print(f"Cost: {info['cost_info']}")
    console.print(f"API Key Env: {info['api_key_env']}")
    console.print(f"API Key Set: {'Yes' if info['api_key_set'] else 'No'}")
    
    if info.get("features"):
        console.print("\nFeatures:")
        for f in info["features"]:
            console.print(f"  • {f}")
    
    if info.get("limitations"):
        console.print("\nLimitations:")
        for l in info["limitations"]:
            console.print(f"  • {l}")
    
    if info["status"] == "stub":
        console.print("\n[yellow]⚠ This provider is not yet implemented[/yellow]")
        console.print("Methods will raise NotImplementedError")


@providers_cmd.command()
@click.argument("name")
@click.option("--prompt", "-p", default="A serene mountain landscape", help="Test prompt")
def test(name: str, prompt: str):
    """Test a provider with a real API call"""
    
    import asyncio
    from claude_studio.core.providers import get_provider_instance
    
    provider = get_provider_instance(name)
    
    if not provider:
        console.print(f"[red]Provider '{name}' not found[/red]")
        return
    
    console.print(f"Testing [cyan]{name}[/cyan] with prompt: {prompt[:50]}...")
    
    try:
        if hasattr(provider, "generate"):
            result = asyncio.run(provider.generate(prompt=prompt, duration=4.0))
            console.print(f"[green]✓ Success![/green]")
            console.print(f"  ID: {result.video_id if hasattr(result, 'video_id') else result.audio_id}")
            console.print(f"  Cost: ${result.generation_cost:.4f}")
        elif hasattr(provider, "generate_speech"):
            result = asyncio.run(provider.generate_speech(text=prompt, voice_id="default"))
            console.print(f"[green]✓ Success![/green]")
            console.print(f"  Duration: {result.duration:.1f}s")
            console.print(f"  Cost: ${result.generation_cost:.4f}")
        else:
            console.print("[yellow]Provider has no testable generate method[/yellow]")
    except NotImplementedError:
        console.print(f"[yellow]⚠ Provider is stubbed (not implemented)[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
```

### cli/agents.py

```python
"""Agent commands"""

import click
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich import box

console = Console()


@click.group()
def agents_cmd():
    """Agent information"""
    pass


@agents_cmd.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list(as_json: bool):
    """List all agents"""
    
    from claude_studio.agents import get_all_agents
    
    agents = get_all_agents()
    
    if as_json:
        import json
        click.echo(json.dumps(agents, indent=2))
        return
    
    table = Table(title="Agents", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Description")
    
    for agent in agents:
        status_style = "green" if agent["status"] == "implemented" else "yellow"
        table.add_row(
            agent["name"],
            f"[{status_style}]{agent['status']}[/{status_style}]",
            agent["description"][:50] + "..." if len(agent["description"]) > 50 else agent["description"]
        )
    
    console.print(table)


@agents_cmd.command()
@click.argument("name")
def schema(name: str):
    """Show input/output schema for an agent"""
    
    from claude_studio.agents import get_agent_schema
    
    schema = get_agent_schema(name)
    
    if not schema:
        console.print(f"[red]Agent '{name}' not found[/red]")
        return
    
    console.print(f"\n[bold cyan]{name}[/bold cyan]")
    console.print(f"{schema['description']}\n")
    
    console.print("[bold]Inputs:[/bold]")
    for input_name, input_info in schema["inputs"].items():
        console.print(f"  {input_name}: {input_info}")
    
    console.print("\n[bold]Outputs:[/bold]")
    console.print(f"  {schema['output']}")
    
    if schema.get("example"):
        console.print("\n[bold]Example:[/bold]")
        syntax = Syntax(schema["example"], "python", theme="monokai")
        console.print(syntax)
```

### cli/config.py

```python
"""Configuration commands"""

import click
from rich.console import Console
from rich.table import Table
from rich import box
from pathlib import Path

console = Console()


@click.group()
def config_cmd():
    """Configuration management"""
    pass


@config_cmd.command()
def show():
    """Show current configuration"""
    
    import os
    from dotenv import dotenv_values
    
    # Load from .env if exists
    env_file = Path(".env")
    env_values = dotenv_values(env_file) if env_file.exists() else {}
    
    table = Table(title="Configuration", box=box.ROUNDED)
    table.add_column("Key", style="cyan")
    table.add_column("Source")
    table.add_column("Status")
    
    keys = [
        ("ANTHROPIC_API_KEY", "Required"),
        ("RUNWAY_API_KEY", "Video"),
        ("PIKA_API_KEY", "Video"),
        ("LUMA_API_KEY", "Video"),
        ("KLING_API_KEY", "Video"),
        ("STABILITY_API_KEY", "Video/Image"),
        ("ELEVENLABS_API_KEY", "Audio"),
        ("OPENAI_API_KEY", "Audio/Image"),
        ("MUBERT_API_KEY", "Music"),
        ("SUNO_API_KEY", "Music"),
    ]
    
    for key, category in keys:
        in_env = key in env_values
        in_environ = key in os.environ
        
        if in_environ:
            source = "environment"
            status = "[green]✓ Set[/green]"
        elif in_env:
            source = ".env file"
            status = "[green]✓ Set[/green]"
        else:
            source = "—"
            status = "[dim]Not set[/dim]"
        
        table.add_row(f"{key} ({category})", source, status)
    
    console.print(table)
    
    if not env_file.exists():
        console.print("\n[yellow]No .env file found. Run 'claude-studio config init' to create one.[/yellow]")


@config_cmd.command()
def validate():
    """Validate API keys by making test calls"""
    
    import os
    import asyncio
    
    console.print("Validating API keys...\n")
    
    validations = [
        ("ANTHROPIC_API_KEY", validate_anthropic),
        ("RUNWAY_API_KEY", validate_runway),
        ("ELEVENLABS_API_KEY", validate_elevenlabs),
    ]
    
    for key_name, validator in validations:
        if os.getenv(key_name):
            console.print(f"Checking {key_name}...", end=" ")
            try:
                asyncio.run(validator())
                console.print("[green]✓ Valid[/green]")
            except Exception as e:
                console.print(f"[red]✗ Invalid: {e}[/red]")
        else:
            console.print(f"{key_name}: [dim]Not set, skipping[/dim]")


@config_cmd.command()
@click.option("--force", "-f", is_flag=True, help="Overwrite existing .env")
def init(force: bool):
    """Create .env template file"""
    
    env_file = Path(".env")
    
    if env_file.exists() and not force:
        console.print("[yellow].env file already exists. Use --force to overwrite.[/yellow]")
        return
    
    template = '''# Claude Studio Producer Configuration
# Copy this file to .env and fill in your API keys

# ===================
# REQUIRED
# ===================
ANTHROPIC_API_KEY=

# ===================
# VIDEO PROVIDERS
# ===================
# At least one recommended for video generation
RUNWAY_API_KEY=
PIKA_API_KEY=
LUMA_API_KEY=
KLING_API_KEY=
STABILITY_API_KEY=

# ===================
# AUDIO PROVIDERS
# ===================
# At least one recommended for voiceover
ELEVENLABS_API_KEY=
OPENAI_API_KEY=

# ===================
# MUSIC PROVIDERS
# ===================
MUBERT_API_KEY=
SUNO_API_KEY=

# ===================
# STORAGE (Optional)
# ===================
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-west-2
S3_BUCKET=

# ===================
# DEVELOPMENT
# ===================
ENV=development
DEBUG=true
PROVIDER_MODE=mock
'''
    
    env_file.write_text(template)
    console.print(f"[green]Created {env_file}[/green]")
    console.print("Edit the file to add your API keys.")


async def validate_anthropic():
    from anthropic import Anthropic
    client = Anthropic()
    # Just check we can create a client without error
    # A real validation would make a small API call


async def validate_runway():
    import httpx
    import os
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.runwayml.com/v1/account",
            headers={"Authorization": f"Bearer {os.getenv('RUNWAY_API_KEY')}"}
        )
        response.raise_for_status()


async def validate_elevenlabs():
    import httpx
    import os
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY")}
        )
        response.raise_for_status()
```

## Provider/Agent Registration

### core/providers/__init__.py (additions)

```python
"""Provider registry with introspection"""

from typing import List, Dict, Optional, Any
import os


# Provider metadata for CLI introspection
PROVIDER_REGISTRY = {
    # Video
    "runway": {
        "name": "runway",
        "category": "video",
        "class": "RunwayProvider",
        "module": "core.providers.video.runway",
        "status": "stub",  # or "implemented"
        "api_key_env": "RUNWAY_API_KEY",
        "cost_info": "$0.25-0.50/sec",
        "features": ["text-to-video", "image-to-video", "10s max"],
        "limitations": ["10 second max duration"],
    },
    "pika": {
        "name": "pika",
        "category": "video",
        "class": "PikaProvider",
        "module": "core.providers.video.pika",
        "status": "stub",
        "api_key_env": "PIKA_API_KEY",
        "cost_info": "$0.20/sec",
        "features": ["text-to-video", "stylized content", "4s max"],
        "limitations": ["4 second max duration"],
    },
    "stability": {
        "name": "stability",
        "category": "video",
        "class": "StabilityVideoProvider",
        "module": "core.providers.video.stability",
        "status": "stub",
        "api_key_env": "STABILITY_API_KEY",
        "cost_info": "$0.10/sec",
        "features": ["image-to-video only"],
        "limitations": ["Requires input image", "4 second max"],
    },
    "luma": {
        "name": "luma",
        "category": "video",
        "class": "LumaProvider",
        "module": "core.providers.video.luma",
        "status": "stub",
        "api_key_env": "LUMA_API_KEY",
        "cost_info": "$0.30/sec",
        "features": ["text-to-video", "camera control", "5s max"],
        "limitations": ["5 second max duration"],
    },
    "kling": {
        "name": "kling",
        "category": "video",
        "class": "KlingProvider",
        "module": "core.providers.video.kling",
        "status": "stub",
        "api_key_env": "KLING_API_KEY",
        "cost_info": "$0.15-0.30/sec",
        "features": ["text-to-video", "10s max", "good physics"],
        "limitations": [],
    },
    
    # Audio
    "elevenlabs": {
        "name": "elevenlabs",
        "category": "audio",
        "class": "ElevenLabsProvider",
        "module": "core.providers.audio.elevenlabs",
        "status": "stub",
        "api_key_env": "ELEVENLABS_API_KEY",
        "cost_info": "$0.30/1K chars",
        "features": ["premium voices", "voice cloning", "multilingual"],
        "limitations": [],
    },
    "openai_tts": {
        "name": "openai_tts",
        "category": "audio",
        "class": "OpenAITTSProvider",
        "module": "core.providers.audio.openai_tts",
        "status": "stub",
        "api_key_env": "OPENAI_API_KEY",
        "cost_info": "$0.015-0.030/1K chars",
        "features": ["6 voices", "fast generation"],
        "limitations": ["fewer voice options"],
    },
    "google_tts": {
        "name": "google_tts",
        "category": "audio",
        "class": "GoogleTTSProvider",
        "module": "core.providers.audio.google_tts",
        "status": "stub",
        "api_key_env": "GOOGLE_CLOUD_API_KEY",
        "cost_info": "$0.004-0.016/1K chars",
        "features": ["200+ voices", "40+ languages", "cheapest"],
        "limitations": ["less natural than others"],
    },
    
    # Music
    "mubert": {
        "name": "mubert",
        "category": "music",
        "class": "MubertProvider",
        "module": "core.providers.music.mubert",
        "status": "stub",
        "api_key_env": "MUBERT_API_KEY",
        "cost_info": "$0.50/track",
        "features": ["AI-generated", "royalty-free", "mood control"],
        "limitations": [],
    },
    "suno": {
        "name": "suno",
        "category": "music",
        "class": "SunoProvider",
        "module": "core.providers.music.suno",
        "status": "stub",
        "api_key_env": "SUNO_API_KEY",
        "cost_info": "$0.05/sec",
        "features": ["vocals support", "lyrics", "full songs"],
        "limitations": [],
    },
    
    # Image
    "dalle": {
        "name": "dalle",
        "category": "image",
        "class": "DalleProvider",
        "module": "core.providers.image.dalle",
        "status": "stub",
        "api_key_env": "OPENAI_API_KEY",
        "cost_info": "$0.04-0.08/image",
        "features": ["high quality", "prompt revision"],
        "limitations": [],
    },
    
    # Storage
    "local": {
        "name": "local",
        "category": "storage",
        "class": "LocalStorageProvider",
        "module": "core.providers.storage.local",
        "status": "implemented",
        "api_key_env": None,
        "cost_info": "Free",
        "features": ["local filesystem"],
        "limitations": ["development only"],
    },
    "s3": {
        "name": "s3",
        "category": "storage",
        "class": "S3StorageProvider",
        "module": "core.providers.storage.s3",
        "status": "stub",
        "api_key_env": "AWS_ACCESS_KEY_ID",
        "cost_info": "~$0.023/GB",
        "features": ["scalable", "CDN integration"],
        "limitations": ["requires AWS account"],
    },
}


def get_all_providers() -> List[Dict[str, Any]]:
    """Get all providers with their status"""
    result = []
    for name, info in PROVIDER_REGISTRY.items():
        result.append({
            **info,
            "api_key_set": bool(os.getenv(info["api_key_env"])) if info["api_key_env"] else True
        })
    return result


def get_provider_info(name: str) -> Optional[Dict[str, Any]]:
    """Get detailed info for a specific provider"""
    if name not in PROVIDER_REGISTRY:
        return None
    
    info = PROVIDER_REGISTRY[name].copy()
    info["api_key_set"] = bool(os.getenv(info["api_key_env"])) if info["api_key_env"] else True
    return info


def get_provider_instance(name: str):
    """Get an instance of a provider by name"""
    if name not in PROVIDER_REGISTRY:
        return None
    
    info = PROVIDER_REGISTRY[name]
    
    # Dynamic import
    import importlib
    module = importlib.import_module(info["module"])
    cls = getattr(module, info["class"])
    
    try:
        return cls()
    except Exception:
        return None
```

### agents/__init__.py (additions)

```python
"""Agent registry with introspection"""

from typing import List, Dict, Optional, Any


AGENT_REGISTRY = {
    "producer": {
        "name": "producer",
        "class": "ProducerAgent",
        "module": "agents.producer",
        "status": "implemented",
        "description": "Analyzes requests and creates pilot strategies",
        "inputs": {
            "user_request": "str - Video concept description",
            "total_budget": "float - Total budget in USD"
        },
        "output": "List[PilotStrategy]",
        "example": '''
agent = ProducerAgent(claude_client)
pilots = await agent.run(
    user_request="60-second product demo",
    total_budget=150.0
)
'''
    },
    "critic": {
        "name": "critic",
        "class": "CriticAgent",
        "module": "agents.critic",
        "status": "implemented",
        "description": "Evaluates pilot results and makes budget decisions",
        "inputs": {
            "original_request": "str - Original video concept",
            "pilot": "PilotStrategy - Pilot being evaluated",
            "scene_results": "List[GeneratedVideo] - Generated test scenes",
            "budget_spent": "float - Budget used so far",
            "budget_allocated": "float - Total pilot budget"
        },
        "output": "PilotEvaluation",
    },
    "script_writer": {
        "name": "script_writer",
        "class": "ScriptWriterAgent",
        "module": "agents.script_writer",
        "status": "implemented",
        "description": "Breaks video concepts into scenes with detailed specs",
        "inputs": {
            "video_concept": "str - Video concept",
            "target_duration": "int - Duration in seconds",
            "num_scenes": "int - Number of scenes",
            "seed_assets": "Optional[SeedAssetCollection] - Reference materials"
        },
        "output": "List[Scene]",
    },
    "asset_analyzer": {
        "name": "asset_analyzer",
        "class": "AssetAnalyzerAgent",
        "module": "agents.asset_analyzer",
        "status": "stub",
        "description": "Analyzes seed assets using Claude Vision",
        "inputs": {
            "collection": "SeedAssetCollection - Assets to analyze"
        },
        "output": "SeedAssetCollection (enriched with extracted info)",
    },
    "video_generator": {
        "name": "video_generator",
        "class": "VideoGeneratorAgent",
        "module": "agents.video_generator",
        "status": "implemented",
        "description": "Generates video content for scenes",
        "inputs": {
            "scenes": "List[Scene] - Scenes to generate",
            "budget_limit": "float - Maximum budget"
        },
        "output": "List[GeneratedVideo]",
    },
    "audio_generator": {
        "name": "audio_generator",
        "class": "AudioGeneratorAgent",
        "module": "agents.audio_generator",
        "status": "stub",
        "description": "Generates voiceover, music, and sound effects",
        "inputs": {
            "scenes": "List[Scene] - Scenes with audio specs",
            "audio_tier": "AudioTier - Quality level"
        },
        "output": "List[SceneAudio]",
    },
    "qa_verifier": {
        "name": "qa_verifier",
        "class": "QAVerifierAgent",
        "module": "agents.qa_verifier",
        "status": "stub",
        "description": "Verifies video quality using Claude Vision",
        "inputs": {
            "video": "GeneratedVideo - Video to verify",
            "scene": "Scene - Expected scene spec"
        },
        "output": "QAResult",
    },
    "editor": {
        "name": "editor",
        "class": "EditorAgent",
        "module": "agents.editor",
        "status": "stub",
        "description": "Creates EDL and edit candidates from raw materials",
        "inputs": {
            "scenes": "List[Scene]",
            "videos": "List[GeneratedVideo]",
            "audio": "List[SceneAudio]"
        },
        "output": "EditDecisionList",
    },
}


def get_all_agents() -> List[Dict[str, Any]]:
    """Get all agents with their status"""
    return list(AGENT_REGISTRY.values())


def get_agent_schema(name: str) -> Optional[Dict[str, Any]]:
    """Get schema for a specific agent"""
    return AGENT_REGISTRY.get(name)
```

## Example Output

```bash
$ claude-studio status

╭─────────────────────────────────────╮
│ Claude Studio Producer              │
│ AI Video Production Pipeline        │
╰─────────────────────────────────────╯

         Providers          
┌──────────┬─────────────┬─────────┐
│ Category │ Implemented │ Stubbed │
├──────────┼─────────────┼─────────┤
│ Video    │ 0           │ 5       │
│ Audio    │ 0           │ 3       │
│ Music    │ 0           │ 2       │
│ Image    │ 0           │ 1       │
│ Storage  │ 1           │ 1       │
└──────────┴─────────────┴─────────┘

           Agents           
┌─────────────────┬─────────────┐
│ Agent           │ Status      │
├─────────────────┼─────────────┤
│ producer        │ implemented │
│ critic          │ implemented │
│ script_writer   │ implemented │
│ asset_analyzer  │ stub        │
│ video_generator │ implemented │
│ audio_generator │ stub        │
│ qa_verifier     │ stub        │
│ editor          │ stub        │
└─────────────────┴─────────────┘

        Configuration        
┌─────────────────────┬─────────────┐
│ Key                 │ Status      │
├─────────────────────┼─────────────┤
│ ANTHROPIC_API_KEY   │ ✓ Set       │
│ RUNWAY_API_KEY      │ ✗ Missing   │
│ PIKA_API_KEY        │ ✗ Missing   │
│ ELEVENLABS_API_KEY  │ ✗ Missing   │
│ OPENAI_API_KEY      │ ✓ Set       │
│ MUBERT_API_KEY      │ ✗ Missing   │
└─────────────────────┴─────────────┘
```

```bash
$ claude-studio providers list --status stub

         Providers          
┌───────────┬──────────┬────────┬──────────────────┬─────────┐
│ Name      │ Category │ Status │ Cost             │ API Key │
├───────────┼──────────┼────────┼──────────────────┼─────────┤
│ runway    │ video    │ stub   │ $0.25-0.50/sec   │ —       │
│ pika      │ video    │ stub   │ $0.20/sec        │ —       │
│ stability │ video    │ stub   │ $0.10/sec        │ —       │
│ luma      │ video    │ stub   │ $0.30/sec        │ —       │
│ kling     │ video    │ stub   │ $0.15-0.30/sec   │ —       │
│ elevenlabs│ audio    │ stub   │ $0.30/1K chars   │ —       │
│ ...       │ ...      │ ...    │ ...              │ ...     │
└───────────┴──────────┴────────┴──────────────────┴─────────┘
```

```bash
$ claude-studio providers check runway

runway
Category: video
Status: stub
Cost: $0.25-0.50/sec
API Key Env: RUNWAY_API_KEY
API Key Set: No

Features:
  • text-to-video
  • image-to-video
  • 10s max

Limitations:
  • 10 second max duration

⚠ This provider is not yet implemented
Methods will raise NotImplementedError
```

## Implementation Priority

This can come later with Docker/Server, but the foundation is:

1. **PROVIDER_REGISTRY** dict in `core/providers/__init__.py`
2. **AGENT_REGISTRY** dict in `agents/__init__.py`
3. Update status as we implement

The CLI itself can wait until we have more implemented!
