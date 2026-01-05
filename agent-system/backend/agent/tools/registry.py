"""
Central registry for all tools

This module provides a global registry that manages local and remote tools,
validates execution, and provides tool documentation.
"""

from typing import Dict, List, Type, Optional, Any
import importlib
import pkgutil
from pathlib import Path
import logging

from .base import BaseTool, ToolMetadata, ToolExecutionContext, ToolResult, ToolPermission

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all tools

    Features:
    - Discovers tools from plugins directory
    - Registers built-in tools
    - Validates tool calls
    - Manages permissions
    - Provides tool documentation
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._metadata_cache: Dict[str, ToolMetadata] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool"""
        metadata = tool.get_metadata()
        tool_name = metadata.name.upper()

        if tool_name in self._tools:
            logger.warning(f"Tool {tool_name} already registered, overwriting")

        self._tools[tool_name] = tool
        self._metadata_cache[tool_name] = metadata

        logger.info(f"Registered tool: {tool_name} ({metadata.category})")

    def register_class(self, tool_class: Type[BaseTool]) -> None:
        """Register a tool by class"""
        tool_instance = tool_class()
        self.register(tool_instance)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self._tools.get(name.upper())

    def get_all_tools(self) -> Dict[str, ToolMetadata]:
        """Get metadata for all registered tools"""
        return self._metadata_cache.copy()

    def get_tools_by_category(self, category: str) -> Dict[str, ToolMetadata]:
        """Get all tools in a category"""
        return {
            name: meta
            for name, meta in self._metadata_cache.items()
            if meta.category == category
        }

    def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolResult:
        """
        Execute a tool with safety checks

        Flow:
        1. Validate tool exists
        2. Check permissions
        3. Validate parameters
        4. Execute tool
        5. Return result with audit trail
        """
        tool_name = tool_name.upper()

        # 1. Check if tool exists
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}"
            )

        # 2. Check if tool is enabled
        metadata = self._metadata_cache[tool_name]
        if not metadata.enabled:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool {tool_name} is disabled"
            )

        # 3. Check permissions
        if not tool.check_permissions(context):
            required_perms = [p.value for p in metadata.permissions]
            return ToolResult(
                success=False,
                output="",
                error=f"Insufficient permissions. Required: {required_perms}"
            )

        # 4. Validate parameters
        valid, error = tool.validate_parameters(params)
        if not valid:
            return ToolResult(
                success=False,
                output="",
                error=f"Parameter validation failed: {error}"
            )

        # 5. Execute tool
        try:
            logger.info(f"Executing tool: {tool_name} with params: {params}")
            result = tool.execute(params, context)

            # Add to trace
            context.trace.append({
                'tool': tool_name,
                'params': params,
                'success': result.success,
                'output_length': len(result.output) if result.output else 0
            })

            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}", exc_info=True)
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution error: {str(e)}"
            )

    def discover_plugins(self, plugins_dir: Path) -> None:
        """
        Auto-discover and register tools from plugins directory

        Looks for modules with classes that extend BaseTool
        """
        if not plugins_dir.exists():
            logger.warning(f"Plugins directory not found: {plugins_dir}")
            return

        # Import all .py files in plugins directory
        for module_info in pkgutil.iter_modules([str(plugins_dir)]):
            module_name = module_info.name

            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    plugins_dir / f"{module_name}.py"
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find all BaseTool subclasses
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    if (isinstance(attr, type) and
                        issubclass(attr, BaseTool) and
                        attr is not BaseTool):

                        self.register_class(attr)
                        logger.info(f"Discovered plugin tool: {attr_name}")

            except Exception as e:
                logger.error(f"Failed to load plugin {module_name}: {e}")

    def generate_prompt_documentation(self) -> str:
        """
        Generate tool documentation for LLM system prompt
        """
        docs = ["# Available Tools\n"]
        docs.append("## CRITICAL: Tool Call Format\n")
        docs.append("**When you need to use a tool, OUTPUT the JSON immediately. Do NOT explain what you will do.**\n\n")
        docs.append("**Correct format:**\n")
        docs.append('```json\n{"name": "WRITE_FILE", "parameters": {"path": "E:/test.txt", "content": "Hello"}}\n```\n\n')
        docs.append("**WRONG - do NOT do this:**\n")
        docs.append('❌ "I will use the WRITE_FILE tool..."\n')
        docs.append('❌ "Let me create the file..."\n')
        docs.append('❌ Explaining before outputting JSON\n\n')
        docs.append("**RIGHT - do this:**\n")
        docs.append('✅ Immediately output: `{"name": "WRITE_FILE", "parameters": {...}}`\n\n')
        docs.append("**Required JSON keys:**\n")
        docs.append('- `"name"` - Tool name (must be uppercase, e.g., "WRITE_FILE")\n')
        docs.append('- `"parameters"` - Parameter object\n\n')

        # Group by category
        categories = {}
        for name, meta in self._metadata_cache.items():
            if meta.enabled:
                categories.setdefault(meta.category, []).append((name, meta))

        for category, tools in sorted(categories.items()):
            docs.append(f"\n## {category.upper()} Tools\n")

            for tool_name, meta in sorted(tools):
                docs.append(f"### {tool_name}")
                docs.append(f"**Description:** {meta.description}")

                if meta.parameters:
                    docs.append("**Parameters:**")
                    for param in meta.parameters:
                        required = "required" if param.required else "optional"
                        default_val = f", default={param.default}" if param.default is not None else ""
                        docs.append(f"  - `{param.name}` ({param.type}, {required}{default_val}): {param.description}")

                if meta.examples:
                    docs.append("**Examples:**")
                    for example in meta.examples:
                        docs.append(f"  {example}")

                docs.append("")

        return "\n".join(docs)


# Global registry singleton
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        _initialize_builtin_tools(_global_registry)
    return _global_registry


def _initialize_builtin_tools(registry: ToolRegistry):
    """Register all built-in tools"""
    try:
        from .builtin import shell_tools, filesystem_tools

        # Register shell tools
        for tool_class in shell_tools.get_all_tools():
            registry.register_class(tool_class)

        # Register filesystem tools
        for tool_class in filesystem_tools.get_all_tools():
            registry.register_class(tool_class)

        from .crs import get_all_tools as get_crs_tools
        # Register CRS tools
        for tool_class in get_crs_tools():
            registry.register_class(tool_class)

        logger.info("Built-in tools initialized successfully")

    except ImportError as e:
        logger.warning(f"Some built-in tools could not be loaded: {e}")
