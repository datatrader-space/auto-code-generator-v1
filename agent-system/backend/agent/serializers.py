# agent/serializers.py
"""
Django REST Framework Serializers for Agent API
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from agent.models import (
    System, Repository, RepositoryQuestion, 
    SystemKnowledge, Task, AgentMemory
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """User serializer"""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'slack_user_id', 'github_username', 'created_at']
        read_only_fields = ['id', 'created_at']


class SystemListSerializer(serializers.ModelSerializer):
    """System list serializer (minimal)"""
    
    repositories_count = serializers.SerializerMethodField()
    knowledge_count = serializers.SerializerMethodField()
    
    class Meta:
        model = System
        fields = [
            'id', 'name', 'slug', 'description', 'status',
            'repositories_count', 'knowledge_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
    
    def get_repositories_count(self, obj):
        return obj.repositories.count()
    
    def get_knowledge_count(self, obj):
        return obj.knowledge.count()


class RepositoryListSerializer(serializers.ModelSerializer):
    """Repository list serializer (minimal)"""
    
    questions_count = serializers.SerializerMethodField()
    questions_answered = serializers.SerializerMethodField()
    
    class Meta:
        model = Repository
        fields = [
            'id', 'name', 'github_url', 'status', 'crs_status',
            'questions_count', 'questions_answered',
            'artifacts_count', 'relationships_count',
            'last_synced', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_questions_count(self, obj):
        return obj.questions.count()
    
    def get_questions_answered(self, obj):
        return obj.questions.filter(answer__isnull=False).count()


class RepositoryDetailSerializer(serializers.ModelSerializer):
    """Repository detail serializer (full)"""
    
    questions_count = serializers.SerializerMethodField()
    questions_answered = serializers.SerializerMethodField()
    
    class Meta:
        model = Repository
        fields = [
            'id', 'system', 'name', 'github_url', 'github_branch',
            'clone_path', 'crs_workspace_path',
            'status', 'error_message', 'crs_status',
            'analysis', 'config',
            'artifacts_count', 'relationships_count',
            'questions_count', 'questions_answered',
            'last_synced', 'last_commit_sha', 'last_crs_run',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'clone_path', 'crs_workspace_path', 
            'status', 'analysis', 'config',
            'artifacts_count', 'relationships_count',
            'last_crs_run', 'created_at', 'updated_at'
        ]
    
    def get_questions_count(self, obj):
        return obj.questions.count()
    
    def get_questions_answered(self, obj):
        return obj.questions.filter(answer__isnull=False).count()


class RepositoryCreateSerializer(serializers.ModelSerializer):
    """Repository creation serializer"""
    
    class Meta:
        model = Repository
        fields = ['name', 'github_url', 'github_branch']
    
    def validate_github_url(self, value):
        """Validate GitHub URL format"""
        if not value.startswith('https://github.com/'):
            raise serializers.ValidationError("Must be a valid GitHub URL")
        return value


class SystemDetailSerializer(serializers.ModelSerializer):
    """System detail serializer (full)"""
    
    repositories = RepositoryListSerializer(many=True, read_only=True)
    knowledge_count = serializers.SerializerMethodField()
    
    class Meta:
        model = System
        fields = [
            'id', 'name', 'slug', 'description', 'status',
            'workspace_path', 'system_spec_path',
            'intent_constraints',
            'repositories', 'knowledge_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'slug', 'workspace_path', 'system_spec_path',
            'created_at', 'updated_at'
        ]
    
    def get_knowledge_count(self, obj):
        return obj.knowledge.count()


class RepositoryQuestionSerializer(serializers.ModelSerializer):
    """Repository question serializer"""
    
    class Meta:
        model = RepositoryQuestion
        fields = [
            'id', 'question_key', 'question_text', 'question_type',
            'options', 'answer', 'required', 'category', 'order',
            'answered_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'question_key', 'question_text', 'question_type',
            'options', 'required', 'category', 'order', 'created_at'
        ]


class AnswerQuestionsSerializer(serializers.Serializer):
    """Serializer for submitting multiple answers"""
    
    answers = serializers.JSONField(help_text="Dictionary of question_key: answer")
    
    def validate_answers(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Answers must be a dictionary")
        return value


class SystemKnowledgeSerializer(serializers.ModelSerializer):
    """System knowledge serializer"""
    
    class Meta:
        model = SystemKnowledge
        fields = [
            'id', 'knowledge_type', 'spec_id', 'content',
            'source', 'confidence', 'spec_file_path',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TaskListSerializer(serializers.ModelSerializer):
    """Task list serializer (minimal)"""
    
    affected_repos_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Task
        fields = [
            'id', 'description', 'status', 'requires_approval',
            'approved', 'affected_repos_count',
            'created_at', 'started_at', 'completed_at'
        ]
        read_only_fields = ['id', 'created_at', 'started_at', 'completed_at']
    
    def get_affected_repos_count(self, obj):
        return obj.affected_repos.count()


class TaskDetailSerializer(serializers.ModelSerializer):
    """Task detail serializer (full)"""
    
    affected_repos = RepositoryListSerializer(many=True, read_only=True)
    
    class Meta:
        model = Task
        fields = [
            'id', 'system', 'user', 'description', 'status',
            'parsed_intent', 'execution_plan', 'impact_analysis',
            'requires_approval', 'slack_message_ts',
            'approved', 'approved_at', 'approval_notes',
            'changes', 'github_prs', 'error_message',
            'affected_repos',
            'created_at', 'started_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'user', 'parsed_intent', 'execution_plan',
            'impact_analysis', 'slack_message_ts',
            'approved_at', 'changes', 'github_prs',
            'created_at', 'started_at', 'completed_at'
        ]


class TaskCreateSerializer(serializers.ModelSerializer):
    """Task creation serializer"""
    
    class Meta:
        model = Task
        fields = ['description', 'requires_approval']
        
    def validate_description(self, value):
        """Ensure description is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Description cannot be empty")
        return value.strip()


class AgentMemorySerializer(serializers.ModelSerializer):
    """Agent memory serializer"""
    
    class Meta:
        model = AgentMemory
        fields = [
            'id', 'memory_type', 'content', 'confidence',
            'learned_from_task', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AnalyzeRepositorySerializer(serializers.Serializer):
    """Serializer for triggering repository analysis"""
    
    force = serializers.BooleanField(
        default=False,
        help_text="Force re-analysis even if already analyzed"
    )


class LLMHealthSerializer(serializers.Serializer):
    """Serializer for LLM health check response"""
    
    local = serializers.DictField()
    cloud = serializers.DictField()
