"""Tests for git pre-commit hook integration."""

import os
import stat
import tempfile
from pathlib import Path

from click.testing import CliRunner

from codecheck.cli.main import main
from codecheck.hooks.pre_commit import (
    get_hook_path,
    get_hook_version,
    install_hook,
    is_hook_installed,
    uninstall_hook,
)


class TestHookInstall:
    """Tests for hook installation."""

    def test_install_hook_creates_file(self):
        """Installing hook creates the pre-commit file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            path = install_hook(repo_root=repo_root)
            hook_path = Path(path)

            assert hook_path.exists()
            assert hook_path.is_file()
            assert "CodeCheck pre-commit hook" in hook_path.read_text()

    def test_install_hook_makes_executable(self):
        """Installed hook is executable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            path = install_hook(repo_root=repo_root)
            hook_path = Path(path)

            st = os.stat(hook_path)
            assert st.st_mode & stat.S_IEXEC

    def test_install_hook_idempotent(self):
        """Installing hook twice is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            path1 = install_hook(repo_root=repo_root)
            path2 = install_hook(repo_root=repo_root)
            assert path1 == path2

    def test_install_hook_overwrites_existing_non_codecheck(self):
        """With force=True, overwrites a non-CodeCheck hook."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            # Create an existing hook
            hook_path = repo_root / ".git" / "hooks" / "pre-commit"
            hook_path.write_text("#!/bin/bash\necho 'other hook'")
            hook_path.chmod(0o755)

            # Install with force
            path = install_hook(repo_root=repo_root, force=True)
            assert "CodeCheck pre-commit hook" in Path(path).read_text()

    def test_install_hook_raises_existing_non_codecheck(self):
        """Without force, raises if non-CodeCheck hook exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            # Create an existing hook
            hook_path = repo_root / ".git" / "hooks" / "pre-commit"
            hook_path.write_text("#!/bin/bash\necho 'other hook'")
            hook_path.chmod(0o755)

            import pytest
            with pytest.raises(FileExistsError):
                install_hook(repo_root=repo_root)

    def test_get_hook_path_not_in_repo(self):
        """get_hook_path raises FileNotFoundError outside repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import pytest
            with pytest.raises(FileNotFoundError):
                get_hook_path(repo_root=tmpdir)


class TestHookUninstall:
    """Tests for hook uninstallation."""

    def test_uninstall_removes_hook(self):
        """Uninstall removes the CodeCheck hook."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            install_hook(repo_root=repo_root)
            assert is_hook_installed(repo_root=repo_root)

            removed = uninstall_hook(repo_root=repo_root)
            assert removed
            assert not is_hook_installed(repo_root=repo_root)

    def test_uninstall_noop_when_not_installed(self):
        """Uninstall returns False when no hook is installed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            removed = uninstall_hook(repo_root=repo_root)
            assert not removed

    def test_uninstall_does_not_remove_other_hooks(self):
        """Uninstall doesn't touch non-CodeCheck hooks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            hook_path = repo_root / ".git" / "hooks" / "pre-commit"
            hook_path.write_text("#!/bin/bash\necho 'other hook'")
            hook_path.chmod(0o755)

            removed = uninstall_hook(repo_root=repo_root)
            assert not removed
            assert hook_path.exists()


class TestHookVersion:
    """Tests for hook version tracking."""

    def test_version_after_install(self):
        """Hook version is tracked after install."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            install_hook(repo_root=repo_root)
            version = get_hook_version(repo_root=repo_root)
            assert version == "0.1.0"

    def test_version_not_installed(self):
        """Version is None when not installed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()

            version = get_hook_version(repo_root=repo_root)
            assert version is None


class TestHookCLI:
    """Tests for the CLI hook commands."""

    def test_install_hook_cli(self):
        """Install hook via CLI."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            import os as _os
            original_cwd = _os.getcwd()
            try:
                _os.chdir(str(repo_root))
                result = runner.invoke(main, ["install-hook"])
                assert result.exit_code == 0
                assert "installed" in result.output.lower()
            finally:
                _os.chdir(original_cwd)

    def test_install_hook_cli_not_in_repo(self):
        """Install hook via CLI outside repo fails."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            import os as _os
            original_cwd = _os.getcwd()
            try:
                _os.chdir(tmpdir)
                result = runner.invoke(main, ["install-hook"])
                assert result.exit_code == 1
            finally:
                _os.chdir(original_cwd)

    def test_uninstall_hook_cli_not_installed(self):
        """Uninstall via CLI when not installed."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            import os as _os
            original_cwd = _os.getcwd()
            try:
                _os.chdir(str(repo_root))
                result = runner.invoke(main, ["uninstall-hook"])
                assert result.exit_code == 0
                assert "No CodeCheck" in result.output
            finally:
                _os.chdir(original_cwd)

    def test_install_and_uninstall_cli(self):
        """Full install and uninstall cycle via CLI."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            (repo_root / ".git" / "hooks").mkdir(parents=True)

            import os as _os
            original_cwd = _os.getcwd()
            try:
                _os.chdir(str(repo_root))
                # Install
                result = runner.invoke(main, ["install-hook"])
                assert result.exit_code == 0

                # Uninstall
                result = runner.invoke(main, ["uninstall-hook"])
                assert result.exit_code == 0
                assert "removed" in result.output.lower()
            finally:
                _os.chdir(original_cwd)

    def test_install_hook_help(self):
        """Verify install-hook --help."""
        runner = CliRunner()
        result = runner.invoke(main, ["install-hook", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output