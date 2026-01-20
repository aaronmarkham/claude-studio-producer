"""Claude Studio Producer CLI"""

import click
from dotenv import load_dotenv
from .status import status_cmd
from .providers import providers_cmd
from .agents import agents_cmd
from .config import config_cmd
from .produce import produce_cmd
from .test_provider import test_provider_cmd
from .render import render_cmd
from .themes import themes_cmd
from .luma import luma_cmd
from .memory import memory_cmd

# Load .env file at CLI startup
load_dotenv()


@click.group()
@click.version_option(version="0.5.0")
def main():
    """Claude Studio Producer - AI Video Production Pipeline

    \b
    Quick Start:
      claude-studio produce -c "Your video concept" --mock
      claude-studio produce -c "Your video concept" --live -p luma

    \b
    Commands:
      produce        Run full video production pipeline
      render         Render final video from existing run
      test-provider  Test a single provider (quick validation)
      luma           Luma API management (list, download, recover)
      memory         Memory and learnings management
      status         Show system status
      providers      List and manage providers
      agents         List and manage agents
      config         Manage configuration
      themes         List and preview color themes
    """
    pass


# Main production commands
main.add_command(produce_cmd, name="produce")
main.add_command(render_cmd, name="render")
main.add_command(test_provider_cmd, name="test-provider")
main.add_command(luma_cmd, name="luma")
main.add_command(memory_cmd, name="memory")

# Status and info commands
main.add_command(status_cmd, name="status")
main.add_command(providers_cmd, name="providers")
main.add_command(agents_cmd, name="agents")
main.add_command(config_cmd, name="config")
main.add_command(themes_cmd, name="themes")


if __name__ == "__main__":
    main()
