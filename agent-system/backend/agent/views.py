from django.shortcuts import render

# Create your views here.
# agent/views.py
"""
Django REST Framework Views for Agent API
"""

from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Avg, Count
from django.db.models import Avg, Count, Sum, Q
from django.db.models.functions import TruncHour, Coalesce
from django.conf import settings
from django.utils import timezone
from pathlib import Path
from datetime import timedelta

from agent.models import (
    System, Repository, RepositoryQuestion,
    SystemKnowledge, Task, AgentMemory,
    ChatConversation, ChatMessage, LLMProvider, LLMModel, LLMRequestLog
)
from agent.serializers import (
    SystemListSerializer, SystemDetailSerializer,
    RepositoryListSerializer, RepositoryDetailSerializer, RepositoryCreateSerializer,
    RepositoryQuestionSerializer, AnswerQuestionsSerializer,
    SystemKnowledgeSerializer, TaskListSerializer, TaskDetailSerializer,
    TaskCreateSerializer, AgentMemorySerializer,
   
    AnalyzeRepositorySerializer, LLMHealthSerializer, LLMStatsSerializer, ChatConversationListSerializer,
    RepositoryReasoningTraceSerializer, SystemDocumentationSerializer, ChatConversationSerializer,
    LLMProviderSerializer, LLMModelSerializer
)
from agent.services.repo_analyzer import RepositoryAnalyzer
from agent.services.question_generator import QuestionGenerator
from agent.services.knowledge_builder import KnowledgeBuilder
from agent.services.github_client import GitHubClient
from agent.services.crs_runner import (
    run_crs_pipeline, load_crs_payload, get_crs_summary,
    run_crs_step, get_crs_step_status
)
from core.events import get_broadcaster
from llm.router import get_llm_router
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import logging
import os

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class SystemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing systems
    
    list: Get all systems for current user
    retrieve: Get single system with repositories
    create: Create new system
    update: Update system
    destroy: Delete system
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
    
    list: Get all repositories in a system
    retrieve: Get single repository with details
    create: Add repository to system
    update: Update repository
    destroy: Remove repository
    analyze: Trigger LLM analysis
    questions: Get questions for repository
    submit_answers: Submit answers to questions
    """
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        if system_id:
            return Repository.objects.filter(
                system_id=system_id,
                system__user=self.request.user
            ).select_related('system')
        return Repository.objects.filter(system__user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return RepositoryCreateSerializer
        elif self.action == 'list':
            return RepositoryListSerializer
        return RepositoryDetailSerializer
    
    def create(self, request, system_pk=None):
        """Create repository in a system"""
        system = get_object_or_404(
            System,
            id=system_pk,
            user=request.user
        )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        repository = serializer.save(system=system)
        
        # Return full detail
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
        """
        Trigger LLM analysis of repository
        
        POST /api/systems/{system_id}/repositories/{repo_id}/analyze/
        Body: {"force": false}
        """
        repository = self.get_object()
        
        serializer = AnalyzeRepositorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        force = serializer.validated_data.get('force', False)
        
        # Check if already analyzed
        if repository.status in ['questions_generated', 'questions_answered', 'ready'] and not force:
            return Response({
                'message': 'Repository already analyzed',
                'status': repository.status,
                'analysis': repository.analysis
            })
        
        try:
            # Update status
            repository.status = 'analyzing'
            repository.save()

            # Ensure repository clone exists
            self._ensure_repo_clone(repository, request.user)
            
            # Analyze
            analyzer = RepositoryAnalyzer()
            analysis = analyzer.analyze(
                repo_path=repository.clone_path,
                repo_name=repository.name
            )
            AIOrchestrator().capture_analysis(repository, analysis)
            
            # Save analysis
            repository.analysis = analysis
            repository.status = 'analyzing'
            repository.save()
            
            # Generate questions
            generator = QuestionGenerator()
            
            # Get other repos for cross-repo questions
            other_repos = [
                {'name': r.name, 'paradigm': r.config.get('paradigm', 'unknown')}
                for r in repository.system.repositories.exclude(id=repository.id)
            ]
            
            questions = generator.generate_questions(
                repo_name=repository.name,
                analysis=analysis,
                other_repos=other_repos
            )
            AIOrchestrator().capture_questions(repository, questions)
            
            # Save questions
            repository.questions.all().delete()  # Clear old questions
            
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
            repository.save()
            
            return Response({
                'message': 'Analysis complete',
                'analysis': analysis,
                'questions_count': len(questions)
            })
        
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save()
            
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @decorators.action(detail=True, methods=['get'])
    def questions(self, request, pk=None, system_pk=None):
        """
        Get questions for repository
        
        GET /api/systems/{system_id}/repositories/{repo_id}/questions/
        """
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
        """
        Submit answers to questions
        
        POST /api/systems/{system_id}/repositories/{repo_id}/submit_answers/
        Body: {"answers": {"question_key": "answer", ...}}
        """
        repository = self.get_object()
        
        serializer = AnswerQuestionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        answers = serializer.validated_data['answers']
        
        try:
            with transaction.atomic():
                # Save answers
                for question in repository.questions.all():
                    if question.question_key in answers:
                        question.answer = answers[question.question_key]
                        question.save()

                # Build knowledge
                builder = KnowledgeBuilder()
                config = builder.build_repo_knowledge(repository, answers)

                # Build system knowledge
                all_repos = list(repository.system.repositories.all())
                knowledge_items = builder.build_system_knowledge(
                    repository.system,
                    all_repos
                )

                # Update system status
                if repository.system.status == 'initializing':
                    repository.system.status = 'ready'
                    repository.system.save()

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
            logger.error(f"Failed to process answers: {e}", exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['post'], url_path='clone')
    def clone_repository(self, request, pk=None, system_pk=None):
        """
        Clone GitHub repository to local workspace

        POST /api/systems/{system_id}/repositories/{repo_id}/clone/
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

            # Count Python files
            import os
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
            logger.error(f"Clone failed: {e}", exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response(
                {'error': str(e), 'details': 'Failed to clone repository'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['get'], url_path='status')
    def repo_status(self, request, pk=None, system_pk=None):
        """
        Get detailed repository status

        GET /api/systems/{system_id}/repositories/{repo_id}/status/
        """
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

        # Check Python files if cloned
        if status_info['clone_exists']:
            py_files = []
            for dirpath, _, filenames in os.walk(repository.clone_path):
                for fn in filenames:
                    if fn.endswith(".py"):
                        py_files.append(fn)
            status_info['python_files_count'] = len(py_files)
            status_info['ready_for_crs'] = len(py_files) > 0
        else:
            status_info['python_files_count'] = 0
            status_info['ready_for_crs'] = False

        return Response(status_info)

    @decorators.action(detail=True, methods=['post'], url_path='ingest')
    def ingest_repository(self, request, pk=None, system_pk=None):
        """
        Complete repository ingestion: Clone + CRS setup

        This endpoint combines cloning and initial CRS workspace setup in one call.
        Use this when adding a new repository to ensure it's ready for CRS analysis.

        POST /api/systems/{system_id}/repositories/{repo_id}/ingest/
        Body: {"force_reclone": false}
        """
        repository = self.get_object()

        try:
            force_reclone = request.data.get('force_reclone', False)

            # Step 1: Ensure repository is cloned
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

                # Count Python files
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

            # Step 2: Build CRS workspace (creates config.json, validates paths)
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
            logger.error(f"Ingestion failed: {e}", exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response(
                {'error': str(e), 'details': 'Failed to ingest repository'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['post'], url_path='crs/run')
    def run_crs(self, request, pk=None, system_pk=None):
        """
        Run CRS pipeline on repository

        POST /api/systems/{system_id}/repositories/{repo_id}/crs/run/
        """
        repository = self.get_object()
        try:
            # Ensure clone exists first
            if not repository.clone_path or not os.path.isdir(repository.clone_path):
                return Response({
                    'error': 'Repository not cloned',
                    'message': 'Please clone the repository first using /clone/ endpoint'
                }, status=status.HTTP_400_BAD_REQUEST)

            repository.status = 'crs_running'
            repository.save(update_fields=["status"])

            crs_summary = run_crs_pipeline(repository)

            return Response({
                'message': 'CRS pipeline complete',
                'crs': crs_summary
            })
        except Exception as e:
            logger.error(f"CRS pipeline failed: {e}", exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response(
                {'error': str(e), 'type': type(e).__name__},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['post'], url_path='crs/ingest')
    def ingest_repository(self, request, pk=None, system_pk=None):
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

            # Step 1: Clone
            repository.status = 'cloning'
            repository.save(update_fields=["status"])

            clone_path = self._ensure_repo_clone(repository, request.user)

            # Count Python files
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
                    'message': f'Repository was cloned but contains no .py files',
                    'clone_path': clone_path
                }, status=status.HTTP_400_BAD_REQUEST)

            # Step 2: Run CRS
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
            logger.error(f"Ingestion failed: {e}", exc_info=True)
            repository.status = 'error'
            repository.error_message = str(e)
            repository.save(update_fields=["status", "error_message"])
            return Response(
                {'error': str(e), 'type': type(e).__name__},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['get'], url_path='crs/summary')
    def crs_summary(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        summary = get_crs_summary(repository)
        return Response(summary)

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
            return Response({'error': 'Artifacts not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    @decorators.action(detail=True, methods=['post'], url_path='crs/steps/(?P<step_name>[^/.]+)/run')
    def run_crs_step_endpoint(self, request, pk=None, system_pk=None, step_name=None):
        """
        Run individual CRS pipeline step with real-time events

        POST /api/systems/{system_id}/repositories/{repo_id}/crs/steps/{step_name}/run/
        Body: {"force": false}

        Steps: blueprints, artifacts, relationships, impact, verification_{suite_id}
        """
        repository = self.get_object()

        try:
            force = request.data.get('force', False)

            # Validate repository is ready
            if not repository.clone_path or not os.path.isdir(repository.clone_path):
                return Response({
                    'error': 'Repository not cloned',
                    'message': 'Please clone the repository first'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Run the step
            result = run_crs_step(repository, step_name, force=force)

            return Response({
                'message': f'Step {step_name} completed',
                'result': result
            })

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Step {step_name} failed: {e}", exc_info=True)
            return Response(
                {'error': str(e), 'type': type(e).__name__},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['get'], url_path='crs/steps/status')
    def crs_steps_status(self, request, pk=None, system_pk=None):
        """
        Get status of all CRS pipeline steps

        GET /api/systems/{system_id}/repositories/{repo_id}/crs/steps/status/

        Returns which steps need to run and current state
        """
        repository = self.get_object()

        try:
            status_info = get_crs_step_status(repository)
            return Response(status_info)
        except Exception as e:
            logger.error(f"Failed to get step status: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=True, methods=['get'], url_path='crs/events')
    def crs_events_stream(self, request, pk=None, system_pk=None):
        """
        Server-Sent Events stream for CRS pipeline events

        GET /api/systems/{system_id}/repositories/{repo_id}/crs/events/
        Query params: ?since=<timestamp>

        Streams real-time events during CRS execution
        """
        from django.http import StreamingHttpResponse
        import time

        repository = self.get_object()
        broadcaster = get_broadcaster()

        # Get since parameter for resuming stream
        since = request.GET.get('since')
        if since:
            try:
                since = float(since)
            except (ValueError, TypeError):
                since = None

        def event_stream():
            """Generate SSE event stream"""
            # Send initial events if resuming
            if since is not None:
                past_events = broadcaster.get_events(repository.id, since=since)
                for event in past_events:
                    yield event.to_sse().encode('utf-8')

            # Stream new events
            last_check = time.time()
            while True:
                # Get new events since last check
                new_events = broadcaster.get_events(repository.id, since=last_check)
                for event in new_events:
                    yield event.to_sse().encode('utf-8')

                last_check = time.time()

                # Send keepalive comment every 30 seconds
                yield b": keepalive\n\n"

                # Small delay to avoid busy loop
                time.sleep(0.5)

        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
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
    """
    API endpoint for viewing system knowledge
    
    list: Get all knowledge for a system
    retrieve: Get single knowledge item
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = SystemKnowledgeSerializer
    
    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        return SystemKnowledge.objects.filter(
            system_id=system_id,
            system__user=self.request.user
        )


class SystemDocumentationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing system documentation
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SystemDocumentationSerializer

    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        return SystemDocumentation.objects.filter(
            system_id=system_id,
            system__user=self.request.user
        )


class TaskViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing tasks
    
    list: Get all tasks for a system
    retrieve: Get single task
    create: Create new task
    approve: Approve task
    reject: Reject task
    """
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        if system_id:
            return Task.objects.filter(
                system_id=system_id,
                system__user=self.request.user
            ).prefetch_related('affected_repos')
        return Task.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return TaskCreateSerializer
        elif self.action == 'list':
            return TaskListSerializer
        return TaskDetailSerializer
    
    def create(self, request, system_pk=None):
        """Create a new task"""
        system = get_object_or_404(
            System,
            id=system_pk,
            user=request.user
        )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        task = serializer.save(
            system=system,
            user=request.user,
            status='pending'
        )
        
        # Return full detail
        detail_serializer = TaskDetailSerializer(task)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
    
    @decorators.action(detail=True, methods=['post'])
    def approve(self, request, pk=None, system_pk=None):
        """Approve a task"""
        task = self.get_object()
        
        if task.status != 'awaiting_approval':
            return Response(
                {'error': 'Task is not awaiting approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task.approved = True
        task.status = 'executing'
        task.approval_notes = request.data.get('notes', '')
        task.save()
        
        # TODO: Trigger task execution
        
        serializer = TaskDetailSerializer(task)
        return Response(serializer.data)
    
    @decorators.action(detail=True, methods=['post'])
    def reject(self, request, pk=None, system_pk=None):
        """Reject a task"""
        task = self.get_object()
        
        if task.status != 'awaiting_approval':
            return Response(
                {'error': 'Task is not awaiting approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task.approved = False
        task.status = 'cancelled'
        task.approval_notes = request.data.get('notes', '')
        task.save()
        
        serializer = TaskDetailSerializer(task)
        return Response(serializer.data)


class AgentMemoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing agent memory
    
    list: Get all memories for a system
    retrieve: Get single memory
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = AgentMemorySerializer
    
    def get_queryset(self):
        system_id = self.kwargs.get('system_pk')
        return AgentMemory.objects.filter(
            system_id=system_id,
            system__user=self.request.user
        ).order_by('-created_at')


@decorators.api_view(['GET'])
@decorators.permission_classes([IsAuthenticated])
def llm_health(request):
    """
    Check LLM health status
    
    GET /api/llm/health/
    """
    try:
        llm = get_llm_router()
        health = llm.health_check()
        
        serializer = LLMHealthSerializer(health)
        return Response(serializer.data)
    
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@decorators.api_view(['GET'])
@decorators.permission_classes([IsAuthenticated])
def llm_stats(request):
    """
    LLM usage statistics for current user
    """
    user = request.user
    now = timezone.now()
    window_start = now - timezone.timedelta(hours=24)

    base_qs = LLMRequestLog.objects.filter(user=user)
    window_qs = base_qs.filter(created_at__gte=window_start)

    totals = base_qs.aggregate(
        total_requests=Count('id'),
        avg_latency_ms=Avg('latency_ms'),
    )
    window_totals = window_qs.aggregate(
        requests_24h=Count('id'),
        avg_latency_ms_24h=Avg('latency_ms'),
    )

    error_count = base_qs.filter(status='error').count()
    error_rate = (error_count / totals['total_requests']) if totals['total_requests'] else 0

    by_provider = list(
        base_qs.values('provider_type')
        .annotate(
            requests=Count('id'),
            avg_latency_ms=Avg('latency_ms')
        )
        .order_by('-requests')
    )

    by_model = list(
        base_qs.values('provider_type', 'model_id')
        .annotate(
            requests=Count('id'),
            avg_latency_ms=Avg('latency_ms')
        )
        .order_by('-requests')[:10]
    )

    return Response({
        'total_requests': totals['total_requests'] or 0,
        'avg_latency_ms': int(totals['avg_latency_ms']) if totals['avg_latency_ms'] else None,
        'error_rate': round(error_rate, 4),
        'requests_24h': window_totals['requests_24h'] or 0,
        'avg_latency_ms_24h': int(window_totals['avg_latency_ms_24h']) if window_totals['avg_latency_ms_24h'] else None,
        'by_provider': by_provider,
        'by_model': by_model
    })
    LLM stats endpoint

    GET /api/llm/stats/
    """
    logs = LLMRequestLog.objects.filter(user=request.user)
    total_requests = logs.count()
    error_count = logs.filter(status='error').count()
    error_rate = error_count / total_requests if total_requests else 0
    avg_latency = logs.aggregate(avg=Avg('latency_ms')).get('avg')

    provider_stats = list(
        logs.values('provider', 'model')
        .annotate(
            total_requests=Count('id'),
            prompt_tokens=Coalesce(Sum('prompt_tokens'), 0),
            completion_tokens=Coalesce(Sum('completion_tokens'), 0),
            total_tokens=Coalesce(Sum('total_tokens'), 0),
            avg_latency_ms=Avg('latency_ms')
        )
        .order_by('-total_requests')
    )

    top_provider_model = None
    if provider_stats:
        top = provider_stats[0]
        top_provider_model = {
            'provider': top.get('provider'),
            'model': top.get('model'),
            'total_requests': top.get('total_requests')
        }

    since = timezone.now() - timedelta(hours=24)
    trend_rows = (
        logs.filter(created_at__gte=since)
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
            'provider': log.provider,
            'model': log.model,
            'status': log.status,
            'latency_ms': log.latency_ms,
            'total_tokens': log.total_tokens,
            'request_type': log.request_type,
            'created_at': log.created_at.isoformat()
        }
        for log in logs.order_by('-created_at')[:15]
    ]

    payload = {
        'total_requests': total_requests,
        'error_rate': error_rate,
        'avg_latency_ms': avg_latency,
        'top_provider_model': top_provider_model,
        'tokens_by_provider_model': provider_stats,
        'last_24h_trend': last_24h_trend,
        'recent_requests': recent_requests
    }

    serializer = LLMStatsSerializer(payload)
    return Response(serializer.data)


@decorators.api_view(['GET'])
def api_root(request):
    """
    API root endpoint
    
    GET /api/
    """
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
    """
    API endpoint for chat conversations
    
    list: Get all conversations (filtered by type, system, or repository)
    retrieve: Get single conversation with full message history
    create: Create new conversation
    destroy: Delete conversation
    """
    
    queryset = ChatConversation.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ChatConversationListSerializer
        return ChatConversationSerializer
    
    def get_queryset(self):
        queryset = ChatConversation.objects.all().order_by('-updated_at')
        
        # Filter by conversation type
        conv_type = self.request.query_params.get('type')
        if conv_type:
            queryset = queryset.filter(conversation_type=conv_type)
        
        # Filter by system
        system_id = self.request.query_params.get('system')
        if system_id:
            queryset = queryset.filter(system_id=system_id)
        
        # Filter by repository
        repository_id = self.request.query_params.get('repository')
        if repository_id:
            queryset = queryset.filter(repository_id=repository_id)
        
        return queryset.select_related('system', 'repository', 'user', 'llm_model', 'llm_model__provider').prefetch_related('messages')


@method_decorator(csrf_exempt, name='dispatch')
class LLMProviderViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing LLM providers
    """

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

        return Response({
            'synced': len(models),
            'created': created,
            'updated': updated
        })


@method_decorator(csrf_exempt, name='dispatch')
class LLMModelViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing LLM models
    """

    serializer_class = LLMModelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LLMModel.objects.select_related('provider').filter(provider__user=self.request.user)

        provider_id = self.request.query_params.get('provider')
        provider_type = self.request.query_params.get('provider_type')
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)
        if provider_type:
            queryset = queryset.filter(provider__provider_type=provider_type)

        return queryset.order_by('name')

    def perform_create(self, serializer):
        provider = serializer.validated_data.get('provider')
        if provider.user_id != self.request.user.id:
            raise PermissionDenied("Provider does not belong to current user.")
        serializer.save()
