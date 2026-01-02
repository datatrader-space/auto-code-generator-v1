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

from agent.tools import get_tool_registry, ToolExecutionContext, ToolPermission
from agent.models import Repository
from agent.tools.loaders.yaml_loader import load_yaml_tools

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
