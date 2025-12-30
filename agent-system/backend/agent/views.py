from django.shortcuts import render

# Create your views here.
# agent/views.py
"""
Django REST Framework Views for Agent API
"""

from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings
from pathlib import Path

from agent.models import (
    System, Repository, RepositoryQuestion,
    SystemKnowledge, Task, AgentMemory
)
from agent.serializers import (
    SystemListSerializer, SystemDetailSerializer,
    RepositoryListSerializer, RepositoryDetailSerializer, RepositoryCreateSerializer,
    RepositoryQuestionSerializer, AnswerQuestionsSerializer,
    SystemKnowledgeSerializer, TaskListSerializer, TaskDetailSerializer,
    TaskCreateSerializer, AgentMemorySerializer,
    AnalyzeRepositorySerializer, LLMHealthSerializer,
    RepositoryReasoningTraceSerializer, SystemDocumentationSerializer
)
from agent.services.repo_analyzer import RepositoryAnalyzer
from agent.services.question_generator import QuestionGenerator
from agent.services.knowledge_builder import KnowledgeBuilder
from agent.services.github_client import GitHubClient
from agent.services.documentation_builder import DocumentationBuilder
from agent.services.crs_runner import run_crs_pipeline, load_crs_payload, get_crs_summary
from agent.services.log_buffer import get_logs
from llm.router import get_llm_router
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import logging
import os

logger = logging.getLogger(__name__)


def _get_ai_orchestrator():
    try:
        from agent.services.ai_orchestrator import AIOrchestrator
        return AIOrchestrator()
    except Exception as exc:
        logger.warning("AIOrchestrator unavailable: %s", exc)
        return None

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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def system_logs(request):
    limit = int(request.query_params.get('limit', 200))
    return Response({
        "logs": get_logs(limit=limit)
    })


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
            orchestrator = _get_ai_orchestrator()
            if orchestrator:
                orchestrator.capture_analysis(repository, analysis)
            
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
            orchestrator = _get_ai_orchestrator()
            if orchestrator:
                orchestrator.capture_questions(repository, questions)
            
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
                DocumentationBuilder().upsert_overview(repository.system)

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
                'documentation_updated': True,
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

    @decorators.action(detail=True, methods=['post'], url_path='crs/run')
    def run_crs(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        try:
            repository.status = 'crs_running'
            repository.save(update_fields=["status"])
            self._ensure_repo_clone(repository, request.user)
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
                {'error': str(e)},
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
            return Response({'error': 'Relationships not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)

    @decorators.action(detail=True, methods=['get'], url_path='reasoning')
    def reasoning(self, request, pk=None, system_pk=None):
        repository = self.get_object()
        traces = repository.reasoning_traces.all()
        serializer = RepositoryReasoningTraceSerializer(traces, many=True)
        return Response(serializer.data)


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
            'docs': '/api/docs/',
        }
    })
