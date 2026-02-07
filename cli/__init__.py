"""Claude Studio Producer CLI"""

import click
from dotenv import load_dotenv
from .status import status_cmd
from .providers import providers_cmd
from .agents import agents_cmd
from .config import config_cmd
from .produce import produce_cmd
from .test_provider import test_provider_cmd
from .render import render_cmd, mix_cmd, edl_cmd
from .themes import themes_cmd
from .luma import luma_cmd
from .memory import memory_cmd
from .qa import qa_cmd
from .document import document_cmd
from .kb import kb_cmd
from .provider_cli import provider
from .secrets import secrets_cli
from .resume import resume_cmd
from .training import training
from .produce_video import produce_video_cmd
from .assemble import assemble_cmd
from .assets import assets

# Load .env file at CLI startup
load_dotenv()


@click.group()
@click.version_option(version="0.6.0")
def main():
    """Claude Studio Producer - AI Video Production Pipeline

    \b
    Quick Start:
      claude-studio produce -c "Your video concept" --mock
      claude-studio produce -c "Your video concept" --live -p luma

    \b
    Commands:
      produce        Run full video production pipeline
      produce-video  Generate explainer video from podcast script
      assemble       Assemble rough cut video from production run
      assets         Asset tracking and approval workflow
      resume         Resume a production from where it stopped
      render         Render commands (edl, mix video+audio)
      test-provider  Test a single provider (quick validation)
      luma           Luma API management (list, download, recover)
      memory         Memory and learnings management
      qa             QA inspection (view quality scores)
      document       Document ingestion (PDF to knowledge graph)
      kb             Knowledge base management (multi-source projects)
      provider       Provider onboarding and management
      training       Training pipeline for podcast calibration
      secrets        Secure API key management (OS keychain)
      status         Show system status
      providers      List and manage providers
      agents         List and manage agents
      config         Manage configuration
      themes         List and preview color themes
    """
    pass


# Main production commands
main.add_command(produce_cmd, name="produce")
main.add_command(produce_video_cmd, name="produce-video")
main.add_command(assemble_cmd, name="assemble")
main.add_command(assets, name="assets")
main.add_command(resume_cmd, name="resume")
main.add_command(render_cmd, name="render")
main.add_command(test_provider_cmd, name="test-provider")
main.add_command(luma_cmd, name="luma")
main.add_command(memory_cmd, name="memory")
main.add_command(qa_cmd, name="qa")
main.add_command(document_cmd, name="document")
main.add_command(kb_cmd, name="kb")

# Provider management commands
main.add_command(provider, name="provider")

# Training commands
main.add_command(training, name="training")

# Security commands
main.add_command(secrets_cli, name="secrets")

# Status and info commands
main.add_command(status_cmd, name="status")
main.add_command(providers_cmd, name="providers")
main.add_command(agents_cmd, name="agents")
main.add_command(config_cmd, name="config")
main.add_command(themes_cmd, name="themes")


if __name__ == "__main__":
    main()
