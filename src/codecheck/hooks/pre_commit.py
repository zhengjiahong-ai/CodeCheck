"""Git hook integration — pre-commit hook for CodeCheck."""

import os
import stat
from pathlib import Path

HOOK_SCRIPT = """#!/bin/bash
# CodeCheck pre-commit hook
# Installed by: codecheck install-hook
# Version: 0.1.0

set -e

echo "🔍 CodeCheck: Running pre-commit review..."

# Run CodeCheck on staged changes
codecheck review --diff --staged --fix

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ CodeCheck: No issues found. Commit allowed."
    exit 0
elif [ $EXIT_CODE -eq 2 ]; then
    echo ""
    echo "⚠️  CodeCheck: Some issues could not be auto-fixed and need manual review."
    echo "   You can still commit with: git commit --no-verify"
    echo "   Or fix the issues and try again."
    exit 1
else
    echo ""
    echo "❌ CodeCheck: Issues found. Commit blocked."
    echo "   Run 'codecheck review' for details."
    echo "   Or use: git commit --no-verify"
    exit 1
fi
"""


def get_hook_path(repo_root: str | Path | None = None) -> Path:
    """Get the path to the pre-commit hook file.

    Args:
        repo_root: Path to the git repository root.
                   If None, traverses up from cwd to find .git.

    Returns:
        Path to the pre-commit hook file.

    Raises:
        FileNotFoundError: If not inside a git repository.
    """
    if repo_root is not None:
        git_dir = Path(repo_root) / ".git"
        if not git_dir.exists():
            raise FileNotFoundError(
                f"No git repository found at {repo_root}. "
                "Run 'git init' to initialize a repository, then try again."
            )
    else:
        current = Path.cwd()
        git_dir = None
        while True:
            candidate = current / ".git"
            if candidate.exists():
                git_dir = candidate
                break
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent

    if git_dir is None:
        raise FileNotFoundError(
            "Not inside a git repository. "
            "Run 'git init' to initialize a repository, then try again."
        )

    return git_dir / "hooks" / "pre-commit"


def is_hook_installed(repo_root: str | Path | None = None) -> bool:
    """Check if the CodeCheck pre-commit hook is installed.

    Args:
        repo_root: Path to the git repository root.

    Returns:
        True if the hook is installed and is a CodeCheck hook.
    """
    try:
        hook_path = get_hook_path(repo_root)
    except FileNotFoundError:
        return False

    if not hook_path.is_file():
        return False

    try:
        content = hook_path.read_text()
        return "CodeCheck pre-commit hook" in content
    except OSError:
        return False


def install_hook(repo_root: str | Path | None = None, force: bool = False) -> str:
    """Install the CodeCheck pre-commit hook.

    Args:
        repo_root: Path to the git repository root.
        force: If True, overwrite an existing hook (even if not CodeCheck's).

    Returns:
        Path to the installed hook file.

    Raises:
        FileNotFoundError: If not inside a git repository.
        FileExistsError: If a non-CodeCheck hook already exists and force=False.
        OSError: If the hook file cannot be written.
    """
    hook_path = get_hook_path(repo_root)

    if hook_path.exists():
        existing = hook_path.read_text()
        if "CodeCheck pre-commit hook" in existing:
            if not force:
                return str(hook_path)  # Already installed
        else:
            if not force:
                raise FileExistsError(
                    f"A pre-commit hook already exists at {hook_path}.\n"
                    "Use --force to overwrite it, or back it up manually first."
                )

    # Ensure hooks directory exists
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the hook script
    hook_path.write_text(HOOK_SCRIPT)

    # Make it executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return str(hook_path)


def uninstall_hook(repo_root: str | Path | None = None) -> bool:
    """Uninstall the CodeCheck pre-commit hook.

    Only removes the hook if it is a CodeCheck hook (checks for the marker).

    Args:
        repo_root: Path to the git repository root.

    Returns:
        True if the hook was removed, False if it wasn't installed.

    Raises:
        FileNotFoundError: If not inside a git repository.
        OSError: If the hook file cannot be removed.
    """
    hook_path = get_hook_path(repo_root)

    if not hook_path.is_file():
        return False

    content = hook_path.read_text()
    if "CodeCheck pre-commit hook" not in content:
        return False  # Not our hook, don't touch it

    hook_path.unlink()
    return True


def get_hook_version(repo_root: str | Path | None = None) -> str | None:
    """Get the version of the installed CodeCheck hook.

    Args:
        repo_root: Path to the git repository root.

    Returns:
        The version string, or None if not installed.
    """
    import re

    try:
        hook_path = get_hook_path(repo_root)
    except FileNotFoundError:
        return None

    if not hook_path.is_file():
        return None

    content = hook_path.read_text()
    match = re.search(r"# Version: (\S+)", content)
    return match.group(1) if match else None