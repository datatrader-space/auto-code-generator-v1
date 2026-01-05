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


class HeadTool(BaseTool):
    """Display first lines of file"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="HEAD",
            category="text",
            description="Display first N lines of file",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path"),
                ToolParameter(name="lines", type="int", required=False, default=10, description="Number of lines")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        lines = params.get("lines", 10)
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
            output_lines = content.splitlines()[:lines]
            return ToolResult(success=True, output='\n'.join(output_lines))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TailTool(BaseTool):
    """Display last lines of file"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TAIL",
            category="text",
            description="Display last N lines of file",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path"),
                ToolParameter(name="lines", type="int", required=False, default=10, description="Number of lines")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        lines = params.get("lines", 10)
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
            output_lines = content.splitlines()[-lines:]
            return ToolResult(success=True, output='\n'.join(output_lines))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class DiffTool(BaseTool):
    """Compare two files"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="DIFF",
            category="text",
            description="Compare two files and show differences",
            parameters=[
                ToolParameter(name="file1", type="path", required=True, description="First file"),
                ToolParameter(name="file2", type="path", required=True, description="Second file")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        file1 = params.get("file1")
        file2 = params.get("file2")
        workspace = Path(context.workspace_path)

        try:
            cmd = f'diff "{workspace / file1}" "{workspace / file2}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout if result.stdout else "Files are identical"
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TouchTool(BaseTool):
    """Create empty file or update timestamp"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TOUCH",
            category="filesystem",
            description="Create empty file or update timestamp",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
            return ToolResult(success=True, output=f"Touched: {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class StatTool(BaseTool):
    """Display file statistics"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="STAT",
            category="filesystem",
            description="Display detailed file information",
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
            return ToolResult(success=False, output="", error=f"Path not found: {path}")

        try:
            import os, time
            stat_info = target.stat()
            output = f"""File: {path}
Size: {stat_info.st_size} bytes
Modified: {time.ctime(stat_info.st_mtime)}
Accessed: {time.ctime(stat_info.st_atime)}
Created: {time.ctime(stat_info.st_ctime)}
Mode: {oct(stat_info.st_mode)}
Inode: {stat_info.st_ino}"""
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class DuTool(BaseTool):
    """Disk usage - show directory size"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="DU",
            category="filesystem",
            description="Show disk usage of directory",
            parameters=[
                ToolParameter(name="path", type="path", required=False, default=".", description="Directory path"),
                ToolParameter(name="human_readable", type="bool", required=False, default=True, description="Human readable sizes")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path", ".")
        human = params.get("human_readable", True)
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            flag = "-h" if human else ""
            cmd = f'du {flag} -s "{target}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            # Fallback to Python implementation
            try:
                total = sum(f.stat().st_size for f in target.rglob('*') if f.is_file())
                if human:
                    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                        if total < 1024.0:
                            output = f"{total:.1f} {unit}\t{path}"
                            break
                        total /= 1024.0
                else:
                    output = f"{total}\t{path}"
                return ToolResult(success=True, output=output)
            except Exception as e2:
                return ToolResult(success=False, output="", error=str(e2))


class DfTool(BaseTool):
    """Disk free - show disk space"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="DF",
            category="system",
            description="Display disk space usage",
            parameters=[
                ToolParameter(name="human_readable", type="bool", required=False, default=True, description="Human readable")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        human = params.get("human_readable", True)

        try:
            flag = "-h" if human else ""
            cmd = f"df {flag}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class FreeTool(BaseTool):
    """Display memory usage"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="FREE",
            category="system",
            description="Display memory and swap usage",
            parameters=[
                ToolParameter(name="human_readable", type="bool", required=False, default=True, description="Human readable")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        human = params.get("human_readable", True)

        try:
            flag = "-h" if human else ""
            cmd = f"free {flag}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class UptimeTool(BaseTool):
    """Show system uptime"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="UPTIME",
            category="system",
            description="Show how long system has been running",
            parameters=[],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            result = subprocess.run("uptime", shell=True, capture_output=True, text=True, timeout=5)
            return ToolResult(success=True, output=result.stdout.strip())
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class EnvTool(BaseTool):
    """Display environment variables"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ENV",
            category="system",
            description="Display environment variables",
            parameters=[
                ToolParameter(name="variable", type="string", required=False, default="", description="Specific variable")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        variable = params.get("variable", "")

        try:
            if variable:
                value = os.environ.get(variable, f"Variable '{variable}' not found")
                return ToolResult(success=True, output=f"{variable}={value}")
            else:
                output = "\n".join([f"{k}={v}" for k, v in sorted(os.environ.items())])
                return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class UniqTool(BaseTool):
    """Remove duplicate lines"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="UNIQ",
            category="text",
            description="Remove duplicate consecutive lines",
            parameters=[
                ToolParameter(name="path", type="path", required=True, description="File path"),
                ToolParameter(name="count", type="bool", required=False, default=False, description="Prefix lines with count")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        path = params.get("path")
        count = params.get("count", False)
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
            result = []
            prev_line = None
            line_count = 0

            for line in lines:
                if line == prev_line:
                    line_count += 1
                else:
                    if prev_line is not None:
                        if count:
                            result.append(f"{line_count} {prev_line}")
                        else:
                            result.append(prev_line)
                    prev_line = line
                    line_count = 1

            if prev_line is not None:
                if count:
                    result.append(f"{line_count} {prev_line}")
                else:
                    result.append(prev_line)

            return ToolResult(success=True, output='\n'.join(result))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TrTool(BaseTool):
    """Translate or delete characters"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TR",
            category="text",
            description="Translate or delete characters",
            parameters=[
                ToolParameter(name="text", type="string", required=True, description="Input text"),
                ToolParameter(name="from_chars", type="string", required=True, description="Characters to replace"),
                ToolParameter(name="to_chars", type="string", required=True, description="Replacement characters")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        text = params.get("text")
        from_chars = params.get("from_chars")
        to_chars = params.get("to_chars")

        try:
            trans_table = str.maketrans(from_chars, to_chars)
            output = text.translate(trans_table)
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class Base64EncodeTool(BaseTool):
    """Encode to base64"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="BASE64_ENCODE",
            category="text",
            description="Encode text to base64",
            parameters=[
                ToolParameter(name="text", type="string", required=True, description="Text to encode")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        text = params.get("text")

        try:
            import base64
            encoded = base64.b64encode(text.encode()).decode()
            return ToolResult(success=True, output=encoded)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class Base64DecodeTool(BaseTool):
    """Decode from base64"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="BASE64_DECODE",
            category="text",
            description="Decode base64 to text",
            parameters=[
                ToolParameter(name="encoded", type="string", required=True, description="Base64 encoded text")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        encoded = params.get("encoded")

        try:
            import base64
            decoded = base64.b64decode(encoded.encode()).decode()
            return ToolResult(success=True, output=decoded)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class Md5Tool(BaseTool):
    """Calculate MD5 checksum"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="MD5",
            category="text",
            description="Calculate MD5 checksum of file",
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
            import hashlib
            md5_hash = hashlib.md5()
            with open(target, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            return ToolResult(success=True, output=f"{md5_hash.hexdigest()}  {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class Sha256Tool(BaseTool):
    """Calculate SHA256 checksum"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="SHA256",
            category="text",
            description="Calculate SHA256 checksum of file",
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
            import hashlib
            sha_hash = hashlib.sha256()
            with open(target, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha_hash.update(chunk)
            return ToolResult(success=True, output=f"{sha_hash.hexdigest()}  {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class WhereisTool(BaseTool):
    """Locate binary, source, and manual files"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="WHEREIS",
            category="system",
            description="Locate binary/source/manual for command",
            parameters=[
                ToolParameter(name="command", type="string", required=True, description="Command name")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        command = params.get("command")

        try:
            result = subprocess.run(f"whereis {command}", shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout.strip())
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class WhichTool(BaseTool):
    """Locate a command in PATH"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="WHICH",
            category="system",
            description="Show full path of command",
            parameters=[
                ToolParameter(name="command", type="string", required=True, description="Command name")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        command = params.get("command")

        try:
            result = subprocess.run(f"which {command}", shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout.strip())
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class DateTool(BaseTool):
    """Display or set date/time"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="DATE",
            category="system",
            description="Display current date and time",
            parameters=[
                ToolParameter(name="format", type="string", required=False, default="%Y-%m-%d %H:%M:%S", description="Date format")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        format_str = params.get("format", "%Y-%m-%d %H:%M:%S")

        try:
            from datetime import datetime
            output = datetime.now().strftime(format_str)
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CalTool(BaseTool):
    """Display calendar"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="CAL",
            category="system",
            description="Display calendar",
            parameters=[
                ToolParameter(name="month", type="int", required=False, default=0, description="Month (0 for current)"),
                ToolParameter(name="year", type="int", required=False, default=0, description="Year (0 for current)")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        month = params.get("month", 0)
        year = params.get("year", 0)

        try:
            import calendar
            from datetime import datetime

            if year == 0:
                year = datetime.now().year
            if month == 0:
                month = datetime.now().month

            output = calendar.month(year, month)
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class ArpTool(BaseTool):
    """Display ARP table"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ARP",
            category="network",
            description="Display or modify ARP table",
            parameters=[
                ToolParameter(name="show_all", type="bool", required=False, default=True, description="Show all entries")
            ],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            cmd = "arp -a" if os.name == 'nt' else "arp -a"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class RouteTool(BaseTool):
    """Display routing table"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ROUTE",
            category="network",
            description="Display network routing table",
            parameters=[],
            permissions=[ToolPermission.READ]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            cmd = "route print" if os.name == 'nt' else "route -n"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CurlTool(BaseTool):
    """Transfer data from URL"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="CURL",
            category="network",
            description="Transfer data from or to a server",
            parameters=[
                ToolParameter(name="url", type="string", required=True, description="URL to fetch"),
                ToolParameter(name="method", type="string", required=False, default="GET", description="HTTP method"),
                ToolParameter(name="headers", type="string", required=False, default="", description="HTTP headers")
            ],
            permissions=[ToolPermission.EXECUTE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        url = params.get("url")
        method = params.get("method", "GET")
        headers = params.get("headers", "")

        try:
            header_flags = f'-H "{headers}"' if headers else ""
            cmd = f'curl -X {method} {header_flags} "{url}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return ToolResult(success=result.returncode == 0, output=result.stdout, error=result.stderr if result.stderr else None)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class WgetTool(BaseTool):
    """Download files from web"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="WGET",
            category="network",
            description="Download file from URL to workspace",
            parameters=[
                ToolParameter(name="url", type="string", required=True, description="URL to download"),
                ToolParameter(name="output", type="path", required=False, default="", description="Output filename")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        url = params.get("url")
        output = params.get("output", "")
        workspace = Path(context.workspace_path)

        try:
            output_flag = f'-O "{workspace / output}"' if output else ""
            cmd = f'wget {output_flag} "{url}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=str(workspace))
            return ToolResult(success=result.returncode == 0, output=result.stdout)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TarTool(BaseTool):
    """Archive files with tar"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TAR",
            category="filesystem",
            description="Create or extract tar archives",
            parameters=[
                ToolParameter(name="operation", type="string", required=True, description="Operation: create or extract"),
                ToolParameter(name="archive", type="path", required=True, description="Archive filename"),
                ToolParameter(name="files", type="string", required=False, default="", description="Files to archive (for create)")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        operation = params.get("operation")
        archive = params.get("archive")
        files = params.get("files", "")
        workspace = Path(context.workspace_path)

        try:
            if operation == "create":
                cmd = f'tar -czf "{workspace / archive}" {files}'
            elif operation == "extract":
                cmd = f'tar -xzf "{workspace / archive}" -C "{workspace}"'
            else:
                return ToolResult(success=False, output="", error="Operation must be 'create' or 'extract'")

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=str(workspace))
            return ToolResult(success=result.returncode == 0, output=f"Archive operation completed: {archive}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class ZipTool(BaseTool):
    """Create or extract ZIP archives"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ZIP",
            category="filesystem",
            description="Create or extract ZIP archives",
            parameters=[
                ToolParameter(name="operation", type="string", required=True, description="Operation: create or extract"),
                ToolParameter(name="archive", type="path", required=True, description="Archive filename"),
                ToolParameter(name="files", type="string", required=False, default="", description="Files to archive (for create)")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        operation = params.get("operation")
        archive = params.get("archive")
        files = params.get("files", "")
        workspace = Path(context.workspace_path)

        try:
            import zipfile
            archive_path = workspace / archive

            if operation == "create":
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for file in files.split():
                        file_path = workspace / file
                        if file_path.exists():
                            zf.write(file_path, file)
                return ToolResult(success=True, output=f"Created archive: {archive}")
            elif operation == "extract":
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(workspace)
                return ToolResult(success=True, output=f"Extracted archive: {archive}")
            else:
                return ToolResult(success=False, output="", error="Operation must be 'create' or 'extract'")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class TeeTool(BaseTool):
    """Read from stdin and write to stdout and files"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="TEE",
            category="text",
            description="Write text to file and also output it",
            parameters=[
                ToolParameter(name="text", type="string", required=True, description="Text to write"),
                ToolParameter(name="path", type="path", required=True, description="File path"),
                ToolParameter(name="append", type="bool", required=False, default=False, description="Append mode")
            ],
            permissions=[ToolPermission.WRITE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        text = params.get("text")
        path = params.get("path")
        append = params.get("append", False)
        workspace = Path(context.workspace_path)
        target = (workspace / path).resolve()

        try:
            target.relative_to(workspace)
        except ValueError:
            return ToolResult(success=False, output="", error="Path outside workspace")

        try:
            mode = 'a' if append else 'w'
            with open(target, mode, encoding='utf-8') as f:
                f.write(text)
            return ToolResult(success=True, output=text)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class XargsTool(BaseTool):
    """Build and execute command lines from input"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="XARGS",
            category="shell",
            description="Build and execute command from input list",
            parameters=[
                ToolParameter(name="items", type="string", required=True, description="Space-separated items"),
                ToolParameter(name="command", type="string", required=True, description="Command template (use {} for item)")
            ],
            permissions=[ToolPermission.EXECUTE]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        items = params.get("items", "").split()
        command_template = params.get("command")
        workspace = Path(context.workspace_path)

        results = []
        for item in items:
            try:
                cmd = command_template.replace("{}", item)
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10, cwd=str(workspace))
                results.append(f"[{item}] {result.stdout}")
            except Exception as e:
                results.append(f"[{item}] Error: {str(e)}")

        return ToolResult(success=True, output='\n'.join(results))


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
        TouchTool,
        StatTool,
        DuTool,
        # Search/Text processing
        FindTool,
        GrepTool,
        WcTool,
        SortTool,
        CutTool,
        HeadTool,
        TailTool,
        DiffTool,
        UniqTool,
        TrTool,
        TeeTool,
        XargsTool,
        # Encoding/Hashing
        Base64EncodeTool,
        Base64DecodeTool,
        Md5Tool,
        Sha256Tool,
        # Network tools
        PingTool,
        TracertTool,
        NslookupTool,
        IpconfigTool,
        NetstatTool,
        ArpTool,
        RouteTool,
        CurlTool,
        WgetTool,
        # System tools
        TasklistTool,
        SysteminfoTool,
        HostnameTool,
        WhoamiTool,
        DfTool,
        FreeTool,
        UptimeTool,
        EnvTool,
        WhereisTool,
        WhichTool,
        DateTool,
        CalTool,
        # Archive tools
        TarTool,
        ZipTool,
    ]
