"""
Django REST Framework Views for Agent API
"""

import logging
import os
import time
from datetime import timedelta
from pathlib import Path

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async  # (only if you actually use it here; otherwise remove)
from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Sum, Q
from django.db.models.functions import TruncHour, Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status, decorators
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agent.models import (
    System, Repository, RepositoryQuestion,
    SystemKnowledge, Task, AgentMemory,
    ChatConversation, ChatMessage,
    LLMProvider, LLMModel, LLMRequestLog,
    SystemDocumentation,
)
from agent.serializers import (
    SystemListSerializer, SystemDetailSerializer,
    RepositoryListSerializer, RepositoryDetailSerializer, RepositoryCreateSerializer,
    RepositoryQuestionSerializer, AnswerQuestionsSerializer,
    SystemKnowledgeSerializer, TaskListSerializer, TaskDetailSerializer,
    TaskCreateSerializer, AgentMemorySerializer,
    AnalyzeRepositorySerializer, LLMHealthSerializer, LLMStatsSerializer,
    ChatConversationListSerializer, ChatConversationSerializer,
    SystemDocumentationSerializer,
    LLMProviderSerializer, LLMModelSerializer,
)
from agent.services.github_client import GitHubClient
from agent.services.knowledge_builder import KnowledgeBuilder
from agent.services.question_generator import QuestionGenerator
from agent.services.repo_analyzer import RepositoryAnalyzer
from agent.services.crs_runner import (
    run_crs_pipeline, load_crs_payload, get_crs_summary,
    run_crs_step, get_crs_step_status
)
from core.events import get_broadcaster
from llm.router import get_llm_router

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class SystemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing systems
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return System.objects.filter(user=self.request.user).prefetch_related('repositories')

    def get_serializer_class(self):
        if self.action == 'list':
            return SystemListSerializer
        return SystemDetailSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RepositoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing repositories
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        if system_id:
            return Repository.objects.filter(
                system_id=system_id,
                system__user=self.request.user
            ).select_related('system')
        return Repository.objects.filter(system__user=self.request.user).select_related('system')

    def get_serializer_class(self):
        if self.action == 'create':
            return RepositoryCreateSerializer
        if self.action == 'list':
            return RepositoryListSerializer
        return RepositoryDetailSerializer

    def create(self, request, system_pk=None):
        system = get_object_or_404(System, id=system_pk, user=request.user)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        repository = serializer.save(system=system)

        detail_serializer = RepositoryDetailSerializer(repository)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    def _ensure_repo_clone(self, repository, user):
        if repository.clone_path and os.path.isdir(repository.clone_path):
            return repository.clone_path

        repo_root = Path(settings.BASE_DIR).parents[1]
        clone_root = repo_root / "workspaces" / str(user.id) / str(repository.system_id)
        clone_path = clone_root / repository.name

        client = GitHubClient(token=user.github_token)
        clone_result = client.clone_repository(
            github_url=repository.github_url,
            target_path=str(clone_path),
            branch=repository.github_branch,
        )

        if not clone_result.get("success"):
            raise RuntimeError(clone_result.get("error") or "Failed to clone repository")

        repository.clone_path = clone_result.get("path", str(clone_path))
        repository.last_commit_sha = clone_result.get("commit_sha", "")
        repository.save(update_fields=["clone_path", "last_commit_sha"])
        return repository.clone_path

    @decorators.action(detail=True, methods=['post'])
    def analyze(self, request, pk=None, system_pk=None):
        repository = self.get_object()

        serializer = AnalyzeRepositorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        force = serializer.validated_data.get('force', False)

        if repository.status in ['questions_generated', 'questions_answered', 'ready'] and not force:
            return Response({
                'message': 'Repository already analyzed',
                'status': repository.status,
                'analysis': repository.analysis
            })

        try:
            repository.status = 'analyzing'
            repository.save(update_fields=["status"])

            self._ensure_repo_clone(repository, request.user)

            analyzer = RepositoryAnalyzer()
            analysis = analyzer.analyze(
                repo_path=repository.clone_path,
                repo_name=repository.name
            )

            repository.analysis = analysis
            repository.status = 'analyzing'
            repository.save(update_fields=["analysis", "status"])

            generator = QuestionGenerator()

            other_repos = [
                {'name': r.name, 'paradigm': (r.config or {}).get('paradigm', 'unknown')}
                for r in repository.system.repositories.exclude(id=repository.id)
            ]

            questions = generator.generate_questions(
                repo_name=repository.name,
                analysis=analysis,
                other_repos=other_repos
            )

            repository.questions.all().delete()
            for idx, q in enumerate(questions, 1):
                RepositoryQuestion.objects.create(
                    repository=repository,
                    question_key=q.key,
                    question_text=q.text,
                    question_type=q.type,
                    options=q.options,
                    required=q.required,
                    category=q.category,
                    order=idx
                )

            repository.status = 'questions_generated'
            repository.save(update_fields=["status"])

            return Response({
                'message': 'Analysis complete',
                'analysis': analysis,
                'questions_count': len(questions)
            })

        except Exception as e:
            logger.error("Analysis failed: %s", e, exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'])
    def questions(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        questions = repository.questions.all().order_by('order')
        serializer = RepositoryQuestionSerializer(questions, many=True)
        return Response({
            'count': questions.count(),
            'answered': questions.filter(answer__isnull=False).count(),
            'questions': serializer.data
        })

    @decorators.action(detail=True, methods=['post'])
    def submit_answers(self, request, pk=None, system_pk=None):
        repository = self.get_object()

        serializer = AnswerQuestionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data['answers']

        try:
            with transaction.atomic():
                for question in repository.questions.all():
                    if question.question_key in answers:
                        question.answer = answers[question.question_key]
                        question.save(update_fields=["answer"])

                builder = KnowledgeBuilder()
                config = builder.build_repo_knowledge(repository, answers)

                all_repos = list(repository.system.repositories.all())
                knowledge_items = builder.build_system_knowledge(repository.system, all_repos)

                if repository.system.status == 'initializing':
                    repository.system.status = 'ready'
                    repository.system.save(update_fields=["status"])

            repository.status = 'crs_running'
            repository.save(update_fields=["status"])

            crs_summary = run_crs_pipeline(repository)

            return Response({
                'message': 'Answers submitted successfully',
                'config': config,
                'knowledge_items': len(knowledge_items),
                'crs': crs_summary
            })

        except Exception as e:
            logger.error("Failed to process answers: %s", e, exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['post'], url_path='clone')
    def clone_repository(self, request, pk=None, system_pk=None):
        repository = self.get_object()

        try:
            if not request.user.github_token:
                return Response({
                    'error': 'GitHub token not configured',
                    'message': 'Please connect your GitHub account first'
                }, status=status.HTTP_400_BAD_REQUEST)

            repository.status = 'cloning'
            repository.save(update_fields=["status"])

            clone_path = self._ensure_repo_clone(repository, request.user)

            py_files = []
            for dirpath, _, filenames in os.walk(clone_path):
                for fn in filenames:
                    if fn.endswith(".py"):
                        py_files.append(os.path.join(dirpath, fn))

            repository.status = 'cloned'
            repository.save(update_fields=["status"])

            return Response({
                'message': 'Repository cloned successfully',
                'clone_path': clone_path,
                'python_files_count': len(py_files),
                'commit_sha': repository.last_commit_sha,
                'ready_for_crs': len(py_files) > 0
            })

        except Exception as e:
            logger.error("Clone failed: %s", e, exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response(
                {'error': str(e), 'details': 'Failed to clone repository'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['get'], url_path='status')
    def repo_status(self, request, pk=None, system_pk=None):
        repository = self.get_object()

        status_info = {
            'repository_id': repository.id,
            'name': repository.name,
            'github_url': repository.github_url,
            'status': repository.status,
            'crs_status': repository.crs_status,
            'error_message': repository.error_message,
            'clone_path': repository.clone_path,
            'clone_exists': bool(repository.clone_path and os.path.isdir(repository.clone_path)),
            'crs_workspace_path': repository.crs_workspace_path,
            'last_commit_sha': repository.last_commit_sha,
            'artifacts_count': repository.artifacts_count,
            'relationships_count': repository.relationships_count,
            'last_crs_run': repository.last_crs_run,
        }

        if status_info['clone_exists']:
            py_count = 0
            for _, _, filenames in os.walk(repository.clone_path):
                py_count += sum(1 for fn in filenames if fn.endswith(".py"))
            status_info['python_files_count'] = py_count
            status_info['ready_for_crs'] = py_count > 0
        else:
            status_info['python_files_count'] = 0
            status_info['ready_for_crs'] = False

        return Response(status_info)

    # ---- FIXED: this was overwriting your /crs/ingest endpoint before ----
    @decorators.action(detail=True, methods=['post'], url_path='ingest')
    def ingest_repository_setup(self, request, pk=None, system_pk=None):
        """
        Clone + create CRS workspace config (does NOT run pipeline)

        POST /api/systems/{system_id}/repositories/{repo_id}/ingest/
        Body: {"force_reclone": false}
        """
        repository = self.get_object()

        try:
            force_reclone = bool(request.data.get('force_reclone', False))

            if not request.user.github_token:
                return Response({
                    'error': 'GitHub token not configured',
                    'message': 'Please connect your GitHub account first'
                }, status=status.HTTP_400_BAD_REQUEST)

            clone_exists = repository.clone_path and os.path.isdir(repository.clone_path)

            if force_reclone or not clone_exists:
                repository.status = 'cloning'
                repository.save(update_fields=["status"])

                clone_path = self._ensure_repo_clone(repository, request.user)

                py_files = []
                for dirpath, _, filenames in os.walk(clone_path):
                    for fn in filenames:
                        if fn.endswith(".py"):
                            py_files.append(os.path.join(dirpath, fn))

                if len(py_files) == 0:
                    return Response({
                        'error': 'No Python files found in repository',
                        'message': 'CRS requires Python files to analyze',
                        'clone_path': clone_path
                    }, status=status.HTTP_400_BAD_REQUEST)

                ingestion_result = {
                    'cloned': True,
                    'clone_path': clone_path,
                    'python_files_count': len(py_files),
                    'commit_sha': repository.last_commit_sha
                }
            else:
                clone_path = repository.clone_path
                ingestion_result = {
                    'cloned': False,
                    'clone_path': clone_path,
                    'message': 'Repository already cloned'
                }

            from agent.services.crs_runner import _build_crs_workspace
            crs_workspace = _build_crs_workspace(repository)

            repository.status = 'ready'
            repository.crs_status = 'pending'
            repository.save(update_fields=["status", "crs_status"])

            return Response({
                'message': 'Repository ingested successfully',
                'status': repository.status,
                'crs_status': repository.crs_status,
                'ingestion': ingestion_result,
                'crs_workspace_path': str(crs_workspace.workspace_root),
                'config_path': str(crs_workspace.config_path),
                'ready_for_pipeline': True
            })

        except Exception as e:
            logger.error("Ingestion failed: %s", e, exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response(
                {'error': str(e), 'details': 'Failed to ingest repository'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['post'], url_path='crs/run')
    def run_crs(self, request, pk=None, system_pk=None):
        repository = self.get_object()

        try:
            if not repository.clone_path or not os.path.isdir(repository.clone_path):
                return Response({
                    'error': 'Repository not cloned',
                    'message': 'Please clone the repository first using /clone/ endpoint'
                }, status=status.HTTP_400_BAD_REQUEST)

            repository.status = 'crs_running'
            repository.save(update_fields=["status"])

            crs_summary = run_crs_pipeline(repository)

            return Response({'message': 'CRS pipeline complete', 'crs': crs_summary})

        except Exception as e:
            logger.error("CRS pipeline failed: %s", e, exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response({'error': str(e), 'type': type(e).__name__}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ---- FIXED: unique name + url path stays crs/ingest ----
    @decorators.action(detail=True, methods=['post'], url_path='crs/ingest')
    def crs_ingest(self, request, pk=None, system_pk=None):
        """
        Full ingestion: Clone repository and run CRS pipeline

        POST /api/systems/{system_id}/repositories/{repo_id}/crs/ingest/
        """
        repository = self.get_object()

        try:
            if not request.user.github_token:
                return Response({
                    'error': 'GitHub token not configured',
                    'message': 'Please connect your GitHub account first'
                }, status=status.HTTP_400_BAD_REQUEST)

            repository.status = 'cloning'
            repository.save(update_fields=["status"])

            clone_path = self._ensure_repo_clone(repository, request.user)

            py_files = []
            for dirpath, _, filenames in os.walk(clone_path):
                for fn in filenames:
                    if fn.endswith(".py"):
                        py_files.append(os.path.join(dirpath, fn))

            if not py_files:
                repository.status = 'error'
                repository.error_message = 'No Python files found in repository'
                repository.save(update_fields=["status", "error_message"])
                return Response({
                    'error': 'No Python files found',
                    'message': 'Repository was cloned but contains no .py files',
                    'clone_path': clone_path
                }, status=status.HTTP_400_BAD_REQUEST)

            repository.status = 'crs_running'
            repository.save(update_fields=["status"])

            crs_summary = run_crs_pipeline(repository)

            return Response({
                'message': 'Repository ingested successfully',
                'clone': {
                    'path': clone_path,
                    'python_files': len(py_files),
                    'commit_sha': repository.last_commit_sha
                },
                'crs': crs_summary
            })

        except Exception as e:
            logger.error("CRS ingest failed: %s", e, exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response({'error': str(e), 'type': type(e).__name__}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='crs/summary')
    def crs_summary(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        return Response(get_crs_summary(repository))

    @decorators.action(detail=True, methods=['get'], url_path='crs/blueprints')
    def crs_blueprints(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        payload = load_crs_payload(repository, "blueprints")
        if not payload:
            return Response({'error': 'Blueprints not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    @decorators.action(detail=True, methods=['get'], url_path='crs/artifacts')
    def crs_artifacts(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        payload = load_crs_payload(repository, "artifacts")
        if not payload:
            return Response({'error': 'Artifacts not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    @decorators.action(detail=True, methods=['get'], url_path='crs/relationships')
    def crs_relationships(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        payload = load_crs_payload(repository, "relationships")
        if not payload:
            return Response({'error': 'Relationships not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    @decorators.action(detail=True, methods=['post'], url_path='crs/steps/(?P<step_name>[^/.]+)/run')
    def run_crs_step_endpoint(self, request, pk=None, system_pk=None, step_name=None):
        repository = self.get_object()

        try:
            force = bool(request.data.get('force', False))

            if not repository.clone_path or not os.path.isdir(repository.clone_path):
                return Response({
                    'error': 'Repository not cloned',
                    'message': 'Please clone the repository first'
                }, status=status.HTTP_400_BAD_REQUEST)

            result = run_crs_step(repository, step_name, force=force)
            return Response({'message': f'Step {step_name} completed', 'result': result})

        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Step %s failed: %s", step_name, e, exc_info=True)
            return Response({'error': str(e), 'type': type(e).__name__}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='crs/steps/status')
    def crs_steps_status(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        try:
            return Response(get_crs_step_status(repository))
        except Exception as e:
            logger.error("Failed to get step status: %s", e, exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='crs/events')
    def crs_events_stream(self, request, pk=None, system_pk=None):
        from django.http import StreamingHttpResponse

        repository = self.get_object()
        broadcaster = get_broadcaster()

        since = request.GET.get('since')
        if since:
            try:
                since = float(since)
            except (ValueError, TypeError):
                since = None

        def event_stream():
            if since is not None:
                past_events = broadcaster.get_events(repository.id, since=since)
                for event in past_events:
                    yield event.to_sse().encode('utf-8')

            last_check = time.time()
            while True:
                new_events = broadcaster.get_events(repository.id, since=last_check)
                for event in new_events:
                    yield event.to_sse().encode('utf-8')

                last_check = time.time()
                yield b": keepalive\n\n"
                time.sleep(0.5)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Access-Control-Allow-Origin'] = '*'
        response.accepted_renderer = None
        response.accepted_media_type = 'text/event-stream'
        response.renderer_context = {}
        return response

    # =========================================================================
    # KNOWLEDGE AGENT ENDPOINTS
    # =========================================================================

    @decorators.action(detail=True, methods=['post'], url_path='knowledge/extract')
    def extract_knowledge(self, request, pk=None, system_pk=None):
        """
        Trigger repository knowledge extraction

        POST /api/systems/{system_id}/repositories/{repo_id}/knowledge/extract/
        Body: {"force": false}

        Analyzes CRS artifacts to build high-level understanding:
        - Architecture patterns
        - Domain models
        - Coding conventions
        - Design patterns
        - Usage guides
        """
        repository = self.get_object()

        # Check prerequisites
        from agent.services.crs_runner import get_crs_summary
        crs_summary = get_crs_summary(repository)

        if crs_summary.get('status') != 'ready':
            return Response({
                'error': 'CRS must be ready before knowledge extraction',
                'crs_status': crs_summary.get('status'),
                'message': 'Please run CRS pipeline first'
            }, status=status.HTTP_400_BAD_REQUEST)

        force = request.data.get('force', False)

        # Check if already extracted and not forcing
        if repository.knowledge_status == 'ready' and not force:
            return Response({
                'message': 'Knowledge already extracted',
                'knowledge_status': repository.knowledge_status,
                'last_extracted': repository.knowledge_last_extracted
            })

        try:
            # Update status
            repository.knowledge_status = 'extracting'
            repository.save(update_fields=['knowledge_status'])

            # Run extraction
            from agent.services.knowledge_agent import RepositoryKnowledgeAgent
            from django.utils import timezone

            knowledge_agent = RepositoryKnowledgeAgent(repository=repository)
            result = knowledge_agent.analyze_repository()

            # Update repository
            repository.knowledge_status = 'ready' if result.get('status') == 'success' else 'error'
            repository.knowledge_last_extracted = timezone.now()
            repository.knowledge_docs_count = result.get('docs_created', 0)
            repository.save(update_fields=[
                'knowledge_status',
                'knowledge_last_extracted',
                'knowledge_docs_count'
            ])

            return Response({
                'status': 'success',
                'knowledge_docs_created': result.get('docs_created'),
                'duration_ms': result.get('duration_ms'),
                'summary': result.get('summary')
            })

        except Exception as e:
            logger.error(f"Knowledge extraction failed: {e}", exc_info=True)

            repository.knowledge_status = 'error'
            repository.save(update_fields=['knowledge_status'])

            return Response({
                'error': str(e),
                'type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='knowledge/summary')
    def knowledge_summary(self, request, pk=None, system_pk=None):
        """
        Get high-level knowledge summary

        GET /api/systems/{system_id}/repositories/{repo_id}/knowledge/summary/

        Returns repository profile and knowledge statistics
        """
        repository = self.get_object()

        try:
            from agent.services.knowledge_agent import RepositoryKnowledgeAgent

            agent = RepositoryKnowledgeAgent(repository=repository)

            # Get profile
            profile = agent.spec_store.get_doc(kind='repository_profile', spec_id='main')

            # Count docs by kind
            docs_by_kind = {}
            for doc in agent.spec_store.list_docs():
                kind = doc.get('kind')
                docs_by_kind[kind] = docs_by_kind.get(kind, 0) + 1

            return Response({
                'status': repository.knowledge_status,
                'last_extracted': repository.knowledge_last_extracted,
                'docs_count': repository.knowledge_docs_count,
                'profile': profile,
                'docs_by_kind': docs_by_kind,
                'total_docs': sum(docs_by_kind.values())
            })

        except Exception as e:
            logger.error(f"Failed to get knowledge summary: {e}", exc_info=True)
            return Response({
                'error': str(e),
                'type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='knowledge/docs')
    def knowledge_docs(self, request, pk=None, system_pk=None):
        """
        List all knowledge documents

        GET /api/systems/{system_id}/repositories/{repo_id}/knowledge/docs/
        Query params: ?kind=<kind>

        Returns list of knowledge documents, optionally filtered by kind
        """
        repository = self.get_object()
        kind = request.query_params.get('kind')

        try:
            from agent.services.knowledge_agent import RepositoryKnowledgeAgent

            agent = RepositoryKnowledgeAgent(repository=repository)
            docs = agent.spec_store.list_docs(kind=kind)

            return Response({
                'docs': docs,
                'count': len(docs),
                'kind_filter': kind
            })

        except Exception as e:
            logger.error(f"Failed to list knowledge docs: {e}", exc_info=True)
            return Response({
                'error': str(e),
                'type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='knowledge/docs/(?P<kind>[^/.]+)/(?P<spec_id>[^/.]+)')
    def knowledge_doc_detail(self, request, pk=None, system_pk=None, kind=None, spec_id=None):
        """
        Get specific knowledge document

        GET /api/systems/{system_id}/repositories/{repo_id}/knowledge/docs/{kind}/{spec_id}/

        Returns detailed knowledge document
        """
        repository = self.get_object()

        try:
            from agent.services.knowledge_agent import RepositoryKnowledgeAgent

            agent = RepositoryKnowledgeAgent(repository=repository)
            doc = agent.spec_store.get_doc(kind=kind, spec_id=spec_id)

            if not doc:
                return Response({
                    'error': f'Document not found: {kind}/{spec_id}'
                }, status=status.HTTP_404_NOT_FOUND)

            return Response(doc)

        except Exception as e:
            logger.error(f"Failed to get knowledge doc {kind}/{spec_id}: {e}", exc_info=True)
            return Response({
                'error': str(e),
                'type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['put'], url_path='knowledge/docs/(?P<kind>[^/.]+)/(?P<spec_id>[^/.]+)')
    def update_knowledge_doc(self, request, pk=None, system_pk=None, kind=None, spec_id=None):
        """
        Update knowledge document (user edits)

        PUT /api/systems/{system_id}/repositories/{repo_id}/knowledge/docs/{kind}/{spec_id}/
        Body: <knowledge document JSON>

        Allows users to edit and enhance knowledge documents
        """
        repository = self.get_object()

        try:
            from agent.services.knowledge_agent import RepositoryKnowledgeAgent

            agent = RepositoryKnowledgeAgent(repository=repository)

            # Validate payload
            payload = request.data
            if not isinstance(payload, dict):
                return Response({
                    'error': 'Payload must be a JSON object'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Add user edit provenance
            payload.setdefault('provenance', {})
            payload['provenance']['edited_by'] = request.user.username if request.user else 'anonymous'
            payload['provenance']['edit_source'] = 'user_ui'
            payload['provenance']['edited_at'] = timezone.now().isoformat()

            # Update doc
            updated_doc = agent.spec_store.upsert_doc(
                kind=kind,
                spec_id=spec_id,
                payload=payload
            )

            return Response(updated_doc)

        except Exception as e:
            logger.error(f"Failed to update knowledge doc {kind}/{spec_id}: {e}", exc_info=True)
            return Response({
                'error': str(e),
                'type': type(e).__name__
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SystemKnowledgeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SystemKnowledgeSerializer

    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        return SystemKnowledge.objects.filter(system_id=system_id, system__user=self.request.user)


class SystemDocumentationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SystemDocumentationSerializer

    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        return SystemDocumentation.objects.filter(system_id=system_id, system__user=self.request.user)


class TaskViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        if system_id:
            return Task.objects.filter(system_id=system_id, system__user=self.request.user).prefetch_related('affected_repos')
        return Task.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return TaskCreateSerializer
        if self.action == 'list':
            return TaskListSerializer
        return TaskDetailSerializer

    def create(self, request, system_pk=None):
        system = get_object_or_404(System, id=system_pk, user=request.user)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task = serializer.save(system=system, user=request.user, status='pending')

        detail_serializer = TaskDetailSerializer(task)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=['post'])
    def approve(self, request, pk=None, system_pk=None):
        task = self.get_object()

        if task.status != 'awaiting_approval':
            return Response({'error': 'Task is not awaiting approval'}, status=status.HTTP_400_BAD_REQUEST)

        task.approved = True
        task.status = 'executing'
        task.approval_notes = request.data.get('notes', '')
        task.save(update_fields=["approved", "status", "approval_notes", "updated_at"])

        serializer = TaskDetailSerializer(task)
        return Response(serializer.data)

    @decorators.action(detail=True, methods=['post'])
    def reject(self, request, pk=None, system_pk=None):
        task = self.get_object()

        if task.status != 'awaiting_approval':
            return Response({'error': 'Task is not awaiting approval'}, status=status.HTTP_400_BAD_REQUEST)

        task.approved = False
        task.status = 'cancelled'
        task.approval_notes = request.data.get('notes', '')
        task.save(update_fields=["approved", "status", "approval_notes", "updated_at"])

        serializer = TaskDetailSerializer(task)
        return Response(serializer.data)


class AgentMemoryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AgentMemorySerializer

    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        return AgentMemory.objects.filter(system_id=system_id, system__user=self.request.user).order_by('-created_at')


@decorators.api_view(['GET'])
@decorators.permission_classes([IsAuthenticated])
def llm_health(request):
    try:
        llm = get_llm_router()
        health = llm.health_check()
        serializer = LLMHealthSerializer(health)
        return Response(serializer.data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@decorators.api_view(['GET'])
@decorators.permission_classes([IsAuthenticated])
def llm_stats(request):
    """
    GET /api/llm/stats/
    Returns aggregate LLM usage stats for the current user.
    """
    user = request.user
    now = timezone.now()
    window_start = now - timedelta(hours=24)

    logs = LLMRequestLog.objects.filter(user=user)
    window_logs = logs.filter(created_at__gte=window_start)

    total_requests = logs.count()
    error_count = logs.filter(status='error').count()
    error_rate = (error_count / total_requests) if total_requests else 0

    avg_latency = logs.aggregate(avg=Avg('latency_ms')).get('avg')
    avg_latency_24h = window_logs.aggregate(avg=Avg('latency_ms')).get('avg')

    # If your model uses provider_type/model_id, keep these:
    provider_breakdown = list(
        logs.values('provider_type')
        .annotate(
            total_requests=Count('id'),
            avg_latency_ms=Avg('latency_ms'),
            prompt_tokens=Coalesce(Sum('prompt_tokens'), 0),
            completion_tokens=Coalesce(Sum('completion_tokens'), 0),
            total_tokens=Coalesce(Sum('total_tokens'), 0),
        )
        .order_by('-total_requests')
    )

    model_breakdown = list(
        logs.values('provider_type', 'model_id')
        .annotate(
            total_requests=Count('id'),
            avg_latency_ms=Avg('latency_ms'),
            prompt_tokens=Coalesce(Sum('prompt_tokens'), 0),
            completion_tokens=Coalesce(Sum('completion_tokens'), 0),
            total_tokens=Coalesce(Sum('total_tokens'), 0),
        )
        .order_by('-total_requests')[:10]
    )

    top_provider_model = None
    if model_breakdown:
        top = model_breakdown[0]
        top_provider_model = {
            'provider': top.get('provider_type'),
            'model': top.get('model_id'),
            'total_requests': top.get('total_requests'),
        }

    trend_rows = (
        window_logs
        .annotate(hour=TruncHour('created_at'))
        .values('hour')
        .annotate(
            total=Count('id'),
            errors=Count('id', filter=Q(status='error'))
        )
        .order_by('hour')
    )
    last_24h_trend = [
        {
            'hour': row['hour'].isoformat() if row['hour'] else None,
            'total': row['total'],
            'errors': row['errors']
        }
        for row in trend_rows
    ]

    recent_requests = [
        {
            'provider': getattr(log, 'provider_type', None) or getattr(log, 'provider', None),
            'model': getattr(log, 'model_id', None) or getattr(log, 'model', None),
            'status': log.status,
            'latency_ms': log.latency_ms,
            'total_tokens': log.total_tokens,
            'request_type': getattr(log, 'request_type', None),
            'created_at': log.created_at.isoformat()
        }
        for log in logs.order_by('-created_at')[:15]
    ]

    payload = {
        'total_requests': total_requests,
        'error_rate': round(error_rate, 4),
        'avg_latency_ms': (int(avg_latency) if avg_latency is not None else None),
        'requests_24h': window_logs.count(),
        'avg_latency_ms_24h': (int(avg_latency_24h) if avg_latency_24h is not None else None),
        'top_provider_model': top_provider_model,
        'tokens_by_provider_model': model_breakdown,
        'by_provider': provider_breakdown,
        'by_model': model_breakdown,
        'last_24h_trend': last_24h_trend,
        'recent_requests': recent_requests,
    }

    serializer = LLMStatsSerializer(payload)
    return Response(serializer.data)


@decorators.api_view(['GET'])
def api_root(request):
    return Response({
        'version': '1.0',
        'endpoints': {
            'systems': '/api/systems/',
            'llm_health': '/api/llm/health/',
            'llm_stats': '/api/llm/stats/',
            'docs': '/api/docs/',
        }
    })


@method_decorator(csrf_exempt, name='dispatch')
class ChatConversationViewSet(viewsets.ModelViewSet):
    queryset = ChatConversation.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return ChatConversationListSerializer
        return ChatConversationSerializer

    def get_queryset(self):
        qs = ChatConversation.objects.all().order_by('-updated_at')

        conv_type = self.request.query_params.get('type')
        if conv_type:
            qs = qs.filter(conversation_type=conv_type)

        system_id = self.request.query_params.get('system')
        if system_id:
            qs = qs.filter(system_id=system_id)

        repository_id = self.request.query_params.get('repository')
        if repository_id:
            qs = qs.filter(repository_id=repository_id)

        return qs.select_related(
            'system', 'repository', 'user', 'llm_model', 'llm_model__provider'
        ).prefetch_related('messages')


@method_decorator(csrf_exempt, name='dispatch')
class LLMProviderViewSet(viewsets.ModelViewSet):
    serializer_class = LLMProviderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LLMProvider.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @decorators.action(detail=True, methods=['post'])
    def sync_ollama_models(self, request, pk=None):
        provider = self.get_object()
        if provider.provider_type != 'ollama':
            return Response(
                {'error': 'Model sync is only available for Ollama providers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from llm.ollama import OllamaClient
        from llm.router import LLMConfig

        base_url = provider.base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        config = LLMConfig(provider='ollama', model='placeholder', base_url=base_url)
        client = OllamaClient(config)
        models = client.list_models()

        created = 0
        updated = 0
        for model_name in models:
            obj, was_created = LLMModel.objects.get_or_create(
                provider=provider,
                model_id=model_name,
                defaults={'name': model_name}
            )
            if was_created:
                created += 1
            else:
                if obj.name != model_name or not obj.is_active:
                    obj.name = model_name
                    obj.is_active = True
                    obj.save(update_fields=['name', 'is_active'])
                    updated += 1

        return Response({'synced': len(models), 'created': created, 'updated': updated})


@method_decorator(csrf_exempt, name='dispatch')
class LLMModelViewSet(viewsets.ModelViewSet):
    serializer_class = LLMModelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = LLMModel.objects.select_related('provider').filter(provider__user=self.request.user)

        provider_id = self.request.query_params.get('provider')
        provider_type = self.request.query_params.get('provider_type')
        if provider_id:
            qs = qs.filter(provider_id=provider_id)
        if provider_type:
            qs = qs.filter(provider__provider_type=provider_type)

        return qs.order_by('name')

    def perform_create(self, serializer):
        provider = serializer.validated_data.get('provider')
        if provider.user_id != self.request.user.id:
            raise PermissionDenied("Provider does not belong to current user.")
        serializer.save()
