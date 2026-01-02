"""
Built-in Filesystem Tools

Provides file operations for agents.
"""

from typing import Dict, Any, List
from pathlib import Path

from agent.tools.base import (
    BaseTool, ToolMetadata, ToolParameter, ToolExecutionContext,
    ToolResult, ToolPermission
)


class WriteFileTool(BaseTool):
    """Write content to file"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="WRITE_FILE",
            category="filesystem",
            description="Create or overwrite file with content",
            parameters=[
                ToolParameter(
                    name="path",
                    type="path",
                    required=True,
                    description="File path relative to workspace"
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    required=True,
                    description="File content"
                ),
                ToolParameter(
                    name="create_dirs",
                    type="bool",
                    required=False,
                    default=True,
                    description="Create parent directories if needed"
                )
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path", "")
        content = params.get("content", "")
        create_dirs = params.get("create_dirs", True)

        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        # Security: must be within workspace
        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)

            target.write_text(content, encoding='utf-8')

            return ToolResult(
                success=True,
                output=f"✅ Wrote {len(content)} bytes to {target.relative_to(workspace)}",
                citations=[str(target.relative_to(workspace))]
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Write failed: {e}")


class ReadFileTool(BaseTool):
    """Read file contents"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="READ_FILE",
            category="filesystem",
            description="Read file contents",
            parameters=[
                ToolParameter(
                    name="path",
                    type="path",
                    required=True,
                    description="File path relative to workspace"
                ),
                ToolParameter(
                    name="start_line",
                    type="int",
                    required=False,
                    default=1,
                    description="First line to read"
                ),
                ToolParameter(
                    name="end_line",
                    type="int",
                    required=False,
                    default=None,
                    description="Last line to read (None = all)"
                )
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path", "")
        start_line = params.get("start_line", 1)
        end_line = params.get("end_line")

        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        # Security check
        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        if not target.is_file():
            return ToolResult(success=False, output="", error=f"Not a file: {path}")

        try:
            with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            total_lines = len(lines)
            start_line = max(1, min(start_line, total_lines))
            if end_line is None:
                end_line = total_lines
            else:
                end_line = max(start_line, min(end_line, total_lines))

            output_lines = [f"📄 File: {path}"]
            output_lines.append(f"📍 Lines {start_line}-{end_line} of {total_lines}\n")

            for i in range(start_line - 1, end_line):
                line_num = i + 1
                line_content = lines[i].rstrip()
                output_lines.append(f"{line_num:4d} | {line_content}")

            if end_line < total_lines:
                output_lines.append(f"\n... {total_lines - end_line} more lines")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                citations=[f"{path}:{start_line}-{end_line}"]
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Read failed: {e}")


class AppendFileTool(BaseTool):
    """Append content to file"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="APPEND_FILE",
            category="filesystem",
            description="Append content to existing file",
            parameters=[
                ToolParameter(name="path", type="path", required=True),
                ToolParameter(name="content", type="string", required=True)
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path", "")
        content = params.get("content", "")

        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error="File does not exist")

        try:
            with target.open('a', encoding='utf-8') as f:
                f.write(content)

            return ToolResult(
                success=True,
                output=f"✅ Appended {len(content)} bytes to {target.relative_to(workspace)}"
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Append failed: {e}")


def get_all_tools() -> List[type]:
    """Return all filesystem tools"""
    return [
        WriteFileTool,
        ReadFileTool,
        AppendFileTool
    ]
