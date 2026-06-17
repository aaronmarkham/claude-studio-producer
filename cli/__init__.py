"""Claude Studio Producer CLI"""

import click
from dotenv import load_dotenv
from ._version import __version__
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
from .produce_unified import produce_unified_cmd
from .assemble import assemble_cmd
from .assets import assets
from .upload import upload_cmd
from .figures import figures

# Load .env file at CLI startup
load_dotenv()


@click.group()
@click.version_option(version=__version__)
def main():
    """Claude Studio Producer - AI Video Production Pipeline

    \b
    Quick Start:
      cs produce topic "How to make French press coffee" --mock
      cs produce paper <kb_id> --live -p luma
      cs produce script myscript.txt --budget 15

    \b
    Production (produce is a group — pick an input):
      produce paper     Produce a video from a knowledge base project
      produce topic     Research a topic, build a KB, then produce
      produce script    Produce from a pre-written script file
      produce project   Multi-source production (shards + KB + assets)
      produce status    Show status of a production run
      produce resume    Resume a run from its last checkpoint
      produce list      List all production runs
      produce edit      Edit a single scene in a run
      produce-legacy    Classic one-shot concept->video pipeline (-c CONCEPT)
      produce-video     Generate explainer video from a podcast script

    \b
    Post-production & assets:
      assemble       Assemble a rough cut from a production run
      figures        Inject/list/remove figures in a run
      assets         Asset tracking and approval workflow
      render         Render commands (edl, mix video+audio)
      upload         Upload videos to platforms (YouTube)

    \b
    Knowledge & inputs:
      document       Document ingestion (PDF to knowledge graph)
      kb             Knowledge base management (multi-source projects)
      memory         Memory and learnings management

    \b
    Providers, config & info:
      test-provider  Test a single provider (quick validation)
      provider       Provider onboarding and management
      providers      List and manage providers
      luma           Luma API management (list, download, recover)
      training       Training pipeline for podcast calibration
      qa             QA inspection (view quality scores)
      secrets        Secure API key management (OS keychain)
      status         Show system status
      agents         List and manage agents
      config         Manage configuration
      themes         List and preview color themes
    """
    pass


# Main production commands
main.add_command(produce_unified_cmd, name="produce")
main.add_command(produce_cmd, name="produce-legacy")
main.add_command(produce_video_cmd, name="produce-video")
main.add_command(assemble_cmd, name="assemble")
main.add_command(assets, name="assets")
main.add_command(figures, name="figures")
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

# Upload commands
main.add_command(upload_cmd, name="upload")


if __name__ == "__main__":
    main()
