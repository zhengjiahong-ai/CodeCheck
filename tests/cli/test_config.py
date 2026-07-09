"""Tests for the config CLI command."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from codecheck.cli.main import main


def test_config_default_shows_status():
    """Running config with no flags shows status."""
    runner = CliRunner()
    result = runner.invoke(main, ["config"])
    # Should succeed (either shows configured or not)
    assert result.exit_code == 0
    assert "API key" in result.output


def test_config_status_flag():
    """Running config --status shows credential status."""
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--status"])
    assert result.exit_code == 0
    assert "API key" in result.output


def test_config_set_key_empty_input():
    """Config --set-key with empty input aborts."""
    runner = CliRunner()
    # Simulate empty input
    with patch("getpass.getpass", return_value=""):
        result = runner.invoke(main, ["config", "--set-key"])
        assert result.exit_code == 1


def test_config_set_key_mismatch():
    """Config --set-key with mismatched confirmation aborts."""
    runner = CliRunner()
    with patch("getpass.getpass", side_effect=["sk-key", "sk-different"]):
        result = runner.invoke(main, ["config", "--set-key"])
        assert result.exit_code == 1


def test_config_set_key_success():
    """Config --set-key with matching keys stores successfully."""
    runner = CliRunner()
    with patch("getpass.getpass", side_effect=[
        "sk-test-key",   # API key
        "sk-test-key",   # API key confirm
        "mypassword",    # Master password
        "mypassword",    # Master password confirm
    ]):
        with patch("codecheck.cli.config_cmd.CredentialStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store_cls.return_value = mock_store
            result = runner.invoke(main, ["config", "--set-key"])
            assert result.exit_code == 0
            mock_store.store.assert_called_once_with("sk-test-key", "mypassword")


def test_config_clear_key_no_stored():
    """Config --clear-key when nothing is stored."""
    runner = CliRunner()
    with patch("codecheck.cli.config_cmd.CredentialStore") as mock_store_cls:
        mock_store = MagicMock()
        mock_store.exists.return_value = False
        mock_store_cls.return_value = mock_store
        result = runner.invoke(main, ["config", "--clear-key"])
        assert result.exit_code == 0
        assert "No stored API key" in result.output


def test_config_clear_key_confirm():
    """Config --clear-key with confirmation."""
    runner = CliRunner()
    with patch("codecheck.cli.config_cmd.CredentialStore") as mock_store_cls:
        mock_store = MagicMock()
        mock_store.exists.return_value = True
        mock_store.clear.return_value = True
        mock_store_cls.return_value = mock_store
        result = runner.invoke(main, ["config", "--clear-key"], input="y\n")
        assert result.exit_code == 0
        mock_store.clear.assert_called_once()


def test_config_clear_key_abort():
    """Config --clear-key with abort (user says no)."""
    runner = CliRunner()
    with patch("codecheck.cli.config_cmd.CredentialStore") as mock_store_cls:
        mock_store = MagicMock()
        mock_store.exists.return_value = True
        mock_store_cls.return_value = mock_store
        result = runner.invoke(main, ["config", "--clear-key"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output


def test_config_multiple_flags_error():
    """Config with multiple flags should error."""
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--status", "--clear-key"])
    assert result.exit_code == 3


def test_config_help():
    """Verify config --help shows all options."""
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--help"])
    assert result.exit_code == 0
    assert "--status" in result.output
    assert "--set-key" in result.output
    assert "--clear-key" in result.output
