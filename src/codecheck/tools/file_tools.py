"""File tools — read and write files with precise string replacement."""

from pathlib import Path

from codecheck.tools.base import Tool, ToolResult


class ReadFileTool(Tool):
    """Read a file's content, optionally with line range limits."""

    name = "read_file"
    description = "Read the contents of a file. Supports line range."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read (relative or absolute).",
            },
            "start_line": {
                "type": "integer",
                "description": "First line to read (1-indexed, inclusive).",
            },
            "end_line": {
                "type": "integer",
                "description": "Last line to read (1-indexed, inclusive).",
            },
        },
        "required": ["path"],
    }

    def execute(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolResult:
        file_path = Path(path)
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="latin-1")
            except Exception as e:
                return ToolResult(success=False, error=f"Failed to read {path}: {e}")
        except FileNotFoundError:
            return ToolResult(success=False, error=f"File not found: {path}")
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read {path}: {e}")

        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            total = len(lines)
            start = max(1, (start_line or 1)) - 1
            end = min(total, end_line or total)
            if start >= total:
                return ToolResult(
                    success=False,
                    error=f"start_line {start_line} exceeds file length {total}",
                )
            result = "".join(lines[start:end])
            # Add line number prefix for clarity
            numbered = []
            for i, line in enumerate(result.splitlines(keepends=True), start=start + 1):
                numbered.append(f"{i:6d}|{line}")
            return ToolResult(success=True, data="".join(numbered))

        # Add line numbers to full file
        numbered = []
        for i, line in enumerate(content.splitlines(keepends=True), start=1):
            numbered.append(f"{i:6d}|{line}")
        return ToolResult(success=True, data="".join(numbered))


class WriteFileTool(Tool):
    """Modify a file by exact string replacement (old_string → new_string).

    The replacement is exact — if old_string does not match uniquely,
    the tool returns an error. This prevents accidental corruption.
    """

    name = "write_file"
    description = (
        "Replace an exact string in a file with new content. "
        "The old_string must match exactly and uniquely in the file. "
        "If the match is not unique or not found, the operation fails."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to modify.",
            },
            "old_string": {
                "type": "string",
                "description": "The exact string to replace.",
            },
            "new_string": {
                "type": "string",
                "description": "The replacement string.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }

    def execute(self, path: str, old_string: str, new_string: str) -> ToolResult:
        file_path = Path(path)
        try:
            content = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolResult(success=False, error=f"File not found: {path}")
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read {path}: {e}")

        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                success=False,
                error=f"old_string not found in {path}. The content may have changed "
                "since you last read it. Re-read the file to get the current content.",
            )
        if count > 1:
            return ToolResult(
                success=False,
                error=f"old_string appears {count} times in {path}. "
                "It must be unique. Provide more surrounding context to make it unique.",
            )

        new_content = content.replace(old_string, new_string, 1)
        try:
            file_path.write_text(new_content, encoding="utf-8")
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to write {path}: {e}")

        return ToolResult(
            success=True,
            data=f"Successfully replaced 1 occurrence in {path}.",
        )
