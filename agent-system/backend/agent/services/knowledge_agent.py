"""
Repository Knowledge Agent
The "Senior Engineer" layer that understands repository architecture

This agent analyzes CRS artifacts to build high-level understanding:
- Architecture patterns
- Domain models
- Design patterns
- Coding conventions
- Usage guides
"""

from typing import Dict, List, Any, Optional, Callable
import time
import logging
import os

logger = logging.getLogger(__name__)


class RepositoryKnowledgeAgent:
    """
    Repository Knowledge Agent
    Builds and maintains high-level understanding of repository architecture
    """

    def __init__(self, repository, socket_callback: Optional[Callable] = None):
        """
        Initialize knowledge agent

        Args:
            repository: Django Repository model instance
            socket_callback: Optional callback for real-time event streaming
        """
        self.repository = repository
        self.socket_callback = socket_callback

        # Initialize CRS components (lazy-loaded when needed)
        self._fs = None
        self._spec_store = None
        self._query_api = None

    @property
    def fs(self):
        """Lazy-load WorkspaceFS"""
        if self._fs is None:
            from core.fs import WorkspaceFS
            self._fs = WorkspaceFS(workspace_root=self.repository.crs_workspace_path)
        return self._fs

    @property
    def spec_store(self):
        """Lazy-load SpecStore"""
        if self._spec_store is None:
            from core.spec_store import SpecStore
            self._spec_store = SpecStore(self.fs)
        return self._spec_store

    @property
    def query_api(self):
        """Lazy-load CRSQueryAPI"""
        if self._query_api is None:
            from core.query_api import CRSQueryAPI
            self._query_api = CRSQueryAPI(self.fs)
        return self._query_api

    def _send_event(self, event_type: str, data: dict):
        """Send event through socket if callback provided"""
        if self.socket_callback:
            try:
                self.socket_callback({
                    'type': event_type,
                    **data
                })
            except Exception as e:
                logger.error(f"Failed to send event {event_type}: {e}")

    def analyze_repository(self) -> Dict[str, Any]:
        """
        Full knowledge extraction

        Returns:
            dict: {
                'docs_created': int,
                'docs_list': List[str],
                'duration_ms': int,
                'summary': dict
            }
        """
        start = time.time()

        logger.info(f"Starting knowledge extraction for repository: {self.repository.name}")

        self._send_event('knowledge_extraction_started', {
            'repository_id': self.repository.id,
            'repository_name': self.repository.name,
            'timestamp': self._utc_iso()
        })

        docs_created = []

        try:
            # 1. Repository Profile
            self._send_event('knowledge_extraction_progress', {
                'stage': 'repository_profile',
                'message': 'Analyzing repository architecture...'
            })
            profile = self._extract_repository_profile()
            self.spec_store.upsert_doc(
                kind='repository_profile',
                spec_id='main',
                payload=profile
            )
            docs_created.append('repository_profile/main')
            logger.info(f"Created repository profile: {profile.get('architecture', {}).get('style')}")

            # 2. Domain Model
            self._send_event('knowledge_extraction_progress', {
                'stage': 'domain_model',
                'message': 'Extracting domain model and business logic...'
            })
            domain_model = self._extract_domain_model()
            self.spec_store.upsert_doc(
                kind='domain_model',
                spec_id='core_entities',
                payload=domain_model
            )
            docs_created.append('domain_model/core_entities')
            logger.info(f"Extracted domain model with {len(domain_model.get('entities', []))} entities")

            # 3. Architectural Patterns
            self._send_event('knowledge_extraction_progress', {
                'stage': 'patterns',
                'message': 'Detecting architectural patterns...'
            })
            patterns = self._detect_patterns()
            for pattern in patterns:
                self.spec_store.upsert_doc(
                    kind='architectural_pattern',
                    spec_id=pattern['id'],
                    payload=pattern
                )
                docs_created.append(f"architectural_pattern/{pattern['id']}")
            logger.info(f"Detected {len(patterns)} architectural patterns")

            # 4. Coding Conventions
            self._send_event('knowledge_extraction_progress', {
                'stage': 'conventions',
                'message': 'Learning coding conventions...'
            })
            conventions = self._extract_conventions()
            for conv in conventions:
                self.spec_store.upsert_doc(
                    kind='coding_convention',
                    spec_id=conv['id'],
                    payload=conv
                )
                docs_created.append(f"coding_convention/{conv['id']}")
            logger.info(f"Extracted {len(conventions)} coding conventions")

            # 5. Usage Guides
            self._send_event('knowledge_extraction_progress', {
                'stage': 'usage_guides',
                'message': 'Generating usage guides...'
            })
            guides = self._generate_usage_guides()
            for guide in guides:
                self.spec_store.upsert_doc(
                    kind='usage_guide',
                    spec_id=guide['id'],
                    payload=guide
                )
                docs_created.append(f"usage_guide/{guide['id']}")
            logger.info(f"Generated {len(guides)} usage guides")

            duration_ms = int((time.time() - start) * 1000)

            result = {
                'status': 'success',
                'docs_created': len(docs_created),
                'docs_list': docs_created,
                'duration_ms': duration_ms,
                'summary': {
                    'architecture_style': profile.get('architecture', {}).get('style'),
                    'domain': profile.get('architecture', {}).get('domain'),
                    'entities_count': len(domain_model.get('entities', [])),
                    'patterns_found': len(patterns),
                    'conventions_found': len(conventions),
                    'guides_created': len(guides)
                }
            }

            self._send_event('knowledge_extraction_complete', result)
            logger.info(f"Knowledge extraction completed in {duration_ms}ms")

            return result

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Knowledge extraction failed: {e}", exc_info=True)

            error_result = {
                'status': 'error',
                'error': str(e),
                'docs_created': len(docs_created),
                'duration_ms': duration_ms
            }

            self._send_event('knowledge_extraction_error', error_result)

            return error_result

    def incremental_update(self, changed_files: List[str]) -> Dict[str, Any]:
        """
        Incremental knowledge update when repository changes

        Args:
            changed_files: List of file paths that changed

        Returns:
            dict: Update results
        """
        logger.info(f"Starting incremental knowledge update for {len(changed_files)} changed files")

        # Determine what knowledge to update based on changed files
        update_areas = self._determine_update_areas(changed_files)

        if not update_areas:
            logger.info("No knowledge areas need updating")
            return {
                'update_type': 'incremental',
                'areas_updated': [],
                'files_analyzed': len(changed_files),
                'changes_made': False
            }

        updated = []

        try:
            if 'conventions' in update_areas:
                conventions = self._extract_conventions()
                for conv in conventions:
                    self.spec_store.upsert_doc(
                        kind='coding_convention',
                        spec_id=conv['id'],
                        payload=conv
                    )
                updated.append('conventions')
                logger.info("Updated coding conventions")

            if 'patterns' in update_areas:
                patterns = self._detect_patterns()
                for pattern in patterns:
                    self.spec_store.upsert_doc(
                        kind='architectural_pattern',
                        spec_id=pattern['id'],
                        payload=pattern
                    )
                updated.append('patterns')
                logger.info("Updated architectural patterns")

            if 'domain_model' in update_areas:
                domain_model = self._extract_domain_model()
                self.spec_store.upsert_doc(
                    kind='domain_model',
                    spec_id='core_entities',
                    payload=domain_model
                )
                updated.append('domain_model')
                logger.info("Updated domain model")

            # Update profile timestamp
            profile = self.spec_store.get_doc(kind='repository_profile', spec_id='main')
            if profile:
                profile['last_incremental_update'] = self._utc_iso()
                profile['last_changed_files'] = changed_files
                self.spec_store.upsert_doc(
                    kind='repository_profile',
                    spec_id='main',
                    payload=profile
                )

            return {
                'update_type': 'incremental',
                'areas_updated': updated,
                'files_analyzed': len(changed_files),
                'changes_made': True
            }

        except Exception as e:
            logger.error(f"Incremental update failed: {e}", exc_info=True)
            return {
                'update_type': 'incremental',
                'error': str(e),
                'areas_updated': updated,
                'files_analyzed': len(changed_files),
                'changes_made': False
            }

    def get_context_for(self, request: str) -> Dict[str, Any]:
        """
        Get relevant knowledge context for a specific request
        Used by Agent Runner to get high-level understanding

        Args:
            request: User's request/question

        Returns:
            dict: Relevant knowledge context
        """
        try:
            # Get profile
            profile = self.spec_store.get_doc(kind='repository_profile', spec_id='main')

            # Search for relevant patterns/guides/conventions
            relevant_docs = self.spec_store.search_docs(q=request, limit=5)

            return {
                'profile': profile,
                'relevant_knowledge': relevant_docs,
                'architecture_style': profile.get('architecture', {}).get('style') if profile else None,
                'domain': profile.get('architecture', {}).get('domain') if profile else None
            }
        except Exception as e:
            logger.error(f"Failed to get context for request: {e}")
            return {
                'profile': None,
                'relevant_knowledge': [],
                'architecture_style': None,
                'domain': None,
                'error': str(e)
            }

    # =========================================================================
    # EXTRACTION METHODS
    # =========================================================================

    def _extract_repository_profile(self) -> Dict[str, Any]:
        """
        Analyze CRS artifacts to detect:
        - Architecture style (Django REST, FastAPI, etc.)
        - Pattern (MVC, 3-tier, hexagonal, etc.)
        - Domain (e-commerce, CRM, etc.)
        - Tech stack
        """
        # Get all artifacts
        artifacts = self.query_api.find_artifacts()

        # Count artifact types
        artifact_counts = {}
        for artifact in artifacts:
            kind = artifact.get('kind', 'unknown')
            artifact_counts[kind] = artifact_counts.get(kind, 0) + 1

        # Detect architecture components
        architecture_style = self._detect_architecture_style(artifact_counts, artifacts)
        pattern = self._detect_architectural_pattern(artifacts)
        domain = self._detect_domain(artifacts)
        tech_stack = self._detect_tech_stack(artifact_counts)

        return {
            'spec_id': 'main',
            'description': f'Repository profile for {self.repository.name}',
            'architecture': {
                'style': architecture_style,
                'pattern': pattern,
                'domain': domain,
                'artifact_counts': artifact_counts,
                'total_artifacts': len(artifacts)
            },
            'tech_stack': tech_stack,
            'repository': {
                'name': self.repository.name,
                'github_url': self.repository.github_url,
                'branch': self.repository.github_branch
            },
            'extracted_at': self._utc_iso()
        }

    def _detect_architecture_style(self, counts: dict, artifacts: list) -> str:
        """Detect architecture style from artifact patterns"""
        # Django REST Framework detection
        if (counts.get('django_model', 0) > 0 and
            counts.get('drf_serializer', 0) > 0 and
            counts.get('drf_viewset', 0) > 0):
            return 'django_rest_framework'

        # Django (non-DRF)
        if counts.get('django_model', 0) > 0:
            return 'django'

        return 'unknown'

    def _detect_architectural_pattern(self, artifacts: list) -> str:
        """Detect architectural pattern"""
        has_models = any(a.get('kind') == 'django_model' for a in artifacts)
        has_serializers = any(a.get('kind') == 'drf_serializer' for a in artifacts)
        has_views = any(a.get('kind') in ['drf_viewset', 'drf_apiview'] for a in artifacts)

        if has_models and has_serializers and has_views:
            return '3_tier_mvc'

        return 'unknown'

    def _detect_domain(self, artifacts: list) -> str:
        """Detect business domain from entity names"""
        model_names = [
            a.get('name', '').lower()
            for a in artifacts
            if a.get('kind') == 'django_model'
        ]

        model_text = ' '.join(model_names)

        # E-commerce
        if any(kw in model_text for kw in ['order', 'product', 'cart', 'payment', 'customer', 'checkout']):
            return 'ecommerce'

        # CRM
        if any(kw in model_text for kw in ['lead', 'contact', 'deal', 'opportunity', 'account']):
            return 'crm'

        # CMS
        if any(kw in model_text for kw in ['post', 'article', 'page', 'content', 'media']):
            return 'cms'

        # Agent/AI system
        if any(kw in model_text for kw in ['agent', 'task', 'system', 'repository', 'llm', 'chat']):
            return 'agent_system'

        return 'general'

    def _detect_tech_stack(self, counts: dict) -> Dict[str, str]:
        """Detect tech stack from artifact types"""
        stack = {
            'language': 'python',
            'framework': 'unknown',
            'conventions': 'unknown'
        }

        if counts.get('drf_serializer', 0) > 0:
            stack['framework'] = 'django_rest_framework'
            stack['conventions'] = 'drf_standard'
        elif counts.get('django_model', 0) > 0:
            stack['framework'] = 'django'
            stack['conventions'] = 'django_standard'

        return stack

    def _extract_domain_model(self) -> Dict[str, Any]:
        """Extract business logic understanding"""
        models = self.query_api.find_artifacts(kind='django_model')

        entities = []
        relationships_map = {}

        for model in models:
            model_id = model.get('id')
            model_name = model.get('name')

            # Get relationships
            outgoing = self.query_api.neighbors(model_id, direction='outgoing')
            incoming = self.query_api.neighbors(model_id, direction='incoming')

            # Determine entity role
            role = self._determine_entity_role(model_name, outgoing, incoming)

            entities.append({
                'name': model_name,
                'id': model_id,
                'role': role,
                'file': model.get('file'),
                'line': model.get('line')
            })

            relationships_map[model_name] = {
                'outgoing': [{'type': r[0], 'target': r[1]} for r in outgoing[:10]],
                'incoming': [{'type': r[0], 'source': r[1]} for r in incoming[:10]]
            }

        return {
            'spec_id': 'core_entities',
            'description': 'Domain model and business logic',
            'entities': entities,
            'relationships': relationships_map,
            'entity_count': len(entities),
            'extracted_at': self._utc_iso()
        }

    def _determine_entity_role(self, name: str, outgoing: list, incoming: list) -> str:
        """Determine entity role in domain model"""
        name_lower = name.lower()

        # Identity entities
        if name_lower in ['user', 'account', 'customer']:
            return 'identity'

        # Transactional entities
        if name_lower in ['order', 'transaction', 'payment']:
            return 'transaction'

        # Master data
        if name_lower in ['product', 'category', 'item']:
            return 'master_data'

        # High connectivity → important entity
        if len(incoming) > 3:
            return 'referenced_entity'

        if len(outgoing) > 3:
            return 'aggregate_root'

        return 'domain_entity'

    def _detect_patterns(self) -> List[Dict[str, Any]]:
        """Detect design patterns in the codebase"""
        patterns = []

        # For now, return empty list
        # Would implement pattern detection heuristics here

        return patterns

    def _extract_conventions(self) -> List[Dict[str, Any]]:
        """Extract coding conventions from existing code"""
        conventions = []

        # Model conventions
        model_convention = self._analyze_model_conventions()
        if model_convention:
            conventions.append(model_convention)

        return conventions

    def _analyze_model_conventions(self) -> Optional[Dict[str, Any]]:
        """Analyze Django model conventions"""
        models = self.query_api.find_artifacts(kind='django_model')

        if not models:
            return None

        return {
            'id': 'model_conventions',
            'spec_id': 'model_conventions',
            'category': 'models',
            'description': f'Django model conventions in {self.repository.name}',
            'rules': [
                {
                    'name': 'model_count',
                    'value': len(models),
                    'description': f'Repository contains {len(models)} Django models'
                }
            ],
            'examples': [
                {
                    'model': m.get('name'),
                    'file': m.get('file'),
                    'line': m.get('line')
                } for m in models[:5]
            ]
        }

    def _generate_usage_guides(self) -> List[Dict[str, Any]]:
        """Generate usage guides for common tasks"""
        guides = []

        models = self.query_api.find_artifacts(kind='django_model')
        serializers = self.query_api.find_artifacts(kind='drf_serializer')
        viewsets = self.query_api.find_artifacts(kind='drf_viewset')

        if models and serializers and viewsets:
            guide = self._generate_add_api_guide(models[0], serializers[0], viewsets[0])
            guides.append(guide)

        return guides

    def _generate_add_api_guide(self, example_model, example_serializer, example_viewset) -> Dict[str, Any]:
        """Generate guide for adding a new model-backed API"""
        return {
            'id': 'add_new_model_backed_api',
            'spec_id': 'add_new_model_backed_api',
            'use_case': 'Creating a new model-backed REST API endpoint',
            'description': 'Step-by-step guide based on existing patterns',
            'steps': [
                {
                    'step': 1,
                    'action': 'Create Django model',
                    'location': '<app>/models.py',
                    'example': f"{example_model.get('file')}:{example_model.get('line')}"
                },
                {
                    'step': 2,
                    'action': 'Create DRF serializer',
                    'location': '<app>/serializers.py',
                    'example': f"{example_serializer.get('file')}:{example_serializer.get('line')}"
                },
                {
                    'step': 3,
                    'action': 'Create ViewSet',
                    'location': '<app>/views.py',
                    'example': f"{example_viewset.get('file')}:{example_viewset.get('line')}"
                },
                {
                    'step': 4,
                    'action': 'Register router',
                    'location': '<app>/urls.py',
                    'code': "router.register(r'<resource>', <ViewSet>)"
                }
            ]
        }

    def _determine_update_areas(self, changed_files: List[str]) -> List[str]:
        """Determine which knowledge areas need updating based on changed files"""
        areas = set()

        for file_path in changed_files:
            # Python files → conventions
            if file_path.endswith('.py'):
                areas.add('conventions')

            # Architecture files → patterns
            if any(x in file_path for x in ['models.py', 'serializers.py', 'views.py', 'services/']):
                areas.add('patterns')

            # Domain entities → domain model
            if 'models.py' in file_path:
                areas.add('domain_model')

        return list(areas)

    def _utc_iso(self) -> str:
        """Return current UTC time in ISO format"""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
