"""Config command — manage API key credentials securely."""

import getpass

import click

from codecheck.credentials.store import CredentialStore


def config(status: bool = False, set_key: bool = False, clear_key: bool = False) -> None:
    """Manage credentials and configuration.

    Store API keys securely using encrypted storage (Fernet + PBKDF2).

    Args:
        status: If True, show credential status.
        set_key: If True, prompt to store a new API key.
        clear_key: If True, remove stored API key.
    """
    store = CredentialStore()

    if sum([status, set_key, clear_key]) > 1:
        click.echo(
            click.style(
                "Error: Only one of --status, --set-key, --clear-key can be used at a time.",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(3)

    if not any([status, set_key, clear_key]):
        # Default: show status
        _show_status(store)
    elif status:
        _show_status(store)
    elif set_key:
        _set_key(store)
    elif clear_key:
        _clear_key(store)


def _show_status(store: CredentialStore) -> None:
    """Display credential configuration status.

    Never shows the plaintext API key.
    """
    if store.exists():
        click.echo(
            click.style("✓ API key is configured.", fg="green")
        )
        click.echo(f"  Storage: {store.path}")
    else:
        click.echo(
            click.style("✗ No API key configured.", fg="yellow")
        )
        click.echo("  Run 'codecheck config --set-key' to configure.")
        click.echo("  Or set the CODE_CHECK_API_KEY environment variable.")

    # Check env var
    import os

    env_key = os.environ.get("CODE_CHECK_API_KEY")
    if env_key:
        click.echo(
            click.style(
                "  Note: CODE_CHECK_API_KEY environment variable is also set.",
                fg="yellow",
            )
        )


def _set_key(store: CredentialStore) -> None:
    """Prompt the user to enter and store an API key securely."""
    click.echo("CodeCheck API Key Setup")
    click.echo("=" * 40)

    # Get API key (hidden input)
    api_key = getpass.getpass("Enter your API key: ")
    if not api_key:
        click.echo(
            click.style("Error: API key must not be empty.", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    # Confirm API key
    api_key_confirm = getpass.getpass("Confirm API key: ")
    if api_key != api_key_confirm:
        click.echo(
            click.style("Error: API keys do not match.", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    # Get master password
    click.echo("\nChoose a master password to encrypt your API key.")
    click.echo("You'll need this password each time CodeCheck needs your API key.")

    master_password = getpass.getpass("Master password: ")
    if not master_password:
        click.echo(
            click.style("Error: Master password must not be empty.", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    master_confirm = getpass.getpass("Confirm master password: ")
    if master_password != master_confirm:
        click.echo(
            click.style("Error: Passwords do not match.", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    # Store the key
    try:
        store.store(api_key, master_password)
        click.echo(
            click.style(
                f"\n✓ API key stored securely at: {store.path}",
                fg="green",
            )
        )
        click.echo(
            click.style(
                "  Keep your master password safe — it cannot be recovered.",
                fg="yellow",
            )
        )
    except Exception as e:
        click.echo(
            click.style(f"Error storing API key: {e}", fg="red"),
            err=True,
        )
        raise SystemExit(1) from e


def _clear_key(store: CredentialStore) -> None:
    """Remove stored API key credentials."""
    if not store.exists():
        click.echo(
            click.style("No stored API key to clear.", fg="yellow")
        )
        return

    if not click.confirm(
        "Are you sure you want to delete your stored API key?"
    ):
        click.echo("Aborted.")
        return

    removed = store.clear()
    if removed:
        click.echo(
            click.style("✓ API key has been cleared.", fg="green")
        )
    else:
        click.echo(
            click.style("Error: Failed to clear API key.", fg="red"),
            err=True,
        )
        raise SystemExit(1)
