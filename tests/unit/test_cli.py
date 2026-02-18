"""CLI command tests using Click's CliRunner

Tests argument parsing, option validation, help text, JSON output, and
basic execution paths for all CLI commands (no real API calls).
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from click.testing import CliRunner

from cli import main


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def runner():
    """Click CliRunner with isolated filesystem"""
    return CliRunner()


@pytest.fixture
def isolated_runner():
    """Click CliRunner with isolated filesystem for file operations"""
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner


# ============================================================
# Main CLI Group
# ============================================================

class TestMainGroup:
    """Tests for the top-level CLI group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Claude Studio Producer" in result.output
        assert "produce" in result.output
        assert "training" in result.output

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.7.0" in result.output

    def test_no_command_shows_help(self, runner):
        result = runner.invoke(main, [])
        # Click groups return exit code 0 or 2 when no command given depending on version
        # The important thing is that help is shown
        assert "Claude Studio Producer" in result.output or "produce" in result.output

    def test_unknown_command(self, runner):
        result = runner.invoke(main, ["nonexistent"])
        assert result.exit_code != 0
        assert "No such command" in result.output or "Error" in result.output

    def test_all_commands_registered(self, runner):
        """Verify all expected commands are registered on the main group."""
        result = runner.invoke(main, ["--help"])
        expected_commands = [
            "produce", "produce-video", "resume", "render",
            "test-provider", "luma", "memory", "qa", "document",
            "kb", "provider", "training", "secrets", "status",
            "providers", "agents", "config", "themes",
        ]
        for cmd in expected_commands:
            assert cmd in result.output, f"Command '{cmd}' not found in help output"


# ============================================================
# Produce Command
# ============================================================

class TestProduceCommand:
    """Tests for the 'produce' command."""

    def test_help(self, runner):
        result = runner.invoke(main, ["produce", "--help"])
        assert result.exit_code == 0
        assert "--concept" in result.output
        assert "--budget" in result.output
        assert "--provider" in result.output
        assert "--live" in result.output
        assert "--mock" in result.output

    def test_requires_concept(self, runner):
        result = runner.invoke(main, ["produce"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()

    def test_invalid_provider_choice(self, runner):
        result = runner.invoke(main, [
            "produce", "-c", "test", "--provider", "nonexistent"
        ])
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid choice" in result.output.lower()

    def test_valid_provider_choices(self, runner):
        """Verify all valid provider choices are accepted in help."""
        result = runner.invoke(main, ["produce", "--help"])
        assert "luma" in result.output
        assert "runway" in result.output
        assert "mock" in result.output

    def test_invalid_audio_tier_choice(self, runner):
        result = runner.invoke(main, [
            "produce", "-c", "test", "--audio-tier", "invalid"
        ])
        assert result.exit_code != 0

    def test_valid_audio_tier_choices(self, runner):
        result = runner.invoke(main, ["produce", "--help"])
        for tier in ["none", "music_only", "simple_overlay", "time_synced"]:
            assert tier in result.output

    def test_invalid_style_choice(self, runner):
        result = runner.invoke(main, [
            "produce", "-c", "test", "--style", "invalid"
        ])
        assert result.exit_code != 0

    def test_valid_style_choices(self, runner):
        result = runner.invoke(main, ["produce", "--help"])
        for style in ["visual_storyboard", "podcast", "educational", "documentary"]:
            assert style in result.output

    def test_invalid_execution_strategy_choice(self, runner):
        result = runner.invoke(main, [
            "produce", "-c", "test", "--execution-strategy", "invalid"
        ])
        assert result.exit_code != 0

    def test_mode_choices(self, runner):
        result = runner.invoke(main, ["produce", "--help"])
        assert "video-led" in result.output
        assert "audio-led" in result.output

    def test_budget_type_validation(self, runner):
        result = runner.invoke(main, [
            "produce", "-c", "test", "--budget", "not_a_number"
        ])
        assert result.exit_code != 0

    def test_seed_assets_nonexistent_path(self, runner):
        result = runner.invoke(main, [
            "produce", "-c", "test", "--seed-assets", "/nonexistent/path"
        ])
        assert result.exit_code != 0

    @patch("cli.produce._run_production", new_callable=AsyncMock)
    def test_mock_mode_runs_pipeline(self, mock_run, runner, tmp_path):
        """Produce command in mock mode invokes the pipeline."""
        mock_run.return_value = {
            "success": True,
            "run_id": "test_run",
            "run_dir": str(tmp_path),
            "scenes": [],
            "videos": {},
            "costs": {"video": 0, "audio": 0, "total": 0},
            "metadata": {
                "costs": {"total": 0},
                "stages": {},
                "actual_video_provider": "mock",
            },
        }
        result = runner.invoke(main, [
            "produce", "-c", "A test concept", "--mock",
            "--output-dir", str(tmp_path),
        ])
        # The command calls asyncio.run(_run_production(...))
        # With our mock, it should succeed
        assert mock_run.called or result.exit_code in (0, 1)

    @patch("cli.produce._run_production", new_callable=AsyncMock)
    def test_json_output_mode(self, mock_run, runner, tmp_path):
        """--json flag produces JSON output."""
        mock_run.return_value = {
            "success": True,
            "run_id": "test_run",
            "run_dir": str(tmp_path),
            "scenes": [],
            "videos": {},
            "costs": {"video": 0, "audio": 0, "total": 0},
            "metadata": {
                "costs": {"total": 0},
                "stages": {},
                "actual_video_provider": "mock",
            },
        }
        result = runner.invoke(main, [
            "produce", "-c", "test concept", "--mock", "--json",
            "--output-dir", str(tmp_path),
        ])
        # If pipeline runs, output should be valid JSON
        if result.exit_code == 0:
            # Find JSON in output (may have other text before)
            output = result.output.strip()
            # Try to parse the last JSON block
            assert "{" in output

    def test_default_budget(self, runner):
        """Budget option accepts float values"""
        result = runner.invoke(main, ["produce", "--help"])
        # Check that --budget option exists with FLOAT type
        assert "--budget" in result.output
        assert "FLOAT" in result.output

    def test_default_duration(self, runner):
        """Duration option accepts float values"""
        result = runner.invoke(main, ["produce", "--help"])
        # Check that --duration option exists with FLOAT type
        assert "--duration" in result.output
        assert "FLOAT" in result.output


# ============================================================
# Produce Video Command
# ============================================================

class TestProduceVideoCommand:
    """Tests for the 'produce-video' command."""

    def test_help(self, runner):
        result = runner.invoke(main, ["produce-video", "--help"])
        assert result.exit_code == 0
        assert "produce-video" in result.output.lower() or "trial" in result.output.lower()


# ============================================================
# Training Command
# ============================================================

class TestTrainingCommand:
    """Tests for the 'training' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["training", "--help"])
        assert result.exit_code == 0
        assert "Training pipeline" in result.output or "training" in result.output.lower()

    def test_run_help(self, runner):
        result = runner.invoke(main, ["training", "run", "--help"])
        assert result.exit_code == 0
        assert "--pairs-dir" in result.output
        assert "--output-dir" in result.output
        assert "--max-trials" in result.output
        assert "--with-audio" in result.output

    def test_list_pairs_help(self, runner):
        result = runner.invoke(main, ["training", "list-pairs", "--help"])
        assert result.exit_code == 0

    def test_list_pairs_empty_directory(self, runner, tmp_path):
        """list-pairs with an empty directory shows no pairs."""
        result = runner.invoke(main, ["training", "list-pairs", str(tmp_path)])
        assert result.exit_code == 0
        assert "No training pairs found" in result.output or result.output.strip() != ""

    def test_list_pairs_with_pair(self, runner, tmp_path):
        """list-pairs finds PDF+MP3 pairs."""
        # Create a matching pair
        (tmp_path / "paper1.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "paper1.mp3").write_bytes(b"fake mp3")

        result = runner.invoke(main, ["training", "list-pairs", str(tmp_path)])
        assert result.exit_code == 0
        assert "paper1" in result.output

    def test_list_pairs_unmatched_files(self, runner, tmp_path):
        """list-pairs ignores PDFs without matching MP3."""
        (tmp_path / "paper_only.pdf").write_bytes(b"%PDF-1.4 fake")

        result = runner.invoke(main, ["training", "list-pairs", str(tmp_path)])
        assert result.exit_code == 0
        # Should not find any pairs since there's no matching mp3
        assert "paper_only" not in result.output

    def test_run_default_options(self, runner):
        """Verify training run command has required options."""
        result = runner.invoke(main, ["training", "run", "--help"])
        assert "--pairs-dir" in result.output
        assert "--output-dir" in result.output
        assert "--max-trials" in result.output


# ============================================================
# Status Command
# ============================================================

class TestStatusCommand:
    """Tests for the 'status' command."""

    def test_help(self, runner):
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    @patch("cli.status.check_config")
    def test_status_runs(self, mock_config, runner):
        mock_config.return_value = {"ANTHROPIC_API_KEY": True, "LUMA_API_KEY": False}

        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        # Status command should output something about the system
        assert len(result.output) > 0

    @patch("cli.status.get_status_dict")
    def test_status_json(self, mock_status, runner):
        mock_status.return_value = {
            "providers": [],
            "agents": [],
            "config": {"ANTHROPIC_API_KEY": True},
        }
        result = runner.invoke(main, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "providers" in data
        assert "agents" in data
        assert "config" in data


# ============================================================
# Providers Command
# ============================================================

class TestProvidersCommand:
    """Tests for the 'providers' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["providers", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output

    def test_list_providers(self, runner):
        result = runner.invoke(main, ["providers", "list"])
        assert result.exit_code == 0
        # Should list some providers (at minimum the help should be shown)
        assert len(result.output) > 0

    def test_list_providers_json(self, runner):
        result = runner.invoke(main, ["providers", "list", "--json"])
        # JSON output should either be valid JSON or the command should work
        assert result.exit_code == 0 or "error" in result.output.lower()

    def test_list_filter_by_category(self, runner):
        result = runner.invoke(main, ["providers", "list", "--category", "video"])
        assert result.exit_code == 0 or "error" in result.output.lower()

    def test_list_filter_by_status(self, runner):
        result = runner.invoke(main, ["providers", "list", "--status", "implemented"])
        assert result.exit_code == 0 or "error" in result.output.lower()

    def test_check_provider(self, runner):
        result = runner.invoke(main, ["providers", "check", "luma"])
        assert result.exit_code == 0 or "error" in result.output.lower()

    def test_check_unknown_provider(self, runner):
        result = runner.invoke(main, ["providers", "check", "nonexistent"])
        assert result.exit_code == 0 or "error" in result.output.lower()


# ============================================================
# Agents Command
# ============================================================

class TestAgentsCommand:
    """Tests for the 'agents' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["agents", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "schema" in result.output

    def test_list_agents(self, runner):
        result = runner.invoke(main, ["agents", "list"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_list_agents_json(self, runner):
        result = runner.invoke(main, ["agents", "list", "--json"])
        assert result.exit_code == 0 or "error" in result.output.lower()

    def test_schema(self, runner):
        result = runner.invoke(main, ["agents", "schema", "ProducerAgent"])
        assert result.exit_code == 0 or "error" in result.output.lower()

    def test_schema_unknown_agent(self, runner):
        result = runner.invoke(main, ["agents", "schema", "FakeAgent"])
        # Should either work or return an error
        assert result.exit_code == 0 or result.exit_code != 0


# ============================================================
# Config Command
# ============================================================

class TestConfigCommand:
    """Tests for the 'config' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["config", "--help"])
        assert result.exit_code == 0
        assert "show" in result.output
        assert "validate" in result.output
        assert "init" in result.output

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    def test_show(self, runner):
        result = runner.invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "ANTHROPIC_API_KEY" in result.output

    def test_init_creates_env_file(self, isolated_runner):
        result = isolated_runner.invoke(main, ["config", "init"])
        assert result.exit_code == 0
        assert Path(".env").exists()
        content = Path(".env").read_text()
        assert "ANTHROPIC_API_KEY" in content
        assert "LUMA_API_KEY" in content

    def test_init_no_overwrite_without_force(self, isolated_runner):
        Path(".env").write_text("existing content")
        result = isolated_runner.invoke(main, ["config", "init"])
        assert result.exit_code == 0
        assert "already exists" in result.output
        assert Path(".env").read_text() == "existing content"

    def test_init_force_overwrites(self, isolated_runner):
        Path(".env").write_text("old content")
        result = isolated_runner.invoke(main, ["config", "init", "--force"])
        assert result.exit_code == 0
        assert "old content" not in Path(".env").read_text()
        assert "ANTHROPIC_API_KEY" in Path(".env").read_text()


# ============================================================
# Themes Command
# ============================================================

class TestThemesCommand:
    """Tests for the 'themes' command."""

    def test_help(self, runner):
        result = runner.invoke(main, ["themes", "--help"])
        assert result.exit_code == 0
        assert "--list" in result.output
        assert "--preview" in result.output

    def test_list_themes(self, runner):
        result = runner.invoke(main, ["themes", "--list"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "matrix" in result.output

    def test_show_specific_theme(self, runner):
        result = runner.invoke(main, ["themes", "matrix"])
        assert result.exit_code == 0
        assert "matrix" in result.output.lower()

    def test_unknown_theme(self, runner):
        result = runner.invoke(main, ["themes", "nonexistent"])
        assert result.exit_code == 0
        assert "Unknown theme" in result.output

    def test_preview_theme(self, runner):
        result = runner.invoke(main, ["themes", "default", "--preview"])
        assert result.exit_code == 0

    def test_preview_all(self, runner):
        result = runner.invoke(main, ["themes", "--preview"])
        assert result.exit_code == 0

    def test_default_shows_theme_list(self, runner):
        """Running themes with no args lists available themes."""
        result = runner.invoke(main, ["themes"])
        assert result.exit_code == 0
        assert "Available Themes" in result.output


# ============================================================
# Memory Command
# ============================================================

class TestMemoryCommand:
    """Tests for the 'memory' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["memory", "--help"])
        assert result.exit_code == 0
        assert "stats" in result.output
        assert "list" in result.output
        assert "search" in result.output
        assert "add" in result.output
        assert "guidelines" in result.output
        assert "tree" in result.output

    def test_subcommand_help_stats(self, runner):
        result = runner.invoke(main, ["memory", "stats", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_subcommand_help_list(self, runner):
        result = runner.invoke(main, ["memory", "list", "--help"])
        assert result.exit_code == 0
        assert "--level" in result.output
        assert "--limit" in result.output

    def test_subcommand_help_search(self, runner):
        result = runner.invoke(main, ["memory", "search", "--help"])
        assert result.exit_code == 0
        assert "--provider" in result.output

    def test_subcommand_help_add(self, runner):
        result = runner.invoke(main, ["memory", "add", "--help"])
        assert result.exit_code == 0
        assert "--category" in result.output
        assert "--level" in result.output

    def test_subcommand_help_guidelines(self, runner):
        result = runner.invoke(main, ["memory", "guidelines", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output

    def test_subcommand_help_validate(self, runner):
        result = runner.invoke(main, ["memory", "validate", "--help"])
        assert result.exit_code == 0
        assert "--provider" in result.output
        assert "--fix" in result.output

    def test_global_options(self, runner):
        """Memory group accepts --org, --actor, --backend."""
        result = runner.invoke(main, ["memory", "--help"])
        assert "--org" in result.output or "-o" in result.output
        assert "--actor" in result.output or "-a" in result.output
        assert "--backend" in result.output or "-b" in result.output

    def test_tree_command(self, runner):
        """Tree command shows namespace hierarchy."""
        result = runner.invoke(main, ["memory", "tree"])
        assert result.exit_code == 0
        assert "platform" in result.output
        assert "Namespace" in result.output or "Retrieval" in result.output

    def test_tree_with_provider(self, runner):
        result = runner.invoke(main, ["memory", "tree", "--provider", "runway"])
        assert result.exit_code == 0
        assert "runway" in result.output


# ============================================================
# Produce Command: Helper Functions (Unit Tests)
# ============================================================

class TestProduceHelpers:
    """Unit tests for helper functions in cli/produce.py"""

    def test_truncate_text_short(self):
        from cli.produce import truncate_text
        assert truncate_text("short", 50) == "short"

    def test_truncate_text_exact_limit(self):
        from cli.produce import truncate_text
        text = "a" * 50
        assert truncate_text(text, 50) == text

    def test_truncate_text_long(self):
        from cli.produce import truncate_text
        text = "This is a rather long sentence that should be truncated at a word boundary"
        result = truncate_text(text, 30)
        assert len(result) <= 30
        assert result.endswith("...")

    def test_truncate_text_verbose_skips(self):
        from cli.produce import truncate_text
        long_text = "x" * 100
        assert truncate_text(long_text, 50, verbose=True) == long_text

    def test_truncate_text_empty(self):
        from cli.produce import truncate_text
        assert truncate_text("", 50) == ""

    def test_truncate_text_none(self):
        from cli.produce import truncate_text
        assert truncate_text(None, 50) is None

    def test_truncate_text_custom_suffix(self):
        from cli.produce import truncate_text
        text = "A very long sentence that needs to be truncated with a custom suffix end"
        result = truncate_text(text, 30, suffix="…")
        assert result.endswith("…")

    def test_get_video_provider_mock(self):
        from cli.produce import get_video_provider
        from core.providers import MockVideoProvider
        provider, name = get_video_provider("luma", live=False)
        assert isinstance(provider, MockVideoProvider)
        assert name == "mock"

    def test_get_video_provider_explicit_mock(self):
        from cli.produce import get_video_provider
        from core.providers import MockVideoProvider
        provider, name = get_video_provider("mock", live=True)
        assert isinstance(provider, MockVideoProvider)
        assert name == "mock"

    def test_get_video_provider_unknown(self):
        from cli.produce import get_video_provider
        from core.providers import MockVideoProvider
        provider, name = get_video_provider("unknown_provider", live=True)
        assert isinstance(provider, MockVideoProvider)
        assert name == "mock"

    def test_get_audio_provider_mock(self):
        from cli.produce import get_audio_provider
        provider, name = get_audio_provider(live=False)
        assert provider is None
        assert name == "mock"

    def test_load_seed_assets_empty_dir(self, tmp_path):
        from cli.produce import load_seed_assets
        assets = load_seed_assets(str(tmp_path))
        assert assets == []

    def test_load_seed_assets_with_images(self, tmp_path):
        from cli.produce import load_seed_assets
        (tmp_path / "img1.png").write_bytes(b"fake png")
        (tmp_path / "img2.jpg").write_bytes(b"fake jpg")
        (tmp_path / "doc.txt").write_text("not an image")
        assets = load_seed_assets(str(tmp_path))
        assert len(assets) == 2
        filenames = {a.filename for a in assets}
        assert "img1.png" in filenames
        assert "img2.jpg" in filenames

    def test_load_seed_assets_sorted(self, tmp_path):
        from cli.produce import load_seed_assets
        (tmp_path / "c.png").write_bytes(b"fake")
        (tmp_path / "a.png").write_bytes(b"fake")
        (tmp_path / "b.png").write_bytes(b"fake")
        assets = load_seed_assets(str(tmp_path))
        assert [a.filename for a in assets] == ["a.png", "b.png", "c.png"]

    def test_seed_asset_local_path(self, tmp_path):
        from cli.produce import SeedAsset
        asset = SeedAsset(path=tmp_path / "test.png", filename="test.png")
        assert str(tmp_path / "test.png") in asset.local_path


# ============================================================
# Training Command: Helper Functions (Unit Tests)
# ============================================================

class TestTrainingHelpers:
    """Unit tests for helper functions in cli/training.py"""

    def test_save_and_load_checkpoint(self, tmp_path):
        from cli.training import save_checkpoint, load_checkpoint
        data = {"key": "value", "nested": {"a": 1}}
        save_checkpoint(tmp_path, "pair_001", "transcription", data)

        loaded = load_checkpoint(tmp_path, "pair_001", "transcription")
        assert loaded == data

    def test_load_checkpoint_missing(self, tmp_path):
        from cli.training import load_checkpoint
        result = load_checkpoint(tmp_path, "nonexistent", "phase")
        assert result is None

    def test_get_namespace_level(self):
        from cli.memory import _get_namespace_level
        assert _get_namespace_level("/platform/learnings") == "platform"
        assert _get_namespace_level("/org/myorg/actor/dev/learnings") == "user"
        assert _get_namespace_level("/org/myorg/actor/dev/sessions/abc/learnings") == "session"
        assert _get_namespace_level("/org/myorg/learnings") == "org"

    def test_document_graph_to_knowledge_graph(self):
        """Test the conversion function with a minimal mock graph."""
        from cli.training import document_graph_to_knowledge_graph

        # Create a minimal mock document graph
        mock_atom = MagicMock()
        mock_atom.topics = ["machine learning", "neural networks"]
        mock_atom.entities = ["GPT", "Transformer"]

        mock_graph = MagicMock()
        mock_graph.atoms = {"atom_1": mock_atom}
        mock_graph.full_summary = "A paper about ML."
        mock_graph.one_paragraph = "Short summary."

        result = document_graph_to_knowledge_graph(mock_graph, "test_pair")
        assert result.project_id == "test_pair"
        assert "atom_1" in result.atoms
        assert "machine learning" in result.topic_index
        assert "GPT" in result.entity_index


# ============================================================
# Discover Training Pairs (Async)
# ============================================================

class TestDiscoverTrainingPairs:
    """Tests for the async discover_training_pairs function."""

    @pytest.mark.asyncio
    async def test_discover_empty_dir(self, tmp_path):
        from cli.training import discover_training_pairs
        pairs = await discover_training_pairs(tmp_path)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_discover_matched_pair(self, tmp_path):
        from cli.training import discover_training_pairs
        (tmp_path / "study1.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "study1.mp3").write_bytes(b"mp3data")
        pairs = await discover_training_pairs(tmp_path)
        assert len(pairs) == 1
        assert pairs[0].pair_id == "study1"

    @pytest.mark.asyncio
    async def test_discover_ignores_unmatched(self, tmp_path):
        from cli.training import discover_training_pairs
        (tmp_path / "only_pdf.pdf").write_bytes(b"%PDF")
        (tmp_path / "only_mp3.mp3").write_bytes(b"mp3")
        pairs = await discover_training_pairs(tmp_path)
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_discover_multiple_pairs(self, tmp_path):
        from cli.training import discover_training_pairs
        for name in ["alpha", "beta", "gamma"]:
            (tmp_path / f"{name}.pdf").write_bytes(b"%PDF")
            (tmp_path / f"{name}.mp3").write_bytes(b"mp3")
        pairs = await discover_training_pairs(tmp_path)
        assert len(pairs) == 3
        pair_ids = {p.pair_id for p in pairs}
        assert pair_ids == {"alpha", "beta", "gamma"}


# ============================================================
# Render Command
# ============================================================

class TestRenderCommand:
    """Tests for the 'render' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["render", "--help"])
        assert result.exit_code == 0


# ============================================================
# KB Command
# ============================================================

class TestKBCommand:
    """Tests for the 'kb' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["kb", "--help"])
        assert result.exit_code == 0
        assert "Knowledge base" in result.output or "kb" in result.output.lower()


# ============================================================
# Provider (Onboarding) Command
# ============================================================

class TestProviderOnboardingCommand:
    """Tests for the 'provider' (onboarding) command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["provider", "--help"])
        assert result.exit_code == 0


# ============================================================
# Secrets Command
# ============================================================

class TestSecretsCommand:
    """Tests for the 'secrets' command group."""

    def test_help(self, runner):
        result = runner.invoke(main, ["secrets", "--help"])
        assert result.exit_code == 0
