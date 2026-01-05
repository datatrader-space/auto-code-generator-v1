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


class DirTool(BaseTool):
    """Windows DIR command - list directory contents"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="DIR",
            category="shell",
            description="List directory contents (Windows-style)",
            parameters=[
                ToolParameter(name="path", type="path", required=False, default=".", description="Directory path")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path", ".")
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")

        try:
            result = subprocess.run(
                f'dir "{target}"' if os.name == 'nt' else f'ls -la "{target}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return ToolResult(success=True, output=result.stdout, error=result.stderr if result.stderr else None)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TypeTool(BaseTool):
    """Windows TYPE command - display file contents"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TYPE",
            category="shell",
            description="Display file contents (Windows TYPE / Unix cat)",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        try:
            content = target.read_text(encoding='utf-8', errors='ignore')
            return ToolResult(success=True, output=content)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CopyTool(BaseTool):
    """Copy files"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="COPY",
            category="shell",
            description="Copy file from source to destination",
            parameters=[
                ToolParameter(name="source", type="path", required=True, description="Source file path"),
                ToolParameter(name="destination", type="path", required=True, description="Destination path")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        source = params.get("source")
        destination = params.get("destination")
        workspace = Path(context.workspace_path)

        src_path = (workspace / source).resolve()
        dst_path = (workspace / destination).resolve()

        try:
            src_path.relative_to(workspace)
            dst_path.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not src_path.exists():
            return ToolResult(success=False, output="", error=f"Source not found: {source}")

        try:
            import shutil
            if src_path.is_file():
                shutil.copy2(src_path, dst_path)
            else:
                shutil.copytree(src_path, dst_path)
            return ToolResult(success=True, output=f"Copied {source} to {destination}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class MoveTool(BaseTool):
    """Move/rename files"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="MOVE",
            category="shell",
            description="Move or rename file/directory",
            parameters=[
                ToolParameter(name="source", type="path", required=True, description="Source path"),
                ToolParameter(name="destination", type="path", required=True, description="Destination path")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        source = params.get("source")
        destination = params.get("destination")
        workspace = Path(context.workspace_path)

        src_path = (workspace / source).resolve()
        dst_path = (workspace / destination).resolve()

        try:
            src_path.relative_to(workspace)
            dst_path.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not src_path.exists():
            return ToolResult(success=False, output="", error=f"Source not found: {source}")

        try:
            import shutil
            shutil.move(str(src_path), str(dst_path))
            return ToolResult(success=True, output=f"Moved {source} to {destination}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class MkdirTool(BaseTool):
    """Create directory"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="MKDIR",
            category="shell",
            description="Create new directory",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="Directory path"),
                ToolParameter(name="parents", type="bool", required=False, default=True, description="Create parent directories")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        parents = params.get("parents", True)
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            target.mkdir(parents=parents, exist_ok=True)
            return ToolResult(success=True, output=f"Created directory: {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class PwdTool(BaseTool):
    """Print working directory"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="PWD",
            category="shell",
            description="Print current working directory",
            parameters=[],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        workspace = Path(context.workspace_path)
        current = context.metadata.get("cwd", workspace)
        return ToolResult(success=True, output=str(current))


class EchoTool(BaseTool):
    """Echo text to output"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ECHO",
            category="shell",
            description="Display text message",
            parameters=[
                ToolParameter(name="text", type="string", required=True, description="Text to display")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        text = params.get("text", "")
        return ToolResult(success=True, output=text)


class FindTool(BaseTool):
    """Search for text in files (grep equivalent)"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="FIND",
            category="shell",
            description="Search for text pattern in files",
            parameters=[
                ToolParameter(name="pattern", type="string", required=True, description="Search pattern"),
                ToolParameter(name="path", type="path", required=False, default=".", description="Search path"),
                ToolParameter(name="recursive", type="bool", required=False, default=True, description="Recursive search")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        pattern = params.get("pattern")
        path = params.get("path", ".")
        recursive = params.get("recursive", True)
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            cmd = f'grep -r "{pattern}" "{target}"' if recursive else f'grep "{pattern}" "{target}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return ToolResult(success=True, output=result.stdout if result.stdout else "No matches found")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class GrepTool(BaseTool):
    """Search for patterns in files using grep"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="GREP",
            category="shell",
            description="Search for patterns in files (advanced)",
            parameters=[
                ToolParameter(name="pattern", type="string", required=True, description="Regex pattern"),
                ToolParameter(name="path", type="path", required=False, default=".", description="File or directory"),
                ToolParameter(name="ignore_case", type="bool", required=False, default=False, description="Case-insensitive"),
                ToolParameter(name="recursive", type="bool", required=False, default=True, description="Recursive search")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        pattern = params.get("pattern")
        path = params.get("path", ".")
        ignore_case = params.get("ignore_case", False)
        recursive = params.get("recursive", True)
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            flags = []
            if ignore_case:
                flags.append("-i")
            if recursive:
                flags.append("-r")

            cmd = f'grep {" ".join(flags)} "{pattern}" "{target}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return ToolResult(success=True, output=result.stdout if result.stdout else "No matches found")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class PingTool(BaseTool):
    """Test network connectivity"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="PING",
            category="network",
            description="Test network connectivity to host",
            parameters=[
                ToolParameter(name="host", type="string", required=True, description="Hostname or IP address"),
                ToolParameter(name="count", type="int", required=False, default=4, description="Number of packets")
            ],
            permissions=[ToolPermission.EXECUTE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        host = params.get("host")
        count = params.get("count", 4)

        try:
            cmd = f"ping -n {count} {host}" if os.name == 'nt' else f"ping -c {count} {host}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return ToolResult(success=result.returncode == 0, output=result.stdout, error=result.stderr if result.stderr else None)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TracertTool(BaseTool):
    """Trace network route to host"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TRACERT",
            category="network",
            description="Trace network route to destination",
            parameters=[
                ToolParameter(name="host", type="string", required=True, description="Hostname or IP address")
            ],
            permissions=[ToolPermission.EXECUTE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        host = params.get("host")

        try:
            cmd = f"tracert {host}" if os.name == 'nt' else f"traceroute {host}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class NslookupTool(BaseTool):
    """DNS lookup"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="NSLOOKUP",
            category="network",
            description="Perform DNS lookup",
            parameters=[
                ToolParameter(name="host", type="string", required=True, description="Hostname to lookup")
            ],
            permissions=[ToolPermission.EXECUTE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        host = params.get("host")

        try:
            result = subprocess.run(f"nslookup {host}", shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class IpconfigTool(BaseTool):
    """Display network configuration"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="IPCONFIG",
            category="network",
            description="Display network interface configuration",
            parameters=[
                ToolParameter(name="all", type="bool", required=False, default=False, description="Show detailed info")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        show_all = params.get("all", False)

        try:
            if os.name == 'nt':
                cmd = "ipconfig /all" if show_all else "ipconfig"
            else:
                cmd = "ifconfig -a" if show_all else "ifconfig"

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class NetstatTool(BaseTool):
    """Display network statistics"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="NETSTAT",
            category="network",
            description="Display network connections and statistics",
            parameters=[
                ToolParameter(name="options", type="string", required=False, default="-an", description="Netstat options")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        options = params.get("options", "-an")

        try:
            result = subprocess.run(f"netstat {options}", shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TasklistTool(BaseTool):
    """List running processes"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TASKLIST",
            category="system",
            description="List all running processes",
            parameters=[
                ToolParameter(name="filter", type="string", required=False, default="", description="Process name filter")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        filter_name = params.get("filter", "")

        try:
            if os.name == 'nt':
                cmd = f'tasklist /FI "IMAGENAME eq {filter_name}*"' if filter_name else "tasklist"
            else:
                cmd = f"ps aux | grep {filter_name}" if filter_name else "ps aux"

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class SysteminfoTool(BaseTool):
    """Display system information"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="SYSTEMINFO",
            category="system",
            description="Display detailed system information",
            parameters=[],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            cmd = "systeminfo" if os.name == 'nt' else "uname -a"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class HostnameTool(BaseTool):
    """Get system hostname"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="HOSTNAME",
            category="system",
            description="Display system hostname",
            parameters=[],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            result = subprocess.run("hostname", shell=True, capture_output=True, text=True, timeout=5)
            return ToolResult(success=True, output=result.stdout.strip())
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class WhoamiTool(BaseTool):
    """Get current user"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="WHOAMI",
            category="system",
            description="Display current user information",
            parameters=[],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            result = subprocess.run("whoami", shell=True, capture_output=True, text=True, timeout=5)
            return ToolResult(success=True, output=result.stdout.strip())
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TreeTool(BaseTool):
    """Display directory tree"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TREE",
            category="filesystem",
            description="Display directory tree structure",
            parameters=[
                ToolParameter(name="path", type="path", required=False, default=".", description="Directory path"),
                ToolParameter(name="depth", type="int", required=False, default=3, description="Maximum depth")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path", ".")
        depth = params.get("depth", 3)
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            if os.name == 'nt':
                cmd = f'tree /F /A "{target}"'
            else:
                cmd = f'tree -L {depth} "{target}"'

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class WcTool(BaseTool):
    """Word count - count lines, words, characters"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="WC",
            category="text",
            description="Count lines, words, and characters in file",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        try:
            result = subprocess.run(f'wc "{target}"', shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            # Fallback to Python implementation
            try:
                content = target.read_text(encoding='utf-8', errors='ignore')
                lines = content.count('\n')
                words = len(content.split())
                chars = len(content)
                output = f"{lines} {words} {chars} {path}"
                return ToolResult(success=True, output=output)
            except Exception as e2:
                return ToolResult(success=False, output="", error=str(e2))


class SortTool(BaseTool):
    """Sort lines in file"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="SORT",
            category="text",
            description="Sort lines in a file",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path"),
                ToolParameter(name="reverse", type="bool", required=False, default=False, description="Reverse sort")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        reverse = params.get("reverse", False)
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        try:
            content = target.read_text(encoding='utf-8', errors='ignore')
            lines = content.splitlines()
            sorted_lines = sorted(lines, reverse=reverse)
            output = '\n'.join(sorted_lines)
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CutTool(BaseTool):
    """Extract columns from file"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="CUT",
            category="text",
            description="Extract columns from delimited file",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path"),
                ToolParameter(name="fields", type="string", required=True, description="Field numbers (e.g., '1,3' or '1-3')"),
                ToolParameter(name="delimiter", type="string", required=False, default="\t", description="Field delimiter")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        fields = params.get("fields")
        delimiter = params.get("delimiter", "\t")
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        if not target.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        try:
            cmd = f'cut -d"{delimiter}" -f{fields} "{target}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


def get_all_tools() -> List[type]:
    """Return all shell tools"""
    return [
        RunCommandTool,
        ChangeDirectoryTool,
        ListDirectoryTool,
        # Windows/File operations
        DirTool,
        TypeTool,
        CopyTool,
        MoveTool,
        MkdirTool,
        PwdTool,
        EchoTool,
        TreeTool,
        # Search/Text processing
        FindTool,
        GrepTool,
        WcTool,
        SortTool,
        CutTool,
        # Network tools
        PingTool,
        TracertTool,
        NslookupTool,
        IpconfigTool,
        NetstatTool,
        # System tools
        TasklistTool,
        SysteminfoTool,
        HostnameTool,
        WhoamiTool,
    ]
