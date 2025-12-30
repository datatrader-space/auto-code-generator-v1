# agent/services/knowledge_builder.py
"""
Knowledge Builder - Builds system knowledge graph from user answers

Takes analysis + answers and creates SystemKnowledge objects
"""

import logging
from typing import Dict, Any, List
from agent.models import Repository, SystemKnowledge

logger = logging.getLogger(__name__)


class KnowledgeBuilder:
    """
    Builds system knowledge from repo analysis + user answers
    """
    
    def build_repo_knowledge(
        self,
        repository: Repository,
        answers: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build knowledge for single repository
        
        Args:
            repository: Repository object
            answers: User answers to questions
            
        Returns:
            Updated repository config
        """
        
        analysis = repository.analysis or {}
        
        # Build configuration
        config = {
            "paradigm": self._determine_paradigm(analysis, answers),
            "can_use_standard_crs": analysis.get('can_use_standard_crs', False),
            "artifact_types": self._determine_artifact_types(analysis, answers),
            "dependencies": self._build_dependencies(answers),
            "communication_patterns": self._build_communication_patterns(answers),
            "fields_used": self._extract_fields_used(answers),
            "conventions": self._extract_conventions(answers)
        }
        
        # Update repository
        repository.config = config
        repository.status = 'questions_answered'
        repository.save()
        
        logger.info(f"Built config for {repository.name}: {config['paradigm']}")
        
        return config
    
    def build_system_knowledge(
        self,
        system,
        repositories: List[Repository]
    ) -> List[SystemKnowledge]:
        """
        Build system-level knowledge from all repositories
        
        Creates:
        - Architecture overview
        - Cross-repo flows (inferred)
        - API contracts
        - Communication patterns
        """
        
        knowledge_items = []
        
        # 1. System architecture
        arch = self._build_architecture(system, repositories)
        arch_knowledge, created = SystemKnowledge.objects.get_or_create(
            system=system,
            knowledge_type='architecture',
            spec_id='system_overview',
            defaults={
                'content': arch,
                'source': 'user_provided',
                'confidence': 1.0
            }
        )
        if not created:
            arch_knowledge.content = arch
            arch_knowledge.save()
        knowledge_items.append(arch_knowledge)
        
        # 2. API contracts (from answers)
        contracts = self._build_contracts(repositories)
        for contract in contracts:
            contract_knowledge, created = SystemKnowledge.objects.get_or_create(
                system=system,
                knowledge_type='contract',
                spec_id=contract['spec_id'],
                defaults={
                    'content': contract['content'],
                    'source': 'user_provided',
                    'confidence': 0.9
                }
            )
            if not created:
                contract_knowledge.content = contract['content']
                contract_knowledge.save()
            knowledge_items.append(contract_knowledge)
        
        # 3. Communication patterns
        patterns = self._build_patterns(repositories)
        for pattern in patterns:
            pattern_knowledge, created = SystemKnowledge.objects.get_or_create(
                system=system,
                knowledge_type='pattern',
                spec_id=pattern['spec_id'],
                defaults={
                    'content': pattern['content'],
                    'source': 'llm_inference',
                    'confidence': 0.8
                }
            )
            if not created:
                pattern_knowledge.content = pattern['content']
                pattern_knowledge.save()
            knowledge_items.append(pattern_knowledge)
        
        logger.info(f"Created {len(knowledge_items)} system knowledge items")
        
        return knowledge_items
    def _determine_paradigm(self, analysis: Dict, answers: Dict) -> str:
        """Determine final paradigm from analysis + answers"""
        
        # User confirmation takes precedence
        if 'paradigm_confirm' in answers:
            answer = answers['paradigm_confirm']
            if 'Django' in answer:
                return 'django'
            elif 'FastAPI' in answer:
                return 'fastapi'
            elif 'Celery' in answer:
                return 'celery_tasks'
            elif 'service' in answer.lower():
                return 'service_classes'
        
        # Fallback to LLM analysis
        return analysis.get('paradigm', 'unknown')
    
    def _determine_artifact_types(self, analysis: Dict, answers: Dict) -> List[str]:
        """Determine what artifact types to extract"""
        
        paradigm = self._determine_paradigm(analysis, answers)
        
        if paradigm == 'django':
            return ['django_model', 'model_field', 'drf_serializer', 'drf_view', 'url_pattern']
        elif paradigm == 'service_classes':
            return ['service_class', 'service_method', 'api_call']
        elif paradigm == 'fastapi':
            return ['fastapi_endpoint', 'pydantic_model', 'handler_function']
        elif paradigm == 'celery_tasks':
            return ['celery_task', 'task_handler', 'queue_config']
        else:
            return ['python_class', 'python_function']
    
    def _build_dependencies(self, answers: Dict) -> Dict[str, Any]:
        """Build dependency information from answers"""
        
        deps = {
            "calls_other_repos": answers.get('calls_other_repos') == 'yes',
            "target_repos": [],
            "communication_methods": []
        }
        
        if 'calls_which_repos' in answers:
            deps['target_repos'] = answers['calls_which_repos']
        
        if 'communication_method' in answers:
            method = answers['communication_method']
            if isinstance(method, list):
                deps['communication_methods'] = method
            else:
                deps['communication_methods'] = [method]
        
        return deps
    
    def _build_communication_patterns(self, answers: Dict) -> List[str]:
        """Extract communication patterns"""
        
        patterns = []
        
        if 'communication_method' in answers:
            method = answers['communication_method']
            if 'API' in str(method):
                patterns.append('rest_api')
            if 'queue' in str(method).lower():
                patterns.append('message_queue')
            if 'import' in str(method).lower():
                patterns.append('direct_import')
        
        return patterns
    
    def _extract_fields_used(self, answers: Dict) -> List[str]:
        """Extract field references from answers"""
        
        fields = []
        
        if 'model_fields_used' in answers:
            raw = answers['model_fields_used']
            if isinstance(raw, str):
                # Parse "Order.status, Customer.email"
                for field in raw.split(','):
                    field = field.strip()
                    if field:
                        fields.append(field)
            elif isinstance(raw, list):
                fields = raw
        
        return fields
    
    def _extract_conventions(self, answers: Dict) -> Dict[str, str]:
        """Extract naming conventions"""
        
        conventions = {}
        
        if 'naming_conventions' in answers:
            conventions['naming'] = answers['naming_conventions']
        
        return conventions
    
    def _build_architecture(self, system, repositories: List[Repository]) -> Dict[str, Any]:
        """Build system architecture document"""
        
        repos_info = []
        for repo in repositories:
            config = repo.config or {}
            repos_info.append({
                "name": repo.name,
                "paradigm": config.get('paradigm', 'unknown'),
                "role": self._infer_role(repo.name, config),
                "dependencies": config.get('dependencies', {})
            })
        
        return {
            "name": system.name,
            "repositories": repos_info,
            "description": f"Multi-repo system with {len(repositories)} repositories"
        }
    
    def _infer_role(self, repo_name: str, config: Dict) -> str:
        """Infer repository role from name and config"""
        
        name_lower = repo_name.lower()
        
        if 'data' in name_lower:
            return 'data_layer'
        elif 'worker' in name_lower:
            return 'background_jobs'
        elif 'storage' in name_lower:
            return 'file_storage'
        elif 'central' in name_lower or 'api' in name_lower:
            return 'api_gateway'
        else:
            return 'application'
    
    def _build_contracts(self, repositories: List[Repository]) -> List[Dict]:
        """Build API contracts from repository configs"""
        
        contracts = []
        
        for repo in repositories:
            config = repo.config or {}
            deps = config.get('dependencies', {})
            
            if deps.get('calls_other_repos'):
                for target_repo in deps.get('target_repos', []):
                    contracts.append({
                        "spec_id": f"{repo.name}_to_{target_repo}_contract",
                        "content": {
                            "provider": target_repo,
                            "consumer": repo.name,
                            "type": "api",  # Inferred
                            "methods": deps.get('communication_methods', [])
                        }
                    })
        
        return contracts
    
    def _build_patterns(self, repositories: List[Repository]) -> List[Dict]:
        """Build communication patterns"""
        
        patterns = []
        
        # Group repos by communication method
        api_callers = []
        queue_users = []
        
        for repo in repositories:
            config = repo.config or {}
            comm_patterns = config.get('communication_patterns', [])
            
            if 'rest_api' in comm_patterns:
                api_callers.append(repo.name)
            if 'message_queue' in comm_patterns:
                queue_users.append(repo.name)
        
        if api_callers:
            patterns.append({
                "spec_id": "rest_api_pattern",
                "content": {
                    "pattern": "REST API calls",
                    "repos": api_callers,
                    "description": "Repositories communicate via HTTP REST APIs"
                }
            })
        
        if queue_users:
            patterns.append({
                "spec_id": "message_queue_pattern",
                "content": {
                    "pattern": "Message Queue",
                    "repos": queue_users,
                    "description": "Repositories communicate via message queue"
                }
            })
        
        return patterns