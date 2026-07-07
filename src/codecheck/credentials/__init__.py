"""CodeCheck credential management — encrypted API key storage."""

from codecheck.credentials.prompt import (
    get_credential_status,
    prompt_clear_key,
    prompt_master_password,
    prompt_set_api_key,
)
from codecheck.credentials.store import CredentialError, CredentialStore, get_api_key

__all__ = [
    "CredentialError",
    "CredentialStore",
    "get_api_key",
    "get_credential_status",
    "prompt_clear_key",
    "prompt_master_password",
    "prompt_set_api_key",
]
