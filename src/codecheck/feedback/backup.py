"""File backup and restore — safe rollback for fix attempts."""

import shutil
from datetime import datetime
from pathlib import Path


def backup_file(file_path: str | Path) -> str:
    """Create a backup of a file before attempting a fix.

    The backup is stored in .codecheck/backups/<timestamp>/<filename>.

    Args:
        file_path: Path to the file to back up.

    Returns:
        The absolute path to the backup file.

    Raises:
        FileNotFoundError: If the source file does not exist.
        OSError: If the backup directory cannot be created or the copy fails.
    """
    source = Path(file_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = Path.cwd() / ".codecheck" / "backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = backup_dir / source.name
    shutil.copy2(source, backup_path)

    return str(backup_path)


def restore_file(backup_path: str | Path) -> None:
    """Restore a file from its backup.

    Args:
        backup_path: Path to the backup file.

    Raises:
        FileNotFoundError: If the backup file does not exist.
        OSError: If the restore operation fails.
    """
    backup = Path(backup_path).resolve()
    if not backup.is_file():
        raise FileNotFoundError(f"Backup file not found: {backup}")

    # The original file path is inferred from the backup filename
    # and the grandparent directory (workspace root)
    backup_dir = backup.parent  # .codecheck/backups/<timestamp>/

    # We need to find the original file. Check the backup filename
    # and search for it in the workspace (or use a stored path).
    # For simplicity, we store the original path as a sibling file.
    metadata_file = backup_dir / f".{backup.name}.origin"
    if metadata_file.is_file():
        original_path = Path(metadata_file.read_text().strip())
    else:
        raise FileNotFoundError(
            f"Cannot determine original file path for backup: {backup}. "
            "The .origin metadata file is missing."
        )

    shutil.copy2(backup, original_path)


def backup_file_with_metadata(file_path: str | Path) -> str:
    """Create a backup and record the original file path.

    Like backup_file(), but also writes a .origin metadata file
    so restore_file() can find the original location.

    Args:
        file_path: Path to the file to back up.

    Returns:
        The absolute path to the backup file.
    """
    source = Path(file_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = Path.cwd() / ".codecheck" / "backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = backup_dir / source.name
    shutil.copy2(source, backup_path)

    # Write origin metadata
    origin_file = backup_dir / f".{source.name}.origin"
    origin_file.write_text(str(source))

    return str(backup_path)
