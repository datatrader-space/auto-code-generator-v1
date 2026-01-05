"""
Service Management API Endpoints

Provides REST API for registering and managing external services and their actions.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify
import json
import logging

from agent.models import RemoteService, ServiceAction, ServiceKnowledgeEntry
from agent.tools import get_tool_registry, ToolMetadata, ToolParameter, ToolPermission
from agent.tools.builtin.remote_tools import RemoteTool, RemoteToolConfig
from agent.tools.ai_designer import APISpecParser, ActionCategorizer

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def list_services(request):
    """
    GET /api/services/

    List all registered services for the current user
    """
    try:
        user = request.user if request.user.is_authenticated else None
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        services = RemoteService.objects.filter(created_by=user)

        services_data = []
        for service in services:
            services_data.append({
                'id': service.id,
                'name': service.name,
                'slug': service.slug,
                'description': service.description,
                'category': service.category,
                'icon': service.icon,
                'base_url': service.base_url,
                'auth_type': service.auth_type,
                'enabled': service.enabled,
                'total_actions': service.total_actions,
                'enabled_actions': service.enabled_actions,
                'created_at': service.created_at.isoformat(),
                'last_used_at': service.last_used_at.isoformat() if service.last_used_at else None
            })

        return JsonResponse({
            'services': services_data,
            'total_count': len(services_data)
        })

    except Exception as e:
        logger.error(f"Failed to list services: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_service_detail(request, service_id):
    """
    GET /api/services/<service_id>/

    Get detailed information about a service including all actions
    """
    try:
        user = request.user if request.user.is_authenticated else None
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        service = RemoteService.objects.filter(id=service_id, created_by=user).first()
        if not service:
            return JsonResponse({'error': 'Service not found'}, status=404)

        # Get all actions grouped by action_group
        actions = ServiceAction.objects.filter(service=service)

        actions_by_group = {}
        for action in actions:
            group = action.action_group
            if group not in actions_by_group:
                actions_by_group[group] = []

            actions_by_group[group].append({
                'id': action.id,
                'name': action.name,
                'tool_name': action.tool_name,
                'description': action.description,
                'endpoint_path': action.endpoint_path,
                'http_method': action.http_method,
                'execution_pattern': action.execution_pattern,
                'enabled': action.enabled,
                'parameters': action.parameters,
                'execution_count': action.execution_count,
                'success_count': action.success_count,
                'failure_count': action.failure_count,
                'average_execution_time': action.average_execution_time
            })

        # Get knowledge entries
        knowledge_entries = ServiceKnowledgeEntry.objects.filter(service=service)[:10]
        knowledge_data = [{
            'id': entry.id,
            'entry_type': entry.entry_type,
            'title': entry.title,
            'content': entry.content[:500],  # Truncate for listing
            'source_url': entry.source_url,
            'tags': entry.tags
        } for entry in knowledge_entries]

        return JsonResponse({
            'id': service.id,
            'name': service.name,
            'slug': service.slug,
            'description': service.description,
            'category': service.category,
            'icon': service.icon,
            'base_url': service.base_url,
            'auth_type': service.auth_type,
            'api_spec_url': service.api_spec_url,
            'api_docs_url': service.api_docs_url,
            'enabled': service.enabled,
            'total_actions': service.total_actions,
            'enabled_actions': service.enabled_actions,
            'actions_by_group': actions_by_group,
            'knowledge_entries': knowledge_data,
            'created_at': service.created_at.isoformat()
        })

    except Exception as e:
        logger.error(f"Failed to get service detail: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_service(request):
    """
    POST /api/services/create/

    Create a new service with selected actions

    Body:
    {
        "name": "Jira",
        "description": "Project management tool",
        "category": "project_management",
        "base_url": "https://mycompany.atlassian.net",
        "auth_type": "bearer",
        "auth_config": {"token": "..."},
        "api_spec_url": "https://...",
        "enabled_action_groups": ["issues", "comments"]
    }
    """
    try:
        user = request.user if request.user.is_authenticated else None
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        data = json.loads(request.body)

        # Validate required fields
        required_fields = ['name', 'description', 'base_url', 'auth_type']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'Missing required field: {field}'}, status=400)

        # Create slug
        slug = slugify(data['name'])

        # Check if service already exists
        existing = RemoteService.objects.filter(created_by=user, slug=slug).first()
        if existing:
            return JsonResponse({'error': f'Service with slug "{slug}" already exists'}, status=400)

        # Create service
        service = RemoteService.objects.create(
            name=data['name'],
            slug=slug,
            description=data['description'],
            category=data.get('category', ''),
            icon=data.get('icon', ''),
            base_url=data['base_url'],
            auth_type=data['auth_type'],
            auth_config=data.get('auth_config', {}),  # Should be encrypted in production
            discovery_method=data.get('discovery_method', 'manual'),
            api_spec_url=data.get('api_spec_url'),
            api_docs_url=data.get('api_docs_url'),
            knowledge_context=data.get('knowledge_context', ''),
            examples=data.get('examples', []),
            created_by=user
        )

        logger.info(f"Created service: {service.name} (ID: {service.id})")

        return JsonResponse({
            'success': True,
            'service_id': service.id,
            'slug': service.slug,
            'message': f'Service "{service.name}" created successfully'
        })

    except Exception as e:
        logger.error(f"Failed to create service: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_service_actions(request, service_id):
    """
    POST /api/services/<service_id>/actions/create/

    Create actions for a service

    Body:
    {
        "actions": [
            {
                "name": "CREATE_ISSUE",
                "action_group": "issues",
                "description": "Create a new issue",
                "endpoint_path": "/rest/api/3/issue",
                "http_method": "POST",
                "parameters": [...],
                "execution_pattern": "simple"
            }
        ]
    }
    """
    try:
        user = request.user if request.user.is_authenticated else None
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        service = RemoteService.objects.filter(id=service_id, created_by=user).first()
        if not service:
            return JsonResponse({'error': 'Service not found'}, status=404)

        data = json.loads(request.body)
        actions_data = data.get('actions', [])

        created_actions = []
        registry = get_tool_registry()

        for action_data in actions_data:
            # Create tool name
            tool_name = f"{service.slug.upper()}_{action_data['name']}"

            # Check if action already exists
            existing = ServiceAction.objects.filter(service=service, name=action_data['name']).first()
            if existing:
                logger.warning(f"Action {action_data['name']} already exists for service {service.name}")
                continue

            # Create action
            action = ServiceAction.objects.create(
                service=service,
                name=action_data['name'],
                action_group=action_data.get('action_group', 'general'),
                description=action_data['description'],
                endpoint_path=action_data['endpoint_path'],
                http_method=action_data.get('http_method', 'POST'),
                parameters=action_data.get('parameters', []),
                request_body_schema=action_data.get('request_body_schema'),
                response_schema=action_data.get('response_schema'),
                execution_pattern=action_data.get('execution_pattern', 'simple'),
                polling_config=action_data.get('polling_config'),
                webhook_config=action_data.get('webhook_config'),
                tool_name=tool_name,
                enabled=action_data.get('enabled', True),
                version=action_data.get('version', '1.0.0')
            )

            # Register as tool in the tool registry
            _register_action_as_tool(service, action, registry)

            created_actions.append(tool_name)
            logger.info(f"Created action: {tool_name}")

        # Update service stats
        service.total_actions = ServiceAction.objects.filter(service=service).count()
        service.enabled_actions = ServiceAction.objects.filter(service=service, enabled=True).count()
        service.save()

        return JsonResponse({
            'success': True,
            'created_actions': created_actions,
            'total_created': len(created_actions)
        })

    except Exception as e:
        logger.error(f"Failed to create actions: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def update_service(request, service_id):
    """
    POST /api/services/<service_id>/update/

    Update service configuration
    """
    try:
        user = request.user if request.user.is_authenticated else None
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        service = RemoteService.objects.filter(id=service_id, created_by=user).first()
        if not service:
            return JsonResponse({'error': 'Service not found'}, status=404)

        data = json.loads(request.body)

        # Update fields
        if 'enabled' in data:
            service.enabled = data['enabled']
        if 'base_url' in data:
            service.base_url = data['base_url']
        if 'auth_config' in data:
            service.auth_config = data['auth_config']
        if 'description' in data:
            service.description = data['description']

        service.save()

        return JsonResponse({
            'success': True,
            'message': 'Service updated successfully'
        })

    except Exception as e:
        logger.error(f"Failed to update service: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_service(request, service_id):
    """
    DELETE /api/services/<service_id>/

    Delete a service and all its actions
    """
    try:
        user = request.user if request.user.is_authenticated else None
        if not user:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        service = RemoteService.objects.filter(id=service_id, created_by=user).first()
        if not service:
            return JsonResponse({'error': 'Service not found'}, status=404)

        service_name = service.name
        service.delete()  # Cascade delete will handle actions and knowledge entries

        return JsonResponse({
            'success': True,
            'message': f'Service "{service_name}" deleted successfully'
        })

    except Exception as e:
        logger.error(f"Failed to delete service: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def _register_action_as_tool(service: RemoteService, action: ServiceAction, registry):
    """Register a service action as a tool in the tool registry"""

    # Build full endpoint URL
    endpoint_url = service.base_url.rstrip('/') + '/' + action.endpoint_path.lstrip('/')

    # Convert parameters to ToolParameter objects
    parameters = []
    for param in action.parameters:
        parameters.append(ToolParameter(
            name=param['name'],
            type=param.get('type', 'string'),
            required=param.get('required', False),
            default=param.get('default'),
            description=param.get('description', ''),
            choices=param.get('choices')
        ))

    # Create tool metadata
    metadata = ToolMetadata(
        name=action.tool_name,
        category=service.slug,
        description=action.description,
        version=action.version,
        parameters=parameters,
        permissions=[ToolPermission.NETWORK],
        examples=[],
        tags=[service.slug, action.action_group],
        enabled=action.enabled
    )

    # Create remote tool config
    config = RemoteToolConfig(
        endpoint_url=endpoint_url,
        method=action.http_method,
        timeout=30,
        auth_type=service.auth_type,
        auth_config=service.auth_config
    )

    # Create and register tool
    tool = RemoteTool(metadata, config)
    registry.register(tool)

    logger.info(f"Registered tool: {action.tool_name}")


@csrf_exempt
@require_http_methods(["POST"])
def discover_actions(request):
    """
    POST /api/services/discover/

    Discover actions from an API specification URL or file

    Body:
    {
        "discovery_method": "openapi|postman|graphql|html_docs",
        "api_spec_url": "https://api.example.com/openapi.json",  // for openapi, graphql, html_docs
        "postman_collection": {...},  // for postman (JSON content)
        "service_type": "jira"  // optional, for better categorization
    }

    Response:
    {
        "total_actions": 150,
        "base_url": "https://api.example.com",
        "auth": {...},
        "categories": {
            "issues": {
                "name": "Issues",
                "count": 15,
                "actions": [...]
            }
        },
        "recommended_categories": ["issues", "comments"]
    }
    """
    try:
        data = json.loads(request.body)

        discovery_method = data.get('discovery_method', 'openapi')
        service_type = data.get('service_type', '')

        # Parse based on discovery method
        parser = APISpecParser()

        if discovery_method == 'postman':
            # Handle Postman collection (could be URL or JSON data)
            print(data)
            postman_collection = data.get('postman_collection')
            api_spec_url = data.get('api_spec_url')

            if postman_collection:
                # Parse JSON collection directly
                spec = parser.parse_postman_collection(postman_collection)
            elif api_spec_url:
                # Fetch from URL
                spec = parser.parse_postman_collection(api_spec_url)
            else:
                return JsonResponse({'error': 'Missing postman_collection or api_spec_url'}, status=400)

        elif discovery_method in ['openapi', 'graphql', 'html_docs']:
            api_spec_url = data.get('api_spec_url')
            if not api_spec_url:
                return JsonResponse({'error': 'Missing api_spec_url'}, status=400)

            spec = parser._fetch_and_parse_sync(api_spec_url, discovery_method=discovery_method)

        else:
            return JsonResponse({'error': f'Invalid discovery_method: {discovery_method}'}, status=400)

        # Categorize actions
        categorizer = ActionCategorizer()
        categorized = categorizer.categorize(spec, service_type=service_type)

        return JsonResponse({
            'total_actions': categorized['total'],
            'base_url': spec['base_url'],
            'auth': spec['auth'],
            'categories': categorized['categories'],
            'recommended_categories': categorized['recommended'],
            'discovery_method': discovery_method,
            'note': spec.get('note', '')
        })

    except Exception as e:
        logger.error(f"Failed to discover actions: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
