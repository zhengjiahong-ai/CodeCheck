"""Interactive prompts for credential management.

These functions handle user interaction for setting, entering,
and checking the status of API key credentials.
"""

from getpass import getpass

from codecheck.credentials.store import CredentialError, CredentialStore


def prompt_set_api_key(store: CredentialStore | None = None) -> bool:
    """Interactively prompt the user to set their API key.

    Flow:
        1. Prompt for API key (hidden input)
        2. Prompt for master password (hidden input)
        3. Confirm master password
        4. Encrypt and store

    Args:
        store: A CredentialStore instance (created with default path if None).

    Returns:
        True if the key was stored successfully, False if the user cancelled.
    """
    if store is None:
        store = CredentialStore()

    print("CodeCheck — API Key Setup")
    print("=" * 40)
    print("The API key will be encrypted and stored at:")
    print(f"  {store.path}")
    print()

    api_key = getpass("Enter your API key (input hidden): ").strip()
    if not api_key:
        print("No API key entered. Aborted.")
        return False

    master_password = getpass("Set a master password (input hidden): ").strip()
    if not master_password:
        print("No master password entered. Aborted.")
        return False

    confirm = getpass("Confirm master password: ").strip()
    if master_password != confirm:
        print("Passwords do not match. Aborted.")
        return False

    try:
        store.store(api_key, master_password)
        print(f"\nAPI key stored securely at {store.path}")
        return True
    except CredentialError as e:
        print(f"Error: {e}")
        return False


def prompt_master_password() -> str:
    """Prompt the user to enter their master password.

    Returns:
        The master password string (may be empty if user cancels).
    """
    return getpass("Enter master password: ").strip()


def get_credential_status(store: CredentialStore | None = None) -> str:
    """Return a human-readable credential status string.

    Args:
        store: A CredentialStore instance (created with default path if None).

    Returns:
        "Configured" if credentials exist, "Not configured" otherwise.
        Never reveals the API key or any part of it.
    """
    if store is None:
        store = CredentialStore()
    if store.exists():
        return "Configured"
    return "Not configured"


def prompt_clear_key(store: CredentialStore | None = None) -> bool:
    """Interactively prompt the user to clear their stored API key.

    Args:
        store: A CredentialStore instance (created with default path if None).

    Returns:
        True if the key was cleared, False if no key existed or user cancelled.
    """
    if store is None:
        store = CredentialStore()

    if not store.exists():
        print("No stored credentials found.")
        return False

    confirm = input("Delete stored API key? This cannot be undone. [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return False

    store.clear()
    print("API key deleted.")
    return True
