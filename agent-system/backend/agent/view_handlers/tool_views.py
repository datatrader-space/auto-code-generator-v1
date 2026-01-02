"""
Tool Management API Endpoints

Provides REST API for managing and executing tools.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from pathlib import Path

from agent.tools import get_tool_registry, ToolExecutionContext, ToolPermission, ToolMetadata, ToolParameter
from agent.models import Repository
from agent.tools.loaders.yaml_loader import load_yaml_tools
from agent.tools.builtin.remote_tools import RemoteTool, RemoteToolConfig
import yaml

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def list_tools(request):
    """
    GET /api/tools/

    Returns all registered tools with metadata
    """
    try:
        registry = get_tool_registry()

        # Load YAML tools if not already loaded
        _ensure_yaml_tools_loaded(registry)

        tools = registry.get_all_tools()

        tools_data = []
        for tool_name, metadata in tools.items():
            tools_data.append({
                'name': tool_name,
                'category': metadata.category,
                'description': metadata.description,
                'version': metadata.version,
                'enabled': metadata.enabled,
                'permissions': [p.value for p in metadata.permissions],
                'parameters': [
                    {
                        'name': p.name,
                        'type': p.type,
                        'required': p.required,
                        'default': p.default,
                        'description': p.description,
                        'choices': p.choices
                    }
                    for p in metadata.parameters
                ],
                'examples': metadata.examples,
                'tags': metadata.tags
            })

        # Group by category
        by_category = {}
        for tool in tools_data:
            category = tool['category']
            by_category.setdefault(category, []).append(tool)

        return JsonResponse({
            'tools': tools_data,
            'by_category': by_category,
            'total_count': len(tools_data),
            'categories': list(by_category.keys())
        })

    except Exception as e:
        logger.error(f"Failed to list tools: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_tool_detail(request, tool_name):
    """
    GET /api/tools/<tool_name>/

    Get detailed information about a specific tool
    """
    try:
        registry = get_tool_registry()
        _ensure_yaml_tools_loaded(registry)

        tool = registry.get_tool(tool_name)

        if not tool:
            return JsonResponse({'error': 'Tool not found'}, status=404)

        metadata = tool.get_metadata()

        return JsonResponse({
            'name': metadata.name,
            'category': metadata.category,
            'description': metadata.description,
            'version': metadata.version,
            'enabled': metadata.enabled,
            'permissions': [p.value for p in metadata.permissions],
            'parameters': [
                {
                    'name': p.name,
                    'type': p.type,
                    'required': p.required,
                    'default': p.default,
                    'description': p.description,
                    'choices': p.choices
                }
                for p in metadata.parameters
            ],
            'examples': metadata.examples,
            'tags': metadata.tags
        })

    except Exception as e:
        logger.error(f"Failed to get tool detail: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def execute_tool(request):
    """
    POST /api/tools/execute/

    Execute a tool with parameters

    Body:
    {
        "tool_name": "RUN_COMMAND",
        "parameters": {"command": "pytest tests/"},
        "repository_id": 123,
        "session_id": "optional-session-id"
    }
    """
    try:
        data = json.loads(request.body)
        tool_name = data.get('tool_name')
        parameters = data.get('parameters', {})
        repository_id = data.get('repository_id')
        session_id = data.get('session_id', f"manual_{request.user.id if request.user.is_authenticated else 'anonymous'}")

        if not tool_name:
            return JsonResponse({'error': 'Missing tool_name'}, status=400)

        if not repository_id:
            return JsonResponse({'error': 'Missing repository_id'}, status=400)

        # Get repository
        repository = Repository.objects.filter(id=repository_id).first()
        if not repository:
            return JsonResponse({'error': 'Repository not found'}, status=404)

        # Create execution context
        context = ToolExecutionContext(
            repository=repository,
            user=request.user if request.user.is_authenticated else None,
            session_id=session_id,
            workspace_path=repository.clone_path or "/tmp",
            permissions=[
                ToolPermission.READ,
                ToolPermission.WRITE,
                ToolPermission.EXECUTE
            ],
            trace=[],
            metadata={}
        )

        # Execute tool
        registry = get_tool_registry()
        _ensure_yaml_tools_loaded(registry)

        result = registry.execute(tool_name, parameters, context)

        return JsonResponse({
            'success': result.success,
            'output': result.output,
            'error': result.error,
            'metadata': result.metadata,
            'citations': result.citations,
            'trace': context.trace
        })

    except Exception as e:
        logger.error(f"Tool execution error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_tool_documentation(request):
    """
    GET /api/tools/documentation/

    Generate LLM-ready tool documentation
    """
    try:
        registry = get_tool_registry()
        _ensure_yaml_tools_loaded(registry)

        docs = registry.generate_prompt_documentation()

        return JsonResponse({
            'documentation': docs,
            'format': 'markdown'
        })

    except Exception as e:
        logger.error(f"Failed to generate documentation: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def _ensure_yaml_tools_loaded(registry):
    """Ensure YAML tools are loaded into registry"""
    # Check if we've already loaded YAML tools
    if hasattr(registry, '_yaml_tools_loaded'):
        return

    try:
        from django.conf import settings
        definitions_dir = Path(settings.BASE_DIR) / 'agent' / 'tools' / 'definitions'

        if definitions_dir.exists():
            yaml_tools = load_yaml_tools(definitions_dir)
            for tool in yaml_tools:
                registry.register(tool)
            logger.info(f"Loaded {len(yaml_tools)} YAML tools")

        # Mark as loaded
        registry._yaml_tools_loaded = True

    except Exception as e:
        logger.error(f"Failed to load YAML tools: {e}")


@csrf_exempt
@require_http_methods(["POST"])
def register_remote_tool(request):
    """
    POST /api/tools/register/remote/

    Register an external HTTP service as a tool

    Body:
    {
        "name": "JIRA_CREATE_ISSUE",
        "category": "jira",
        "description": "Create a new Jira issue",
        "version": "1.0.0",
        "endpoint_url": "https://api.example.com/tools/jira/create",
        "method": "POST",
        "timeout": 30,
        "auth_type": "bearer",  // "bearer", "basic", "api_key", null
        "auth_config": {
            "token": "..."  // or {"username": "...", "password": "..."} for basic
        },
        "parameters": [
            {
                "name": "summary",
                "type": "string",
                "required": true,
                "description": "Issue summary"
            }
        ],
        "permissions": ["network"],
        "examples": [...],
        "tags": ["jira", "issue-tracking"]
    }
    """
    try:
        data = json.loads(request.body)

        # Validate required fields
        required_fields = ['name', 'category', 'description', 'endpoint_url']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'Missing required field: {field}'}, status=400)

        # Parse parameters
        parameters = []
        for param_data in data.get('parameters', []):
            parameters.append(ToolParameter(
                name=param_data['name'],
                type=param_data.get('type', 'string'),
                required=param_data.get('required', True),
                default=param_data.get('default'),
                description=param_data.get('description', ''),
                choices=param_data.get('choices')
            ))

        # Parse permissions
        permissions = []
        for perm in data.get('permissions', ['network']):
            try:
                permissions.append(ToolPermission(perm))
            except ValueError:
                logger.warning(f"Invalid permission: {perm}")

        # Create metadata
        metadata = ToolMetadata(
            name=data['name'],
            category=data['category'],
            description=data['description'],
            version=data.get('version', '1.0.0'),
            parameters=parameters,
            permissions=permissions,
            examples=data.get('examples', []),
            tags=data.get('tags', []),
            enabled=data.get('enabled', True)
        )

        # Create remote config
        config = RemoteToolConfig(
            endpoint_url=data['endpoint_url'],
            method=data.get('method', 'POST'),
            timeout=data.get('timeout', 30),
            headers=data.get('headers'),
            auth_type=data.get('auth_type'),
            auth_config=data.get('auth_config')
        )

        # Create and register tool
        tool = RemoteTool(metadata, config)
        registry = get_tool_registry()
        registry.register(tool)

        logger.info(f"Registered remote tool: {data['name']}")

        return JsonResponse({
            'success': True,
            'message': f"Tool {data['name']} registered successfully",
            'tool_name': data['name']
        })

    except Exception as e:
        logger.error(f"Failed to register remote tool: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_yaml_tool(request):
    """
    POST /api/tools/create/yaml/

    Create a new YAML-based tool

    Body:
    {
        "name": "CUSTOM_COMMAND",
        "category": "custom",
        "description": "Run a custom command",
        "yaml_definition": "tool:\\n  name: CUSTOM_COMMAND\\n  ..."
    }
    """
    try:
        data = json.loads(request.body)

        if 'name' not in data or 'yaml_definition' not in data:
            return JsonResponse({'error': 'Missing name or yaml_definition'}, status=400)

        # Parse YAML
        try:
            yaml_data = yaml.safe_load(data['yaml_definition'])
        except yaml.YAMLError as e:
            return JsonResponse({'error': f'Invalid YAML: {str(e)}'}, status=400)

        # Save to definitions directory
        from django.conf import settings
        definitions_dir = Path(settings.BASE_DIR) / 'agent' / 'tools' / 'definitions'
        definitions_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{data['name'].lower()}_custom.yaml"
        filepath = definitions_dir / filename

        with open(filepath, 'w') as f:
            f.write(data['yaml_definition'])

        logger.info(f"Created YAML tool: {data['name']} at {filepath}")

        return JsonResponse({
            'success': True,
            'message': f"Tool {data['name']} created successfully",
            'file_path': str(filepath)
        })

    except Exception as e:
        logger.error(f"Failed to create YAML tool: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def update_tool(request, tool_name):
    """
    POST /api/tools/<tool_name>/update/

    Update tool metadata (enable/disable, etc.)

    Body:
    {
        "enabled": false
    }
    """
    try:
        data = json.loads(request.body)
        registry = get_tool_registry()
        _ensure_yaml_tools_loaded(registry)

        tool = registry.get_tool(tool_name)
        if not tool:
            return JsonResponse({'error': 'Tool not found'}, status=404)

        metadata = tool.get_metadata()

        # Update enabled status
        if 'enabled' in data:
            metadata.enabled = data['enabled']
            logger.info(f"Updated tool {tool_name}: enabled={metadata.enabled}")

        return JsonResponse({
            'success': True,
            'message': f"Tool {tool_name} updated successfully"
        })

    except Exception as e:
        logger.error(f"Failed to update tool: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_tool(request, tool_name):
    """
    DELETE /api/tools/<tool_name>/

    Delete a tool (only custom tools can be deleted)
    """
    try:
        registry = get_tool_registry()
        _ensure_yaml_tools_loaded(registry)

        tool = registry.get_tool(tool_name)
        if not tool:
            return JsonResponse({'error': 'Tool not found'}, status=404)

        # Check if it's a custom tool (has _custom suffix in filename)
        from django.conf import settings
        definitions_dir = Path(settings.BASE_DIR) / 'agent' / 'tools' / 'definitions'
        filename = f"{tool_name.lower()}_custom.yaml"
        filepath = definitions_dir / filename

        if filepath.exists():
            filepath.unlink()
            logger.info(f"Deleted custom tool: {tool_name}")

        # Unregister from registry
        if hasattr(registry, '_tools') and tool_name in registry._tools:
            del registry._tools[tool_name]
            if hasattr(registry, '_metadata_cache') and tool_name in registry._metadata_cache:
                del registry._metadata_cache[tool_name]

        return JsonResponse({
            'success': True,
            'message': f"Tool {tool_name} deleted successfully"
        })

    except Exception as e:
        logger.error(f"Failed to delete tool: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
