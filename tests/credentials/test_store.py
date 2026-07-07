"""Unit tests for credential storage — encryption, decryption, and clearing.

All tests are DETERMINISTIC — no real API key, no real master password used.
"""

import stat

import pytest

from codecheck.credentials.store import CredentialError, CredentialStore, get_api_key

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    """Create a CredentialStore with a temp file path."""
    return CredentialStore(storage_path=tmp_path / "credentials.enc")


@pytest.fixture
def stored_key(store):
    """A store with a pre-stored key for retrieval tests."""
    store.store("sk-test-api-key-12345", "my-secret-password")
    return store


# ── Store and retrieve ────────────────────────────────────────────────────


class TestStoreAndRetrieve:
    """Test the basic store/retrieve cycle."""

    def test_store_creates_file(self, store):
        store.store("sk-abc", "password123")
        assert store.exists()

    def test_retrieve_returns_original_key(self, store):
        store.store("sk-my-secret-key", "hunter2")
        retrieved = store.retrieve("hunter2")
        assert retrieved == "sk-my-secret-key"

    def test_retrieve_with_wrong_password_fails(self, stored_key):
        with pytest.raises(CredentialError, match="Failed to decrypt"):
            stored_key.retrieve("wrong-password")

    def test_retrieve_when_no_file_raises(self, store):
        with pytest.raises(CredentialError, match="No credentials file"):
            store.retrieve("any-password")

    def test_retrieve_with_empty_password_raises(self, stored_key):
        with pytest.raises(CredentialError, match="Master password must not be empty"):
            stored_key.retrieve("")

    def test_store_with_empty_api_key_raises(self, store):
        with pytest.raises(CredentialError, match="API key must not be empty"):
            store.store("", "password")

    def test_store_with_empty_password_raises(self, store):
        with pytest.raises(CredentialError, match="Master password must not be empty"):
            store.store("sk-abc", "")

    def test_store_overwrites_existing(self, store):
        store.store("sk-old-key", "password1")
        store.store("sk-new-key", "password2")
        assert store.retrieve("password2") == "sk-new-key"
        # Old password should no longer work
        with pytest.raises(CredentialError):
            store.retrieve("password1")


# ── File permissions ──────────────────────────────────────────────────────


class TestFilePermissions:
    """Test that the credentials file has secure permissions."""

    def test_file_permissions_are_600(self, store):
        store.store("sk-test", "password")
        file_mode = store.path.stat().st_mode
        # 0o600 = owner read/write only
        expected_perms = stat.S_IRUSR | stat.S_IWUSR
        actual_perms = file_mode & 0o777
        assert actual_perms == expected_perms, (
            f"Expected permissions 0o600, got {oct(actual_perms)}"
        )

    def test_parent_dir_permissions_are_700(self, store):
        store.store("sk-test", "password")
        dir_mode = store.path.parent.stat().st_mode
        expected_perms = stat.S_IRWXU
        actual_perms = dir_mode & 0o777
        assert actual_perms == expected_perms, (
            f"Expected directory permissions 0o700, got {oct(actual_perms)}"
        )


# ── Clear ─────────────────────────────────────────────────────────────────


class TestClear:
    """Test credential clearing."""

    def test_clear_removes_file(self, stored_key):
        assert stored_key.exists()
        result = stored_key.clear()
        assert result is True
        assert not stored_key.exists()

    def test_clear_when_no_file_returns_false(self, store):
        assert not store.exists()
        result = store.clear()
        assert result is False

    def test_clear_then_retrieve_raises(self, stored_key):
        stored_key.clear()
        with pytest.raises(CredentialError, match="No credentials file"):
            stored_key.retrieve("password")


# ── File content is not plaintext ─────────────────────────────────────────


class TestEncryption:
    """Test that the stored file contains encrypted data, not plaintext."""

    def test_file_content_not_plaintext(self, store):
        api_key = "sk-very-secret-key-98765"
        store.store(api_key, "password")
        content = store.path.read_text()
        # The raw API key should not appear in the file
        assert api_key not in content

    def test_file_has_expected_format(self, store):
        store.store("sk-test", "password")
        content = store.path.read_text().strip()
        # Should have exactly one "$" separator
        assert content.count("$") == 1
        salt_b64, token_b64 = content.split("$")
        import base64

        # Both parts should be valid base64
        base64.b64decode(salt_b64)
        base64.b64decode(token_b64)

    def test_different_passwords_produce_different_ciphertexts(self, store):
        store.store("sk-same-key", "password-A")
        content_a = store.path.read_text()
        store.store("sk-same-key", "password-B")
        content_b = store.path.read_text()
        # Different salt → different ciphertext even for same plaintext
        assert content_a != content_b

    def test_same_key_different_salts(self, store):
        """Storing the same key twice produces different ciphertexts (different salt)."""
        store.store("sk-key", "password")
        content1 = store.path.read_text()
        store.store("sk-key", "password")
        content2 = store.path.read_text()
        # Different salts should produce different ciphertexts
        assert content1 != content2


# ── get_api_key helper ────────────────────────────────────────────────────


class TestGetAPIKey:
    """Test the get_api_key() convenience function."""

    def test_env_var_takes_priority(self, store, monkeypatch):
        monkeypatch.setenv("CODE_CHECK_API_KEY", "sk-from-env")
        store.store("sk-from-store", "password")
        key = get_api_key(store=store, master_password="password")
        assert key == "sk-from-env"

    def test_falls_back_to_store(self, store, monkeypatch):
        monkeypatch.delenv("CODE_CHECK_API_KEY", raising=False)
        store.store("sk-from-store", "password")
        key = get_api_key(store=store, master_password="password")
        assert key == "sk-from-store"

    def test_returns_none_when_no_source(self, store, monkeypatch):
        monkeypatch.delenv("CODE_CHECK_API_KEY", raising=False)
        key = get_api_key(store=store)
        assert key is None

    def test_env_var_without_store(self, monkeypatch):
        monkeypatch.setenv("CODE_CHECK_API_KEY", "sk-env-only")
        key = get_api_key()
        assert key == "sk-env-only"


# ── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_unicode_api_key(self, store):
        """Unicode characters in API keys should work."""
        key = "sk-🔑-test-αβγ"
        store.store(key, "password")
        assert store.retrieve("password") == key

    def test_unicode_password(self, store):
        """Unicode passwords should work."""
        store.store("sk-test", "密码-パスワード-🔒")
        assert store.retrieve("密码-パスワード-🔒") == "sk-test"

    def test_long_api_key(self, store):
        """Long API keys should work."""
        key = "sk-" + "a" * 1000
        store.store(key, "password")
        assert store.retrieve("password") == key

    def test_special_characters_in_password(self, store):
        """Passwords with special characters should work."""
        password = "p@ss!\\n\\t\\r%^&*()"
        store.store("sk-test", password)
        assert store.retrieve(password) == "sk-test"

    def test_custom_path(self, tmp_path):
        """Custom storage path should work."""
        custom_path = tmp_path / "custom" / "subdir" / "creds.enc"
        store = CredentialStore(storage_path=custom_path)
        store.store("sk-test", "password")
        assert custom_path.is_file()
        assert store.retrieve("password") == "sk-test"


# ── Corrupt file handling ─────────────────────────────────────────────────


class TestCorruptFile:
    """Test behavior when the credentials file is corrupted."""

    def test_corrupt_file_missing_separator(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("just-some-garbage-data")
        with pytest.raises(CredentialError, match="corrupted.*separator"):
            store.retrieve("password")

    def test_corrupt_file_invalid_base64(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("not-base64!!!$also-not-base64???")
        with pytest.raises(CredentialError, match="corrupted.*base64"):
            store.retrieve("password")

    def test_corrupt_file_valid_format_wrong_key(self, store):
        """A file with valid format but encrypted with a different key."""
        # Create a valid-looking file with a different salt
        import base64
        import secrets

        from cryptography.fernet import Fernet

        salt = secrets.token_bytes(16)
        # Use a different key derivation
        fake_key = base64.urlsafe_b64encode(secrets.token_bytes(32))
        fernet = Fernet(fake_key)
        token = fernet.encrypt(b"fake-data")
        data = base64.b64encode(salt).decode() + "$" + base64.b64encode(token).decode()
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(data)
        with pytest.raises(CredentialError, match="Failed to decrypt"):
            store.retrieve("password")
