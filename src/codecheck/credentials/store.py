"""Credential store — encrypt, store, retrieve, and clear API keys.

Uses Fernet (AES-128-CBC + HMAC-SHA256) for authenticated encryption.
The encryption key is derived from a master password via PBKDF2-HMAC-SHA256
with a random salt (100,000 iterations by default).

Storage format (in ~/.codecheck/credentials.enc):
    base64(salt) + "$" + base64(fernet_token)

Security:
    - File permissions set to 0o600 (owner read/write only)
    - API key never written to logs, terminal, or any plaintext file
    - Master password is not stored; only the salt is persisted
    - Environment variable CODE_CHECK_API_KEY as fallback
"""

import base64
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CredentialError(Exception):
    """Raised on credential store errors (wrong password, corrupt file, etc.)."""


class CredentialStore:
    """Encrypted API key storage using Fernet + PBKDF2.

    Usage:
        store = CredentialStore()
        store.store("sk-abc123", "my-master-password")
        key = store.retrieve("my-master-password")
        assert key == "sk-abc123"
    """

    # PBKDF2 parameters
    SALT_LENGTH = 16
    ITERATIONS = 100_000
    KEY_LENGTH = 32  # bytes; Fernet needs 32-byte URL-safe base64 key

    def __init__(self, storage_path: str | Path | None = None):
        """Initialize the credential store.

        Args:
            storage_path: Path to the encrypted credentials file.
                          Defaults to ~/.codecheck/credentials.enc
        """
        if storage_path is None:
            storage_path = Path.home() / ".codecheck" / "credentials.enc"
        self._storage_path = Path(storage_path)

    @property
    def path(self) -> Path:
        """Return the storage file path."""
        return self._storage_path

    def exists(self) -> bool:
        """Check if a credentials file exists."""
        return self._storage_path.is_file()

    def store(self, api_key: str, master_password: str) -> None:
        """Encrypt and store the API key.

        Args:
            api_key: The API key to encrypt.
            master_password: The master password used to derive the encryption key.

        Raises:
            CredentialError: If the API key or password is empty.
        """
        if not api_key:
            raise CredentialError("API key must not be empty")
        if not master_password:
            raise CredentialError("Master password must not be empty")

        salt = secrets.token_bytes(self.SALT_LENGTH)
        key = self._derive_key(master_password, salt)
        fernet = Fernet(key)

        token = fernet.encrypt(api_key.encode("utf-8"))

        # Format: base64(salt) + "$" + base64(token)
        data = (
            base64.b64encode(salt).decode("ascii")
            + "$"
            + base64.b64encode(token).decode("ascii")
        )

        # Ensure parent directory exists with secure permissions
        self._storage_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Write with 0o600 permissions
        fd = os.open(
            self._storage_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            os.write(fd, data.encode("utf-8"))
        finally:
            os.close(fd)

    def retrieve(self, master_password: str) -> str:
        """Decrypt and return the stored API key.

        Args:
            master_password: The master password to derive the encryption key.

        Returns:
            The decrypted API key as a string.

        Raises:
            CredentialError: If the file doesn't exist, is corrupt, or the
                             password is wrong.
        """
        if not self.exists():
            raise CredentialError(
                f"No credentials file found at {self._storage_path}. "
                "Run 'codecheck config --set-key' to configure."
            )

        if not master_password:
            raise CredentialError("Master password must not be empty")

        try:
            data = self._storage_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise CredentialError(f"Failed to read credentials file: {e}") from e

        if "$" not in data:
            raise CredentialError(
                "Credentials file is corrupted (missing separator)"
            )

        salt_b64, token_b64 = data.split("$", 1)

        try:
            salt = base64.b64decode(salt_b64)
            token = base64.b64decode(token_b64)
        except Exception as e:
            raise CredentialError(
                f"Credentials file is corrupted (invalid base64): {e}"
            ) from e

        key = self._derive_key(master_password, salt)
        fernet = Fernet(key)

        try:
            api_key = fernet.decrypt(token).decode("utf-8")
        except Exception as e:
            raise CredentialError(
                "Failed to decrypt credentials. The master password may be wrong, "
                "or the credentials file is corrupted."
            ) from e

        return api_key

    def clear(self) -> bool:
        """Delete the credentials file.

        Returns:
            True if the file was deleted, False if it didn't exist.
        """
        if not self.exists():
            return False
        self._storage_path.unlink()
        return True

    @classmethod
    def _derive_key(cls, master_password: str, salt: bytes) -> bytes:
        """Derive a Fernet-compatible key from a password and salt.

        Uses PBKDF2-HMAC-SHA256 to derive 32 bytes, then encodes as
        URL-safe base64 for Fernet.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=cls.KEY_LENGTH,
            salt=salt,
            iterations=cls.ITERATIONS,
        )
        derived = kdf.derive(master_password.encode("utf-8"))
        return base64.urlsafe_b64encode(derived)


def get_api_key(
    store: CredentialStore | None = None,
    master_password: str | None = None,
) -> str | None:
    """Get the API key from the best available source.

    Priority:
        1. Environment variable CODE_CHECK_API_KEY
        2. Encrypted credential store (if master_password provided)

    Args:
        store: A CredentialStore instance (created with default path if None).
        master_password: Master password for decrypting from store.

    Returns:
        The API key string, or None if not available.

    Raises:
        CredentialError: If retrieval from store fails.
    """
    # Priority 1: environment variable
    env_key = os.environ.get("CODE_CHECK_API_KEY")
    if env_key:
        return env_key

    # Priority 2: encrypted store
    if master_password is not None:
        if store is None:
            store = CredentialStore()
        if store.exists():
            return store.retrieve(master_password)

    return None
