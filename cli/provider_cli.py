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
@click.option("--resume", "-r", is_flag=True, help="Resume from saved session")
@click.option("--auto", "-a", is_flag=True, help="Fully automatic mode: no prompts, run all tests")
def onboard(name: str, provider_type: str, docs_url: tuple, stub: str, output: str, interactive: bool, skip_tests: bool, resume: bool, auto: bool):
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
    
    async def run():
        from agents.provider_onboarding import (
            ProviderOnboardingAgent,
            ProviderType,
        )
        from core.claude_client import ClaudeClient
        from core.memory.manager import MemoryManager

        claude = ClaudeClient()
        memory = MemoryManager()
        agent = ProviderOnboardingAgent(claude, memory_manager=memory)

        # Auto mode disables all interactive prompts
        is_interactive = interactive and not auto

        # Check for existing session to resume
        should_resume = resume
        if not resume and ProviderOnboardingAgent.has_session(name) and is_interactive:
            # Ask if they want to resume
            console.print(f"[yellow]Found existing session for {name}[/yellow]")
            should_resume = Confirm.ask("Resume from previous session?", default=True)

        if should_resume and ProviderOnboardingAgent.has_session(name):
            console.print(Panel.fit(
                f"[bold]Resuming Provider Onboarding[/bold]\n\n"
                f"Name: [cyan]{name}[/cyan]",
                title="📂 Resume Session"
            ))
            session = await agent.resume_session(name)

            # Show current state
            console.print(f"\n[dim]Current step: {session.current_step}[/dim]")
            if session.spec:
                console.print(f"[dim]Spec loaded: {session.spec.name}[/dim]")
            if session.implementation_path:
                console.print(f"[dim]Implementation: {session.implementation_path}[/dim]")
            if session.answers:
                console.print(f"[dim]Questions answered: {len(session.answers)}[/dim]")
        else:
            console.print(Panel.fit(
                f"[bold]Provider Onboarding[/bold]\n\n"
                f"Name: [cyan]{name}[/cyan]\n"
                f"Type: [yellow]{provider_type}[/yellow]\n"
                f"Docs: {len(docs_url)} URL(s)\n"
                f"Stub: {stub or 'None'}",
                title="🚀 Starting Onboarding"
            ))

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

        # Determine which steps to skip based on current_step
        completed_steps = []
        step_order = ["init", "docs", "spec", "questions", "implementation", "implementation_failed", "testing", "complete"]
        current_step = session.current_step

        # implementation_failed means questions are done but implementation needs retry
        if current_step == "implementation_failed":
            completed_steps = ["init", "docs", "spec", "questions"]
        elif current_step in step_order:
            current_idx = step_order.index(current_step)
            completed_steps = [s for s in step_order[:current_idx + 1] if s != "implementation_failed"]

        if completed_steps:
            console.print(f"[dim]Completed steps: {', '.join(completed_steps)}[/dim]\n")

        # Handle clarifying questions (skip if already done)
        if "questions" not in completed_steps and session.questions and is_interactive:
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
        elif "questions" in completed_steps and session.questions:
            console.print(f"[dim]Skipping questions (already answered {len(session.answers)})[/dim]")
        elif "questions" not in completed_steps and session.questions and not is_interactive:
            # In auto mode, use default values for questions
            console.print("[dim]Using default values for questions (auto mode)[/dim]")
            for q in session.questions:
                default = q.get("default_value", "")
                await agent.answer_question(q["id"], default)

        # Show spec details
        if session.spec:
            _show_spec_details(session.spec)

        # Generate implementation (skip if already done successfully)
        if "implementation" in completed_steps and session.implementation_path:
            console.print(f"[dim]Skipping implementation (already at {session.implementation_path})[/dim]")
            generate = False
        elif is_interactive:
            generate = Confirm.ask("\n[cyan]Generate implementation?[/cyan]")
        else:
            generate = True

        if generate:
            output_path = output or f"core/providers/{provider_type}/{name.lower()}.py"

            # Warn if output would overwrite the stub
            if stub and output_path == stub:
                console.print(f"\n[yellow]⚠ Output path is same as stub file: {stub}[/yellow]")
                if is_interactive:
                    overwrite = Confirm.ask("Overwrite stub with generated code?", default=False)
                    if not overwrite:
                        output_path = output_path.replace(".py", "_generated.py")
                        console.print(f"[dim]Using alternate path: {output_path}[/dim]")
                else:
                    # In batch/auto mode, don't overwrite - use alternate path
                    output_path = output_path.replace(".py", "_generated.py")
                    console.print(f"[dim]Using alternate path: {output_path}[/dim]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating implementation...", total=None)
                implementation = await agent.generate_implementation(output_path)

            console.print(f"\n[green]✓ Implementation saved to {output_path}[/green]")

            # Preview
            if is_interactive and Confirm.ask("Preview implementation?"):
                console.print(Syntax(implementation[:2000], "python", theme="monokai"))
                if len(implementation) > 2000:
                    console.print("[dim]... (truncated)[/dim]")
        
        # Generate tests
        if not skip_tests and session.implementation_path:
            if is_interactive:
                run_tests = Confirm.ask("\n[cyan]Generate and run tests?[/cyan]")
            else:
                run_tests = True

            if run_tests:
                results = await agent.run_tests(interactive=is_interactive)
                _show_test_results(results)
        elif not skip_tests and not session.implementation_path:
            console.print("[yellow]⚠ Skipping tests - no valid implementation path[/yellow]")

        # Record learnings
        if is_interactive:
            record = Confirm.ask("\n[cyan]Record learnings to memory?[/cyan]")
        else:
            record = True
        
        if record:
            try:
                await agent.record_learnings()
                console.print("[green]✓ Learnings recorded to memory[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ Could not record learnings: {e}[/yellow]")
        
        # Export tests to pytest file
        if session.test_results:
            if is_interactive:
                export_tests = Confirm.ask("\n[cyan]Export tests to pytest file?[/cyan]")
            else:
                export_tests = True

            if export_tests:
                try:
                    test_file = await agent.export_tests_to_pytest()
                    if test_file:
                        console.print(f"[green]✓ Tests exported to {test_file}[/green]")
                except Exception as e:
                    console.print(f"[yellow]⚠ Could not export tests: {e}[/yellow]")

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
@click.option("--prompt", "-p", default="Hello, this is a test of text to speech.", help="Test prompt/text")
@click.option("--voice", "-v", help="Voice ID to use (for audio providers)")
@click.option("--list-voices", is_flag=True, help="List available voices (for audio providers)")
@click.option("--live", is_flag=True, help="Use live API (costs money)")
def test_provider(provider_name: str, provider_type: str, prompt: str, voice: str, list_voices: bool, live: bool):
    """
    Test a provider with a simple generation.

    Examples:
        claude-studio provider test elevenlabs -t audio --live
        claude-studio provider test elevenlabs -t audio --list-voices
        claude-studio provider test elevenlabs -t audio -v 21m00Tcm4TlvDq8ikWAM -p "Hello world" --live
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

            # Find provider class - search for any class ending in "Provider"
            provider_class = None
            class_name = None
            for name in dir(module):
                if name.endswith("Provider") and name != "AudioProvider" and name != "VideoProvider":
                    obj = getattr(module, name)
                    if isinstance(obj, type):
                        provider_class = obj
                        class_name = name
                        break

            if not provider_class:
                # Fallback to convention
                class_name = f"{provider_name.capitalize()}Provider"
                provider_class = getattr(module, class_name)

            provider_instance = provider_class()

            # Helper to resolve voice name to ID
            async def resolve_voice(voice_input: str) -> tuple[str, str]:
                """Resolve a voice name or ID to (voice_id, voice_name)"""
                if not hasattr(provider_instance, 'list_voices'):
                    return voice_input, voice_input

                voices = await provider_instance.list_voices()

                # First try exact ID match
                for v in voices:
                    vid = v.get("voice_id", v.get("id", ""))
                    if vid == voice_input:
                        return vid, v.get("name", vid)

                # Then try case-insensitive name match
                for v in voices:
                    vname = v.get("name", "")
                    if vname.lower() == voice_input.lower():
                        return v.get("voice_id", v.get("id", "")), vname

                # Then try partial name match
                for v in voices:
                    vname = v.get("name", "")
                    if voice_input.lower() in vname.lower():
                        return v.get("voice_id", v.get("id", "")), vname

                # Return as-is if no match found
                return voice_input, voice_input

            # Handle --list-voices for audio providers
            if list_voices and provider_type == "audio":
                console.print(f"\n[cyan]Fetching voices from {class_name}...[/cyan]\n")

                if hasattr(provider_instance, 'list_voices'):
                    voices = await provider_instance.list_voices()

                    if voices:
                        table = Table(title=f"Available Voices for {provider_name}", show_lines=True)
                        table.add_column("Name", style="green", no_wrap=True)
                        table.add_column("Category/Labels", max_width=40)
                        table.add_column("Description", max_width=50)

                        for v in voices:
                            name = v.get("name", v.get("voice_id", v.get("id", "")))
                            # Handle different voice metadata formats
                            labels = v.get("labels", {})
                            if isinstance(labels, dict):
                                category = ", ".join(f"{k}: {val}" for k, val in labels.items())
                            else:
                                category = str(labels) if labels else ""
                            description = v.get("description", "")[:100] if v.get("description") else ""

                            table.add_row(name, category, description)

                        console.print(table)
                        console.print(f"\n[dim]Use -v <name> to test with a specific voice (e.g., -v Rachel)[/dim]")
                    else:
                        console.print("[yellow]No voices returned from provider[/yellow]")
                else:
                    console.print(f"[yellow]{class_name} does not support list_voices()[/yellow]")
                return

            # Resolve voice name to ID if specified
            voice_id = None
            voice_name = None
            if voice and provider_type == "audio":
                voice_id, voice_name = await resolve_voice(voice)
                if voice_id != voice:
                    console.print(f"[dim]Resolved voice '{voice}' → '{voice_name}' ({voice_id})[/dim]")

            console.print(f"\n[cyan]Testing {class_name}...[/cyan]")
            console.print(f"Prompt/Text: {prompt}")
            if voice_name:
                console.print(f"Voice: {voice_name}")
            console.print()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating...", total=None)

                # Call appropriate method based on provider type
                if provider_type == "audio":
                    # Pass voice_id if specified
                    kwargs = {"text": prompt}
                    if voice_id:
                        kwargs["voice_id"] = voice_id

                    result = await provider_instance.generate_speech(**kwargs)
                    progress.update(task, description="Complete!")

                    # Save audio file
                    if result.success and result.audio_data:
                        output_file = f"test_{provider_name}.mp3"
                        with open(output_file, "wb") as f:
                            f.write(result.audio_data)
                        console.print(Panel.fit(
                            f"[green]✓ Generation successful![/green]\n\n"
                            f"Audio saved to: {output_file}\n"
                            f"Size: {len(result.audio_data)} bytes\n"
                            f"Format: {result.format}" +
                            (f"\nVoice: {voice_name}" if voice_name else ""),
                            title="Test Result"
                        ))
                    else:
                        console.print(f"[red]Generation failed: {result.error_message}[/red]")
                elif provider_type == "video":
                    result = await provider_instance.generate(
                        prompt=prompt,
                        duration=5.0,
                    )
                    progress.update(task, description="Complete!")
                    console.print(Panel.fit(
                        f"[green]✓ Generation successful![/green]\n\n"
                        f"Result: {result}",
                        title="Test Result"
                    ))
                else:
                    result = await provider_instance.generate(prompt=prompt)
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
# SESSIONS COMMAND
# =============================================================================

@provider.command("sessions")
@click.option("--delete", "-d", help="Delete a session by provider name")
def sessions(delete: str):
    """
    List or manage saved onboarding sessions.

    Sessions are saved automatically during onboarding and can be resumed.

    Examples:
        claude-studio provider sessions           # List all sessions
        claude-studio provider sessions -d luma   # Delete luma session
    """
    from agents.provider_onboarding import ProviderOnboardingAgent, OnboardingSession
    from pathlib import Path

    if delete:
        path = ProviderOnboardingAgent.get_session_path(delete)
        if path.exists():
            path.unlink()
            console.print(f"[green]✓ Deleted session for {delete}[/green]")
        else:
            console.print(f"[yellow]No session found for {delete}[/yellow]")
        return

    # List all sessions
    session_names = ProviderOnboardingAgent.list_sessions()

    if not session_names:
        console.print("[dim]No saved sessions found.[/dim]")
        console.print("\nStart onboarding with:")
        console.print("  [cyan]claude-studio provider onboard -n <name> -t <type> -d <docs_url>[/cyan]")
        return

    table = Table(title="📂 Saved Onboarding Sessions")
    table.add_column("Provider", style="cyan")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Implementation")
    table.add_column("Tests")

    for name in session_names:
        try:
            session = OnboardingSession.load(str(ProviderOnboardingAgent.get_session_path(name)))
            impl = "✓" if session.implementation_path else "-"
            tests = f"{len(session.test_results)} run" if session.test_results else "-"
            table.add_row(
                name,
                session.current_step,
                session.status,
                impl,
                tests,
            )
        except Exception as e:
            table.add_row(name, "[red]error[/red]", str(e)[:20], "-", "-")

    console.print(table)
    console.print("\nResume a session with:")
    console.print("  [cyan]claude-studio provider onboard -n <name> -t <type> --resume[/cyan]")


# =============================================================================
# EXPORT-TESTS COMMAND
# =============================================================================

@provider.command("export-tests")
@click.argument("provider_name")
@click.option("--output", "-o", help="Output directory for tests (default: tests/integration)")
@click.option("--regenerate", "-r", is_flag=True, help="Regenerate test cases before exporting")
def export_tests(provider_name: str, output: str, regenerate: bool):
    """
    Export generated tests from an onboarding session to a pytest file.

    This converts the tests generated during provider onboarding into a
    proper pytest test file that can be run with the test suite.

    Examples:
        claude-studio provider export-tests elevenlabs
        claude-studio provider export-tests inworld -o tests/unit
        claude-studio provider export-tests elevenlabs --regenerate
    """
    from agents.provider_onboarding import ProviderOnboardingAgent, OnboardingSession

    # Check for existing session
    if not ProviderOnboardingAgent.has_session(provider_name):
        console.print(f"[red]No onboarding session found for {provider_name}[/red]")
        console.print("\nAvailable sessions:")
        for name in ProviderOnboardingAgent.list_sessions():
            console.print(f"  - {name}")
        return

    async def run():
        from core.claude_client import ClaudeClient

        claude = ClaudeClient()
        agent = ProviderOnboardingAgent(claude)

        # Load the session
        await agent.resume_session(provider_name)

        # Check if we need to regenerate test cases
        needs_regenerate = regenerate
        if not needs_regenerate and agent.session.test_results:
            # Check if test_results have test_case data
            first_result = agent.session.test_results[0]
            if "test_case" not in first_result or not first_result.get("test_case", {}).get("inputs"):
                console.print("[yellow]Test results missing test case details. Regenerating...[/yellow]")
                needs_regenerate = True

        if needs_regenerate:
            if not agent.session.implementation_path:
                console.print(f"[red]No implementation path in session. Cannot regenerate tests.[/red]")
                return

            from pathlib import Path
            impl_content = Path(agent.session.implementation_path).read_text()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Regenerating test cases...", total=None)
                test_cases = await agent.tester.generate_test_cases(
                    agent.session.spec,
                    impl_content,
                )

            if test_cases:
                # Replace test_results with regenerated cases
                agent.session.test_results = [
                    {"name": tc.get("name"), "status": "pending", "test_case": tc}
                    for tc in test_cases
                ]
                console.print(f"[green]✓ Regenerated {len(test_cases)} test cases[/green]")
            else:
                console.print("[yellow]No test cases generated[/yellow]")
                return

        if not agent.session.test_results:
            console.print(f"[yellow]No test results found in session for {provider_name}[/yellow]")
            console.print("\nRun tests first with:")
            console.print(f"  [cyan]claude-studio provider onboard -n {provider_name} -t <type> --resume[/cyan]")
            return

        # Export tests
        test_file = await agent.export_tests_to_pytest(output_dir=output)

        if test_file:
            console.print(f"\n[green]✓ Tests exported to {test_file}[/green]")
            console.print(f"\nRun tests with:")
            console.print(f"  [cyan]pytest {test_file} -m live_api -v[/cyan]")
        else:
            console.print("[red]Failed to export tests[/red]")

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
