"""
API Specification Parser

Parses OpenAPI/Swagger specifications and discovers available actions
"""

import requests
import yaml
import json
import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class APISpecParser:
    """Parse OpenAPI/Swagger specs and generate action configs"""

    @staticmethod
    async def fetch_and_parse(spec_url: str) -> Dict:
        """
        Fetch and parse API specification

        Returns a dict with:
        - base_url: str
        - auth: dict
        - actions: list of action configs
        - total_count: int
        """
        try:
            # Synchronous version (async for future enhancement)
            return APISpecParser._fetch_and_parse_sync(spec_url)
        except Exception as e:
            logger.error(f"Failed to fetch/parse API spec: {e}", exc_info=True)
            raise

    @staticmethod
    def _fetch_and_parse_sync(spec_url: str) -> Dict:
        """Synchronous version of fetch_and_parse"""

        # Try OpenAPI/Swagger first
        if 'swagger' in spec_url.lower() or 'openapi' in spec_url.lower() or spec_url.endswith('.json') or spec_url.endswith('.yaml'):
            return APISpecParser.parse_openapi(spec_url)

        # Try Google API Discovery
        elif 'discovery' in spec_url.lower() or 'googleapis.com' in spec_url.lower():
            return APISpecParser.parse_google_discovery(spec_url)

        # Default to OpenAPI parser
        else:
            return APISpecParser.parse_openapi(spec_url)

    @staticmethod
    def parse_openapi(spec_url: str) -> Dict:
        """Parse OpenAPI 3.0 or Swagger 2.0 spec"""

        try:
            # Fetch spec
            response = requests.get(spec_url, timeout=30)
            response.raise_for_status()

            # Parse based on content type
            if spec_url.endswith('.yaml') or spec_url.endswith('.yml') or 'yaml' in response.headers.get('content-type', ''):
                spec = yaml.safe_load(response.text)
            else:
                spec = response.json()

            # Extract base URL
            base_url = ''
            if 'servers' in spec and len(spec['servers']) > 0:
                # OpenAPI 3.0
                base_url = spec['servers'][0]['url']
            elif 'host' in spec:
                # Swagger 2.0
                scheme = spec.get('schemes', ['https'])[0]
                base_path = spec.get('basePath', '')
                base_url = f"{scheme}://{spec['host']}{base_path}"

            # Parse paths and operations
            actions = []
            for path, path_item in spec.get('paths', {}).items():
                for method, operation in path_item.items():
                    if method.lower() in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:

                        # Generate action name from operationId or path
                        if 'operationId' in operation:
                            action_name = operation['operationId'].replace('-', '_').replace('.', '_').upper()
                        else:
                            # Generate from method and path
                            path_parts = [p for p in path.split('/') if p and not p.startswith('{')]
                            action_name = f"{method.upper()}_{'_'.join(path_parts)}".upper()

                        action = {
                            'name': action_name,
                            'description': operation.get('summary', operation.get('description', f'{method.upper()} {path}')),
                            'endpoint_path': path,
                            'full_url': urljoin(base_url, path) if base_url else path,
                            'http_method': method.upper(),
                            'parameters': [],
                            'request_body_schema': None,
                            'response_schema': None,
                            'tags': operation.get('tags', []),
                            'execution_pattern': 'simple'
                        }

                        # Extract parameters
                        for param in operation.get('parameters', []):
                            param_def = {
                                'name': param['name'],
                                'location': param.get('in', 'query'),  # query, path, header, cookie
                                'type': APISpecParser._get_param_type(param.get('schema', param)),
                                'required': param.get('required', False),
                                'description': param.get('description', '')
                            }

                            # Extract enum/choices
                            schema = param.get('schema', param)
                            if 'enum' in schema:
                                param_def['choices'] = schema['enum']

                            action['parameters'].append(param_def)

                        # Extract request body (OpenAPI 3.0)
                        if 'requestBody' in operation:
                            request_body = operation['requestBody']
                            content = request_body.get('content', {})

                            if 'application/json' in content:
                                schema = content['application/json'].get('schema', {})
                                action['request_body_schema'] = schema

                                # Extract properties as parameters
                                if 'properties' in schema:
                                    required_props = schema.get('required', [])
                                    for prop_name, prop_schema in schema['properties'].items():
                                        action['parameters'].append({
                                            'name': prop_name,
                                            'location': 'body',
                                            'type': prop_schema.get('type', 'string'),
                                            'required': prop_name in required_props,
                                            'description': prop_schema.get('description', '')
                                        })

                        # Extract response schema
                        responses = operation.get('responses', {})
                        if '200' in responses or '201' in responses:
                            success_response = responses.get('200', responses.get('201', {}))
                            if 'content' in success_response:
                                content = success_response['content']
                                if 'application/json' in content:
                                    action['response_schema'] = content['application/json'].get('schema')

                        # Detect execution pattern
                        action['execution_pattern'] = APISpecParser._detect_execution_pattern(operation, responses)

                        actions.append(action)

            # Extract auth info
            auth_info = APISpecParser._extract_auth_info(spec)

            return {
                'base_url': base_url,
                'auth': auth_info,
                'actions': actions,
                'total_count': len(actions)
            }

        except Exception as e:
            logger.error(f"Failed to parse OpenAPI spec: {e}", exc_info=True)
            raise

    @staticmethod
    def parse_google_discovery(spec_url: str) -> Dict:
        """Parse Google API Discovery document"""

        try:
            response = requests.get(spec_url, timeout=30)
            response.raise_for_status()
            spec = response.json()

            base_url = spec.get('baseUrl', spec.get('rootUrl', ''))
            actions = []

            # Parse resources and methods
            def parse_resource(resource_name, resource_def, parent_path=''):
                methods = resource_def.get('methods', {})

                for method_name, method_def in methods.items():
                    action_name = f"{method_name}".upper()

                    # Get path
                    path = method_def.get('path', '')
                    full_path = parent_path + '/' + path if parent_path else path

                    action = {
                        'name': action_name,
                        'description': method_def.get('description', method_name),
                        'endpoint_path': '/' + full_path.lstrip('/'),
                        'http_method': method_def.get('httpMethod', 'POST'),
                        'parameters': [],
                        'tags': [resource_name],
                        'execution_pattern': 'simple'
                    }

                    # Parse parameters
                    for param_name, param_def in method_def.get('parameters', {}).items():
                        action['parameters'].append({
                            'name': param_name,
                            'location': param_def.get('location', 'query'),
                            'type': param_def.get('type', 'string'),
                            'required': param_def.get('required', False),
                            'description': param_def.get('description', '')
                        })

                    actions.append(action)

                # Parse nested resources
                for nested_name, nested_def in resource_def.get('resources', {}).items():
                    parse_resource(nested_name, nested_def, full_path)

            # Parse all top-level resources
            for resource_name, resource_def in spec.get('resources', {}).items():
                parse_resource(resource_name, resource_def)

            return {
                'base_url': base_url,
                'auth': {'type': 'oauth2'},  # Google APIs typically use OAuth2
                'actions': actions,
                'total_count': len(actions)
            }

        except Exception as e:
            logger.error(f"Failed to parse Google Discovery doc: {e}", exc_info=True)
            raise

    @staticmethod
    def _get_param_type(schema: Dict) -> str:
        """Extract parameter type from schema"""
        if 'type' in schema:
            return schema['type']
        elif '$ref' in schema:
            return 'object'
        return 'string'

    @staticmethod
    def _detect_execution_pattern(operation: Dict, responses: Dict) -> str:
        """Detect if operation is sync, async polling, webhook, etc."""

        # Check for callbacks (webhooks)
        if 'callbacks' in operation or 'x-webhooks' in operation:
            return 'webhook'

        # Check for async indicators
        if 'x-async' in operation or 'x-long-running' in operation:
            return 'async_polling'

        # Check response codes
        if '202' in responses:  # Accepted - typically async
            return 'async_polling'

        # Check for streaming
        if 'x-stream' in operation:
            return 'streaming'

        return 'simple'

    @staticmethod
    def _extract_auth_info(spec: Dict) -> Dict:
        """Extract authentication information from spec"""

        auth_info = {'type': None, 'schemes': []}

        # OpenAPI 3.0
        if 'components' in spec and 'securitySchemes' in spec['components']:
            schemes = spec['components']['securitySchemes']

            for scheme_name, scheme_def in schemes.items():
                scheme_type = scheme_def.get('type')

                if scheme_type == 'http':
                    auth_info['type'] = scheme_def.get('scheme', 'bearer')
                elif scheme_type == 'apiKey':
                    auth_info['type'] = 'api_key'
                    auth_info['key_name'] = scheme_def.get('name', 'X-API-Key')
                elif scheme_type == 'oauth2':
                    auth_info['type'] = 'oauth2'
                elif scheme_type == 'openIdConnect':
                    auth_info['type'] = 'oidc'

                auth_info['schemes'].append({
                    'name': scheme_name,
                    'type': scheme_type,
                    'details': scheme_def
                })

        # Swagger 2.0
        elif 'securityDefinitions' in spec:
            for scheme_name, scheme_def in spec['securityDefinitions'].items():
                scheme_type = scheme_def.get('type')

                if scheme_type == 'basic':
                    auth_info['type'] = 'basic'
                elif scheme_type == 'apiKey':
                    auth_info['type'] = 'api_key'
                elif scheme_type == 'oauth2':
                    auth_info['type'] = 'oauth2'

        return auth_info


class ActionCategorizer:
    """Categorize API actions into logical groups"""

    @staticmethod
    def categorize(spec: Dict, service_type: str = '') -> Dict:
        """
        Categorize actions based on tags, paths, and patterns

        Returns:
        {
            'categories': {
                'category_name': {
                    'name': str,
                    'count': int,
                    'actions': [...]
                }
            },
            'total': int,
            'recommended': [category_names]
        }
        """

        categories = {}

        for action in spec['actions']:
            # Use OpenAPI tags first
            if action['tags']:
                category = action['tags'][0].lower().replace(' ', '_')
            else:
                # Infer from endpoint path
                category = ActionCategorizer._infer_category(action['endpoint_path'], service_type)

            if category not in categories:
                categories[category] = {
                    'name': category.replace('_', ' ').title(),
                    'count': 0,
                    'actions': []
                }

            categories[category]['actions'].append(action)
            categories[category]['count'] += 1

        # AI recommends which categories to enable
        recommended = ActionCategorizer._recommend_categories(categories, service_type)

        return {
            'categories': categories,
            'total': sum(cat['count'] for cat in categories.values()),
            'recommended': recommended
        }

    @staticmethod
    def _infer_category(path: str, service_type: str) -> str:
        """Infer category from API path"""

        path_lower = path.lower()

        # Common patterns
        if '/issue' in path_lower or '/issues' in path_lower:
            return 'issues'
        elif '/comment' in path_lower:
            return 'comments'
        elif '/user' in path_lower or '/member' in path_lower:
            return 'users'
        elif '/workflow' in path_lower or '/transition' in path_lower:
            return 'workflows'
        elif '/attachment' in path_lower or '/file' in path_lower:
            return 'attachments'
        elif '/search' in path_lower:
            return 'search'
        elif '/project' in path_lower:
            return 'projects'
        elif '/message' in path_lower or '/chat' in path_lower:
            return 'messages'
        elif '/channel' in path_lower:
            return 'channels'
        elif '/repository' in path_lower or '/repo/' in path_lower:
            return 'repositories'
        elif '/pull' in path_lower or '/pr/' in path_lower:
            return 'pull_requests'

        return 'general'

    @staticmethod
    def _recommend_categories(categories: Dict, service_type: str) -> List[str]:
        """AI recommends which categories to enable by default"""

        # Service-specific recommendations
        recommendations_map = {
            'jira': ['issues', 'comments', 'workflows', 'projects'],
            'slack': ['messages', 'channels', 'users'],
            'github': ['issues', 'pull_requests', 'repositories'],
            'google_drive': ['files', 'permissions'],
            'trello': ['boards', 'cards', 'lists'],
            'asana': ['tasks', 'projects', 'teams']
        }

        service_lower = service_type.lower()

        # Return service-specific recommendations if available
        for key, recs in recommendations_map.items():
            if key in service_lower:
                # Filter to only existing categories
                return [cat for cat in recs if cat in categories]

        # Default: return top 3 categories by action count
        sorted_cats = sorted(categories.items(), key=lambda x: x[1]['count'], reverse=True)
        return [cat[0] for cat in sorted_cats[:3]]
