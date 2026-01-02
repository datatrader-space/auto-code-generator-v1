"""
Built-in Shell Tools

Provides shell command execution tools for agents.
"""

from typing import Dict, Any, List
import subprocess
import os
from pathlib import Path

from agent.tools.base import (
    BaseTool, ToolMetadata, ToolParameter, ToolExecutionContext,
    ToolResult, ToolPermission
)


class RunCommandTool(BaseTool):
    """
    Execute shell command in repository workspace
    """

    BLACKLISTED_COMMANDS = {
        'rm -rf /', 'dd', 'mkfs', 'fdisk',
        'format', ':(){:|:&};:'
    }

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="RUN_COMMAND",
            category="shell",
            description="Execute a shell command in the repository workspace",
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    required=True,
                    description="Shell command to execute"
                ),
                ToolParameter(
                    name="timeout",
                    type="int",
                    required=False,
                    default=30,
                    description="Timeout in seconds (max 300)"
                )
            ],
            permissions=[ToolPermission.EXECUTE],
            examples=[
                '{"name":"RUN_COMMAND","parameters":{"command":"pytest tests/"}}',
                '{"name":"RUN_COMMAND","parameters":{"command":"python manage.py check"}}'
            ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        command = params.get("command", "")
        timeout = min(int(params.get("timeout", 30)), 300)  # Max 5 minutes

        # Security check: blacklist dangerous commands
        if any(dangerous in command.lower() for dangerous in self.BLACKLISTED_COMMANDS):
            return ToolResult(
                success=False,
                output="",
                error="Command contains blacklisted pattern (security violation)"
            )

        try:
            # Run in repository workspace
            workspace = Path(context.workspace_path)

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "CWD": str(workspace)}
            )

            output = result.stdout
            error = result.stderr
            success = result.returncode == 0

            # Limit output size
            MAX_OUTPUT = 10000
            if len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + f"\n... (truncated, {len(output)} chars total)"

            formatted_output = f"$ {command}\n\n{output}"
            if error:
                formatted_output += f"\nSTDERR:\n{error}"

            return ToolResult(
                success=success,
                output=formatted_output,
                error=None if success else f"Command failed with code {result.returncode}",
                metadata={
                    "return_code": result.returncode,
                    "command": command,
                    "duration_s": timeout
                }
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Command execution error: {str(e)}"
            )


class ChangeDirectoryTool(BaseTool):
    """Change working directory within workspace"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="CD",
            category="shell",
            description="Change current working directory (session-scoped)",
            parameters=[
                ToolParameter(
                    name="path",
                    type="path",
                    required=True,
                    description="Directory path (relative to workspace)"
                )
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        target_path = params.get("path", "")
        workspace = Path(context.workspace_path)

        # Resolve path relative to workspace
        if target_path.startswith('/'):
            new_path = Path(target_path)
        else:
            # Get current directory from context (stored per-session)
            current = context.metadata.get("cwd", workspace)
            new_path = (Path(current) / target_path).resolve()

        # Security: must stay within workspace
        try:
            new_path.relative_to(workspace)
        except ValueError:
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot navigate outside workspace: {new_path}"
            )

        if not new_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Directory does not exist: {new_path}"
            )

        if not new_path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"Not a directory: {new_path}"
            )

        # Update session context
        context.metadata["cwd"] = str(new_path)

        return ToolResult(
            success=True,
            output=f"Changed directory to: {new_path.relative_to(workspace)}",
            metadata={"cwd": str(new_path)}
        )


class ListDirectoryTool(BaseTool):
    """List files and directories"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="LS",
            category="shell",
            description="List files in directory",
            parameters=[
                ToolParameter(
                    name="path",
                    type="path",
                    required=False,
                    default=".",
                    description="Directory to list (default: current)"
                ),
                ToolParameter(
                    name="show_hidden",
                    type="bool",
                    required=False,
                    default=False,
                    description="Show hidden files"
                )
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path", ".")
        show_hidden = params.get("show_hidden", False)

        workspace = Path(context.workspace_path)
        current = context.metadata.get("cwd", workspace)
        target = (Path(current) / path).resolve()

        # Security check
        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")

        entries = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith('.'):
                continue

            icon = "📁" if item.is_dir() else "📄"
            size = item.stat().st_size if item.is_file() else ""
            entries.append(f"{icon} {item.name} {size}")

        output = f"Directory: {target.relative_to(workspace)}\n\n"
        output += "\n".join(entries) if entries else "(empty)"

        return ToolResult(success=True, output=output)


def get_all_tools() -> List[type]:
    """Return all shell tools"""
    return [
        RunCommandTool,
        ChangeDirectoryTool,
        ListDirectoryTool
    ]
