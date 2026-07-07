"""Unit tests for git tools (GitDiffTool, GitLogTool, GitBlameTool)."""

import subprocess

import pytest

from codecheck.tools.git_tools import GitBlameTool, GitDiffTool, GitLogTool


def _is_git_repo():
    """Check if we're in a git repo (should be in CI and local dev)."""
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@pytest.mark.skipif(not _is_git_repo(), reason="Not in a git repository")
class TestGitDiffTool:
    """Test GitDiffTool behavior (requires git repo)."""

    def test_git_diff_returns_data(self):
        tool = GitDiffTool()
        result = tool.execute()
        assert result.success
        # In a clean repo, this should say "No changes"
        assert isinstance(result.data, str)

    def test_git_diff_staged(self):
        tool = GitDiffTool()
        result = tool.execute(staged=True)
        assert result.success

    def test_git_diff_with_path(self):
        tool = GitDiffTool()
        result = tool.execute(path=".")
        assert result.success


@pytest.mark.skipif(not _is_git_repo(), reason="Not in a git repository")
class TestGitLogTool:
    """Test GitLogTool behavior (requires git repo)."""

    def test_git_log_returns_data(self):
        tool = GitLogTool()
        result = tool.execute(max_count=3)
        assert result.success
        assert isinstance(result.data, str)

    def test_git_log_with_path(self):
        tool = GitLogTool()
        result = tool.execute(path=".", max_count=1)
        assert result.success


@pytest.mark.skipif(not _is_git_repo(), reason="Not in a git repository")
class TestGitBlameTool:
    """Test GitBlameTool behavior (requires git repo)."""

    def test_git_blame_returns_data(self):
        tool = GitBlameTool()
        result = tool.execute(path="README.md")
        assert result.success
        assert isinstance(result.data, str)

    def test_git_blame_nonexistent_file(self):
        tool = GitBlameTool()
        result = tool.execute(path="nonexistent_file_xyz.txt")
        assert not result.success


class TestGitToolsNotInRepo:
    """Test git tool behavior when NOT in a git repo."""

    def test_git_diff_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = GitDiffTool()
        result = tool.execute()
        assert not result.success
        assert "not in a git repository" in result.error.lower()

    def test_git_log_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = GitLogTool()
        result = tool.execute()
        assert not result.success
        assert "not in a git repository" in result.error.lower()

    def test_git_blame_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = GitBlameTool()
        result = tool.execute(path="README.md")
        assert not result.success
        assert "not in a git repository" in result.error.lower()
