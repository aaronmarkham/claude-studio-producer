"""
CLI commands for secure API key management.

Usage:
    claude-studio secrets list          # Show configured keys
    claude-studio secrets set KEY       # Store a key securely
    claude-studio secrets delete KEY    # Remove a key
    claude-studio secrets import .env   # Import from .env file
"""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group(name="secrets")
def secrets_cli():
    """Manage API keys securely using OS keychain."""
    pass


@secrets_cli.command(name="list")
def list_keys():
    """List all API keys and their status."""
    from core.secrets import list_api_keys, KNOWN_KEYS, is_keyring_available

    if not is_keyring_available():
        console.print(
            "[yellow]Warning:[/yellow] keyring not available. "
            "Install with: pip install keyring"
        )
        console.print("Falling back to environment variable check only.\n")

    status = list_api_keys()

    table = Table(title="API Key Status")
    table.add_column("Key", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Status", style="bold")

    for key_name, description in KNOWN_KEYS.items():
        key_status = status.get(key_name, "not_set")

        if key_status == "keychain":
            status_display = "[green]Keychain[/green]"
        elif key_status == "env":
            status_display = "[yellow]Env var[/yellow]"
        else:
            status_display = "[red]Not set[/red]"

        table.add_row(key_name, description, status_display)

    console.print(table)
    console.print()

    # Show legend
    console.print("[green]Keychain[/green] = Stored securely in OS credential manager")
    console.print("[yellow]Env var[/yellow] = Available via environment variable (less secure)")
    console.print("[red]Not set[/red] = Not configured")


@secrets_cli.command(name="set")
@click.argument("key_name")
@click.option("--value", "-v", help="API key value (will prompt if not provided)")
def set_key(key_name: str, value: str = None):
    """Store an API key in the secure keychain."""
    from core.secrets import set_api_key, KNOWN_KEYS, is_keyring_available

    if not is_keyring_available():
        console.print(
            "[red]Error:[/red] keyring not available. "
            "Install with: pip install keyring"
        )
        return

    # Normalize key name
    key_name = key_name.upper()

    # Only auto-append _API_KEY if the key isn't already known and doesn't end with a known suffix
    if key_name not in KNOWN_KEYS:
        if not key_name.endswith("_API_KEY") and not key_name.endswith("_KEY") and not key_name.endswith("_ID") and not key_name.endswith("_SECRET") and not key_name.endswith("_PATH"):
            key_name = f"{key_name}_API_KEY"

    # Check if it's a known key
    if key_name not in KNOWN_KEYS:
        console.print(f"[yellow]Warning:[/yellow] {key_name} is not a recognized key name.")
        if not click.confirm("Store anyway?"):
            return

    # Prompt for value if not provided
    if not value:
        value = click.prompt(f"Enter value for {key_name}", hide_input=True)

    if not value:
        console.print("[red]Error:[/red] No value provided")
        return

    if set_api_key(key_name, value):
        console.print(f"[green]Success:[/green] Stored {key_name} in secure keychain")

        # Show where it's stored based on platform
        import platform
        system = platform.system()
        if system == "Windows":
            console.print("  Location: Windows Credential Manager")
        elif system == "Darwin":
            console.print("  Location: macOS Keychain")
        else:
            console.print("  Location: Secret Service (GNOME Keyring/KWallet)")
    else:
        console.print(f"[red]Error:[/red] Failed to store {key_name}")


@secrets_cli.command(name="delete")
@click.argument("key_name")
@click.option("--force", "-f", is_flag=True, help="Don't ask for confirmation")
def delete_key(key_name: str, force: bool = False):
    """Delete an API key from the keychain."""
    from core.secrets import delete_api_key, is_keyring_available

    if not is_keyring_available():
        console.print(
            "[red]Error:[/red] keyring not available. "
            "Install with: pip install keyring"
        )
        return

    # Normalize key name
    key_name = key_name.upper()
    if key_name not in KNOWN_KEYS:
        if not key_name.endswith("_API_KEY") and not key_name.endswith("_KEY") and not key_name.endswith("_ID") and not key_name.endswith("_SECRET") and not key_name.endswith("_PATH"):
            key_name = f"{key_name}_API_KEY"

    if not force:
        if not click.confirm(f"Delete {key_name} from keychain?"):
            return

    if delete_api_key(key_name):
        console.print(f"[green]Success:[/green] Deleted {key_name} from keychain")
    else:
        console.print(f"[yellow]Warning:[/yellow] {key_name} not found in keychain")


@secrets_cli.command(name="import")
@click.argument("env_file", type=click.Path(exists=True))
@click.option("--delete-after", is_flag=True, help="Delete .env file after import")
def import_keys(env_file: str, delete_after: bool = False):
    """Import API keys from a .env file into the secure keychain."""
    from core.secrets import import_from_env_file, is_keyring_available
    import os

    if not is_keyring_available():
        console.print(
            "[red]Error:[/red] keyring not available. "
            "Install with: pip install keyring"
        )
        return

    console.print(f"Importing keys from {env_file}...")

    try:
        results = import_from_env_file(env_file)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] File not found: {env_file}")
        return

    if not results:
        console.print("[yellow]No API keys found in file[/yellow]")
        return

    # Show results
    success_count = sum(1 for v in results.values() if v)
    fail_count = sum(1 for v in results.values() if not v)

    for key_name, success in results.items():
        if success:
            console.print(f"  [green]+[/green] {key_name}")
        else:
            console.print(f"  [red]x[/red] {key_name}")

    console.print()
    console.print(f"Imported: {success_count} keys")
    if fail_count:
        console.print(f"Failed: {fail_count} keys")

    # Optionally delete the .env file
    if delete_after and success_count > 0:
        if click.confirm(f"\nDelete {env_file}? (keys are now in secure storage)"):
            os.remove(env_file)
            console.print(f"[green]Deleted[/green] {env_file}")
    elif success_count > 0:
        console.print(
            f"\n[yellow]Tip:[/yellow] You can now delete {env_file} - "
            "keys are stored securely in your OS keychain."
        )


@secrets_cli.command(name="check")
def check_backend():
    """Check keyring backend status and capabilities."""
    from core.secrets import is_keyring_available

    import platform
    system = platform.system()

    console.print(f"Platform: {system}")

    if not is_keyring_available():
        console.print("[red]Keyring not available[/red]")
        console.print("\nInstall with: pip install keyring")
        return

    try:
        import keyring
        backend = keyring.get_keyring()
        console.print(f"Backend: [green]{backend.__class__.__name__}[/green]")

        if system == "Windows":
            console.print("Storage: Windows Credential Manager")
            console.print("Access: Control Panel > Credential Manager")
        elif system == "Darwin":
            console.print("Storage: macOS Keychain")
            console.print("Access: Keychain Access.app")
        else:
            console.print("Storage: Secret Service API")
            console.print("Access: Seahorse or KWallet")

        console.print("\n[green]Keyring is working correctly![/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
