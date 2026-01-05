# agent/serializers.py
"""
Django REST Framework Serializers for Agent API
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from agent.models import (
    System, Repository, RepositoryQuestion,
    SystemKnowledge, Task, AgentMemory,
    SystemDocumentation,
    ChatConversation, ChatMessage, LLMProvider, LLMModel,
    AgentSession, BenchmarkRun, ToolDefinition, AgentProfile, ContextFile
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
            'id', 'name', 'description', 'status',
            'repositories_count', 'knowledge_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
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
            'id', 'name', 'github_url', 'status',
            'questions_count', 'questions_answered',
            'last_synced_at', 'created_at'
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
            'clone_path', 'local_path',
            'status', 'error_message',
            'analysis', 'config',
            'questions_count', 'questions_answered',
            'last_synced_at', 'last_commit_sha',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'clone_path',
            'status', 'analysis', 'config',
            'created_at', 'updated_at'
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
            'id', 'name', 'description', 'status',
            'intent_constraints',
            'repositories', 'knowledge_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at'
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


class SystemDocumentationSerializer(serializers.ModelSerializer):
    """System documentation serializer"""

    class Meta:
        model = SystemDocumentation
        fields = ['id', 'doc_type', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
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


class BenchmarkRunSerializer(serializers.ModelSerializer):
    system_name = serializers.CharField(source='system.name', read_only=True)

    class Meta:
        model = BenchmarkRun
        fields = [
            'run_id',
            'system',
            'system_name',
            'selected_models',
            'agent_modes',
            'suite_definition',
            'run_jsonl_path',
            'context_trace_path',
            'report_output_path',
            'status',
            'current_phase',
            'progress',
            'report_metrics',
            'report_artifacts',
            'error_message',
            'created_at',
            'started_at',
            'completed_at',
            'updated_at',
        ]
        read_only_fields = [
            'run_id',
            'status',
            'current_phase',
            'progress',
            'report_metrics',
            'report_artifacts',
            'error_message',
            'created_at',
            'started_at',
            'completed_at',
            'updated_at',
        ]


class BenchmarkRunCreateSerializer(serializers.Serializer):
    system_id = serializers.IntegerField(required=False, allow_null=True)
    selected_models = serializers.JSONField()
    agent_modes = serializers.JSONField()
    suite_definition = serializers.JSONField()
    run_jsonl_path = serializers.CharField(required=False, allow_blank=True)
    context_trace_path = serializers.CharField(required=False, allow_blank=True)
    report_output_path = serializers.CharField(required=False, allow_blank=True)


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


class LLMStatsSerializer(serializers.Serializer):
    """Serializer for LLM stats response"""

    total_requests = serializers.IntegerField()
    error_rate = serializers.FloatField()
    avg_latency_ms = serializers.FloatField(allow_null=True)
    top_provider_model = serializers.DictField(allow_null=True)
    tokens_by_provider_model = serializers.ListField(child=serializers.DictField())
    last_24h_trend = serializers.ListField(child=serializers.DictField())
    recent_requests = serializers.ListField(child=serializers.DictField())


class LLMProviderSerializer(serializers.ModelSerializer):
    """Serializer for LLM provider configuration"""

    class Meta:
        model = LLMProvider
        fields = [
            'id', 'name', 'provider_type', 'base_url', 'api_key',
            'metadata', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LLMModelSerializer(serializers.ModelSerializer):
    """Serializer for LLM model configuration"""

    provider_name = serializers.CharField(source='provider.name', read_only=True)
    provider_type = serializers.CharField(source='provider.provider_type', read_only=True)

    class Meta:
        model = LLMModel
        fields = [
            'id', 'provider', 'provider_name', 'provider_type',
            'name', 'model_id', 'context_window', 'metadata',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChatMessageSerializer(serializers.ModelSerializer):
    """Chat message serializer"""
    
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'context_used', 'model_info', 'created_at']
        read_only_fields = ['id', 'created_at']


class ContextFileSerializer(serializers.ModelSerializer):
    """Context file serializer"""

    class Meta:
        model = ContextFile
        fields = ['id', 'conversation', 'file', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']


class ChatConversationSerializer(serializers.ModelSerializer):
    """Chat conversation serializer with messages"""
    
    messages = ChatMessageSerializer(many=True, read_only=True)
    repository_name = serializers.CharField(source='repository.name', read_only=True, allow_null=True)
    system_name = serializers.CharField(source='system.name', read_only=True)
    llm_model_name = serializers.CharField(source='llm_model.name', read_only=True, allow_null=True)
    llm_model_id = serializers.CharField(source='llm_model.model_id', read_only=True, allow_null=True)
    llm_provider_name = serializers.CharField(source='llm_model.provider.name', read_only=True, allow_null=True)
    llm_provider_type = serializers.CharField(source='llm_model.provider.provider_type', read_only=True, allow_null=True)
    
    class Meta:
        model = ChatConversation
        fields = [
            'id', 'conversation_type', 'title', 'repository', 'repository_name',
            'system', 'system_name', 'model_provider', 'llm_model',
            'llm_model_name', 'llm_model_id', 'llm_provider_name', 'llm_provider_type',
            'created_at', 'updated_at', 'messages'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChatConversationListSerializer(serializers.ModelSerializer):
    """Chat conversation list serializer (without messages)"""
    
    repository_name = serializers.CharField(source='repository.name', read_only=True, allow_null=True)
    system_name = serializers.CharField(source='system.name', read_only=True)
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    llm_model_name = serializers.CharField(source='llm_model.name', read_only=True, allow_null=True)
    llm_model_id = serializers.CharField(source='llm_model.model_id', read_only=True, allow_null=True)
    llm_provider_name = serializers.CharField(source='llm_model.provider.name', read_only=True, allow_null=True)
    llm_provider_type = serializers.CharField(source='llm_model.provider.provider_type', read_only=True, allow_null=True)
    
    class Meta:
        model = ChatConversation
        fields = [
            'id', 'conversation_type', 'title', 'repository', 'repository_name',
            'system', 'system_name', 'model_provider', 'llm_model',
            'llm_model_name', 'llm_model_id', 'llm_provider_name', 'llm_provider_type',
            'message_count', 'last_message',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_message_count(self, obj):
        return obj.messages.count()
    
    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'role': last_msg.role,
                'content': last_msg.content[:100] + '...' if len(last_msg.content) > 100 else last_msg.content,
                'created_at': last_msg.created_at
            }
        return None


class AgentSessionSerializer(serializers.ModelSerializer):
    """Agent session serializer for debugging and replay"""
    
    repository_name = serializers.CharField(source='repository.name', read_only=True)
    conversation_title = serializers.CharField(source='conversation.title', read_only=True)
    llm_model_name = serializers.CharField(source='llm_model_used.name', read_only=True, allow_null=True)
    
    class Meta:
        model = AgentSession
        fields = [
            'id', 'session_id', 'session_type', 'intent_classified_as',
            'user_request', 'status', 'plan', 'steps',
            'final_answer', 'artifacts_used', 'tools_called',
            'duration_ms', 'error_message', 'knowledge_context',
            'repository', 'repository_name',
            'conversation', 'conversation_title',
            'llm_model_used', 'llm_model_name',
            'created_at', 'completed_at'
        ]
        read_only_fields = ['id', 'session_id', 'created_at', 'completed_at']


class AgentSessionListSerializer(serializers.ModelSerializer):
    """Agent session list serializer (minimal)"""
    
    repository_name = serializers.CharField(source='repository.name', read_only=True)
    step_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AgentSession
        fields = [
            'id', 'session_id', 'session_type', 'status',
            'user_request', 'duration_ms',
            'repository', 'repository_name',
            'step_count', 'created_at', 'completed_at'
        ]
        read_only_fields = ['id', 'session_id', 'created_at', 'completed_at']
    
    def get_step_count(self, obj):
        return len(obj.steps) if obj.steps else 0


class ToolDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ['id', 'name', 'category', 'description', 'enabled', 'created_at']
        read_only_fields = ['id', 'created_at']


class AgentProfileSerializer(serializers.ModelSerializer):
    tools = ToolDefinitionSerializer(many=True, read_only=True)
    tool_ids = serializers.PrimaryKeyRelatedField(
        source='tools', 
        many=True, 
        queryset=ToolDefinition.objects.all(), 
        write_only=True,
        required=False
    )
    default_model_name = serializers.CharField(source='default_model.name', read_only=True)
    
    class Meta:
        model = AgentProfile
        fields = [
            'id', 'name', 'description', 'system_prompt_template',
            'default_model', 'default_model_name', 'temperature',
            'tools', 'tool_ids',
            'knowledge_scope',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

