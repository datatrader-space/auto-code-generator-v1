"""
Base classes for the extensible tool framework

This module provides the foundation for creating local and remote tools
that agents can use during execution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ToolPermission(Enum):
    """Permission levels for tools"""
    READ = "read"           # Read-only operations
    WRITE = "write"         # File modifications
    EXECUTE = "execute"     # Command execution
    NETWORK = "network"     # Network access
    ADMIN = "admin"         # System administration


@dataclass
class ToolParameter:
    """Tool parameter definition"""
    name: str
    type: str  # "string", "int", "bool", "path", "choice", "list", "dict"
    required: bool = True
    default: Any = None
    description: str = ""
    choices: Optional[List[str]] = None

    def validate(self, value: Any) -> bool:
        """Validate parameter value"""
        if self.required and value is None:
            return False

        if value is None:
            return True  # Optional parameter not provided

        if self.type == "int":
            try:
                int(value)
                return True
            except (ValueError, TypeError):
                return False

        elif self.type == "bool":
            return isinstance(value, bool) or value in ["true", "false", "True", "False", True, False]

        elif self.type == "choice":
            return value in self.choices if self.choices else True

        elif self.type == "path":
            return isinstance(value, str) and len(value) > 0

        elif self.type == "list":
            return isinstance(value, list)

        elif self.type == "dict":
            return isinstance(value, dict)

        return True  # string type


@dataclass
class ToolMetadata:
    """Metadata about a tool"""
    name: str
    category: str  # "crs", "filesystem", "shell", "git", "network", "custom", "remote"
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    permissions: List[ToolPermission] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    version: str = "1.0"
    enabled: bool = True
    tags: List[str] = field(default_factory=list)


@dataclass
class ToolExecutionContext:
    """Context provided during tool execution"""
    repository: Any  # Repository model
    user: Any  # User model (can be None)
    session_id: str
    workspace_path: str
    permissions: List[ToolPermission]
    trace: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Session-scoped data


@dataclass
class ToolResult:
    """Result of tool execution"""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    citations: List[str] = field(default_factory=list)


class BaseTool(ABC):
    """
    Base class for all tools

    All tools must:
    1. Define metadata (name, description, parameters, permissions)
    2. Implement execute() method
    3. Validate parameters
    4. Return ToolResult
    """

    def __init__(self):
        self._metadata: Optional[ToolMetadata] = None

    @abstractmethod
    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata"""
        pass

    @abstractmethod
    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """
        Execute the tool with given parameters

        Args:
            params: Tool parameters
            context: Execution context (repository, user, permissions)

        Returns:
            ToolResult with output/error
        """
        pass

    def validate_parameters(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate parameters against metadata

        Returns:
            (is_valid, error_message)
        """
        metadata = self.get_metadata()

        for param_def in metadata.parameters:
            if param_def.required and param_def.name not in params:
                return False, f"Missing required parameter: {param_def.name}"

            value = params.get(param_def.name)
            if value is not None and not param_def.validate(value):
                return False, f"Invalid value for {param_def.name}: {value}"

        return True, None

    def check_permissions(self, context: ToolExecutionContext) -> bool:
        """Check if context has required permissions"""
        required = self.get_metadata().permissions
        return all(perm in context.permissions for perm in required)
