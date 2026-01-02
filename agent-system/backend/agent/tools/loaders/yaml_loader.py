"""
YAML Tool Loader

Loads tool definitions from YAML files and creates executable tools.
Supports Jinja2 templating for command generation.
"""

from pathlib import Path
import yaml
from jinja2 import Template
from typing import Dict, Any, List
import subprocess
import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolParameter, ToolExecutionContext, ToolResult, ToolPermission

logger = logging.getLogger(__name__)


class YAMLTool(BaseTool):
    """
    Tool dynamically created from YAML definition
    """

    def __init__(self, definition: Dict[str, Any]):
        super().__init__()
        self.definition = definition
        self._parse_definition()

    def _parse_definition(self):
        """Parse YAML definition into structured format"""
        tool_def = self.definition.get('tool', {})

        # Parse parameters
        self.params = []
        for param_def in tool_def.get('parameters', []):
            self.params.append(ToolParameter(
                name=param_def['name'],
                type=param_def.get('type', 'string'),
                required=param_def.get('required', True),
                default=param_def.get('default'),
                description=param_def.get('description', ''),
                choices=param_def.get('choices')
            ))

        # Parse execution logic
        self.execution = tool_def.get('execution', {})
        self.execution_type = self.execution.get('type', 'shell_command')

    def get_metadata(self) -> ToolMetadata:
        tool_def = self.definition.get('tool', {})

        return ToolMetadata(
            name=tool_def['name'],
            category=tool_def.get('category', 'custom'),
            description=tool_def.get('description', ''),
            parameters=self.params,
            permissions=[],  # Will add permission system later
            examples=[ex.get('description', '') if isinstance(ex, dict) else str(ex)
                     for ex in tool_def.get('examples', [])],
            version=tool_def.get('version', '1.0'),
            enabled=True,
            tags=tool_def.get('tags', [])
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """
        Execute tool based on execution type
        """
        if self.execution_type == 'shell_command':
            return self._execute_shell_command(params, context)
        elif self.execution_type == 'pipeline':
            return self._execute_pipeline(params, context)
        elif self.execution_type == 'composite':
            return self._execute_composite(params, context)
        elif self.execution_type == 'smart_command':
            return self._execute_smart_command(params, context)
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown execution type: {self.execution_type}"
            )

    def _execute_shell_command(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """Execute a shell command with Jinja2 templating"""
        template_str = self.execution.get('template', '')
        timeout = self.execution.get('timeout', 30)
        working_dir = self.execution.get('working_dir', 'repository_root')

        # Determine working directory
        if working_dir == 'repository_root':
            cwd = context.workspace_path
        elif working_dir == 'current':
            cwd = context.metadata.get('cwd', context.workspace_path)
        else:
            cwd = working_dir

        # Render command template with parameters
        template = Template(template_str)
        command = template.render(**params)

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output = result.stdout
            error = result.stderr if result.returncode != 0 else None

            # Limit output size
            MAX_OUTPUT = 10000
            if len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + f"\n... (truncated, {len(output)} chars total)"

            return ToolResult(
                success=result.returncode == 0,
                output=output,
                error=error,
                metadata={'command': command, 'return_code': result.returncode}
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout}s"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Command execution error: {str(e)}"
            )

    def _execute_pipeline(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """Execute multi-step pipeline"""
        steps = self.execution.get('steps', [])
        step_outputs = {}
        combined_output = []

        for step in steps:
            step_name = step.get('name')

            # Check condition
            condition = step.get('condition')
            if condition:
                template = Template(condition)
                should_run = template.render(**params, **step_outputs)
                if should_run.lower() in ['false', '0', 'no']:
                    continue

            # Execute step
            step_template = Template(step.get('template', ''))
            command = step_template.render(**params, **step_outputs)

            working_dir = step.get('working_dir', context.metadata.get('cwd', context.workspace_path))

            result = subprocess.run(
                command,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                text=True
            )

            # Save output if specified
            if step.get('save_output'):
                step_outputs[step.get('save_output')] = result.stdout.strip()

            combined_output.append(f"[{step_name}] {result.stdout}")

            # Handle errors
            on_error = step.get('on_error', 'fail')
            if result.returncode != 0:
                if on_error == 'fail':
                    return ToolResult(
                        success=False,
                        output="\n".join(combined_output),
                        error=f"Step '{step_name}' failed: {result.stderr}"
                    )
                # continue on error

        # Format final output
        output_template = self.definition.get('tool', {}).get('output', {}).get('format', '')
        if output_template:
            template = Template(output_template)
            final_output = template.render(**params, **step_outputs)
        else:
            final_output = "\n".join(combined_output)

        return ToolResult(
            success=True,
            output=final_output,
            metadata=step_outputs
        )

    def _execute_smart_command(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """
        Smart command execution - detects project type and runs appropriate command
        """
        detect_config = self.execution.get('detect_from_files', [])
        workspace = Path(context.workspace_path)

        for detector in detect_config:
            pattern = detector.get('pattern')
            matches = list(workspace.glob(pattern))

            if matches:
                # Found matching file
                command_template = detector.get('command', '')
                template = Template(command_template)
                command = template.render(**params)

                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=context.workspace_path,
                    capture_output=True,
                    text=True
                )

                return ToolResult(
                    success=result.returncode == 0,
                    output=result.stdout,
                    error=result.stderr if result.returncode != 0 else None,
                    metadata={'detected_file': str(matches[0]), 'command': command}
                )

        return ToolResult(
            success=False,
            output="",
            error="Could not detect project type - no matching configuration files found"
        )

    def _execute_composite(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """Execute composite tool (calls other tools)"""
        # TODO: Implement tool composition
        return ToolResult(
            success=False,
            output="",
            error="Composite tool execution not yet implemented"
        )


def load_yaml_tools(directory: Path) -> List[YAMLTool]:
    """
    Load all YAML tool definitions from directory
    """
    tools = []

    if not directory.exists():
        logger.warning(f"Tool definitions directory not found: {directory}")
        return tools

    for yaml_file in directory.glob('**/*.yaml'):
        try:
            with open(yaml_file, 'r') as f:
                definition = yaml.safe_load(f)

            tool = YAMLTool(definition)
            tools.append(tool)
            logger.info(f"Loaded YAML tool from {yaml_file.name}")

        except Exception as e:
            logger.error(f"Failed to load tool from {yaml_file}: {e}")

    return tools
