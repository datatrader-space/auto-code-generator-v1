from django.db import models

# Create your models here.
# agent/models.py
"""
Core Django models for the Agent System
Supports multi-tenant, multi-repo, heterogeneous architectures
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from django.utils import timezone
import json

import uuid
class User(AbstractUser):
    """Agent system user"""
    
    # Slack integration
    slack_user_id = models.CharField(max_length=100, blank=True)
    slack_workspace_id = models.CharField(max_length=100, blank=True)
    
    # GitHub integration
    github_username = models.CharField(max_length=100, blank=True)
    github_token = models.CharField(max_length=200, blank=True)  # Encrypted in production
    
    # Preferences
    preferences = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'agent_users'
    
    def __str__(self):
        return self.username


class GitHubOAuthConfig(models.Model):
    """Store GitHub OAuth configuration in the database."""

    client_id = models.CharField(max_length=200)
    client_secret = models.CharField(max_length=200)
    callback_url = models.URLField(
        default='http://localhost:8000/api/auth/github/callback'
    )
    scope = models.CharField(max_length=200, default='repo,user')
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_github_oauth_config'
        ordering = ['-created_at']

    def __str__(self):
        return f"GitHub OAuth Config ({self.client_id})"


class LLMProvider(models.Model):
    """Third-party or local LLM provider configuration."""

    PROVIDER_CHOICES = [
        ('ollama', 'Ollama'),
        ('anthropic', 'Anthropic'),
        ('openai', 'OpenAI'),
        ('gemini', 'Google Gemini'),
        ('custom', 'Custom'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='llm_providers')
    name = models.CharField(max_length=200)
    provider_type = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    base_url = models.URLField(blank=True)
    api_key = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'llm_providers'
        unique_together = [['user', 'name']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}/{self.name}"


class LLMModel(models.Model):
    """Model configuration for a specific provider."""

    provider = models.ForeignKey(LLMProvider, on_delete=models.CASCADE, related_name='models')
    name = models.CharField(max_length=200)
    model_id = models.CharField(max_length=200)
    context_window = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'llm_models'
        unique_together = [['provider', 'model_id']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider.name}/{self.name}"


class LLMRequestLog(models.Model):
    """Log of LLM API requests for monitoring and debugging."""

    conversation = models.ForeignKey(
        'ChatConversation',
        on_delete=models.CASCADE,
        related_name='llm_requests',
        null=True,
        blank=True
    )
    model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Request details
    request_type = models.CharField(
        max_length=50,
        choices=[
            ('completion', 'Completion'),
            ('stream', 'Stream'),
            ('embedding', 'Embedding'),
        ]
    )
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)

    # Response details
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('error', 'Error'),
            ('timeout', 'Timeout'),
        ]
    )
    latency_ms = models.IntegerField(help_text='Response time in milliseconds',null=True)
    error_message = models.TextField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'llm_request_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.request_type} | {self.status} | {self.latency_ms}ms"


class System(models.Model):
    """
    A system represents a collection of repositories that work together
    (e.g., microservices, monorepo modules, etc.)
    """
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='systems')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # System-level metadata
    status = models.CharField(
        max_length=50,
        default='initializing',
        choices=[
            ('initializing', 'Initializing'),
            ('ready', 'Ready'),
            ('error', 'Error'),
        ]
    )
    
    # Intent & constraints (user-defined goals)
    intent_constraints = models.JSONField(
        default=dict,
        blank=True,
        help_text='User-defined intent summary and constraints for this system'
    )
    
    # Metrics
    knowledge_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'systems'
        unique_together = [['user', 'name']]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username}/{self.name}"


class Repository(models.Model):
    """
    A repository within a system
    Can be a git repo, local folder, or external source
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='repositories')
    name = models.CharField(max_length=200)
    
    # Source
    github_url = models.URLField(blank=True)
    github_branch = models.CharField(max_length=100, default='main')
    local_path = models.CharField(max_length=500, blank=True)
    clone_path = models.CharField(max_length=500, blank=True)
    
    # Git metadata
    last_commit_sha = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    
    # Analysis status
    status = models.CharField(
        max_length=50,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('analyzing', 'Analyzing'),
            ('questions_generated', 'Questions Generated'),
            ('questions_answered', 'Questions Answered'),
            ('crs_running', 'CRS Running'),
            ('ready', 'Ready'),
            ('error', 'Error'),
        ]
    )
    error_message = models.TextField(blank=True)
    
    # Analysis results
    analysis = models.JSONField(default=dict, blank=True)
    
    # Configuration (paradigm, tech stack, etc.)
    config = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'repositories'
        unique_together = [['system', 'name']]
        ordering = ['name']
    
    def __str__(self):
        return f"{self.system.name}/{self.name}"


class RepositoryQuestion(models.Model):
    """
    Questions generated for a repository to gather context
    """
    
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='questions')
    
    question_key = models.CharField(max_length=100)
    question_text = models.TextField()
    question_type = models.CharField(
        max_length=50,
        choices=[
            ('yes_no', 'Yes/No'),
            ('text', 'Text'),
            ('multiple_choice', 'Multiple Choice'),
            ('list', 'List'),
        ]
    )
    options = models.JSONField(default=list, blank=True)
    required = models.BooleanField(default=False)
    category = models.CharField(max_length=100, blank=True)
    order = models.IntegerField(default=0)
    
    # Answer
    answer = models.JSONField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'repository_questions'
        ordering = ['order', 'created_at']
        unique_together = [['repository', 'question_key']]
    
    def __str__(self):
        return f"{self.repository.name}: {self.question_text[:50]}"


class SystemKnowledge(models.Model):
    """
    Knowledge extracted from the system
    (e.g., architecture patterns, conventions, etc.)
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='knowledge')
    
    knowledge_type = models.CharField(
        max_length=100,
        choices=[
            ('pattern', 'Pattern'),
            ('convention', 'Convention'),
            ('architecture', 'Architecture'),
            ('dependency', 'Dependency'),
        ]
    )
    
    title = models.CharField(max_length=200,null=True)
    description = models.TextField(blank=True,null=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'system_knowledge'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.system.name}: {self.title}"


class Task(models.Model):
    """
    A task represents a unit of work to be done by the agent
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='tasks')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    
    # Task details
    task_id = models.CharField(max_length=100, unique=True, db_index=True,default=str(uuid.uuid1()))
    title = models.CharField(max_length=200,null=True)
    description = models.TextField()
    
    # Status
    status = models.CharField(
        max_length=50,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('planning', 'Planning'),
            ('awaiting_approval', 'Awaiting Approval'),
            ('executing', 'Executing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ]
    )
    
    # Approval workflow
    approved = models.BooleanField(default=False)
    approval_notes = models.TextField(blank=True)
    
    # Execution plan
    plan = models.JSONField(default=dict, blank=True)
    
    # Results
    result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    
    # Affected repositories
    affected_repos = models.ManyToManyField(Repository, related_name='tasks', blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tasks'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.task_id}: {self.title}"


class AgentMemory(models.Model):
    """
    Long-term memory for the agent
    Stores important facts, decisions, and context
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='memories')
    
    memory_type = models.CharField(
        max_length=100,
        choices=[
            ('fact', 'Fact'),
            ('decision', 'Decision'),
            ('preference', 'Preference'),
            ('context', 'Context'),
        ]
    )
    
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    
    # Relevance scoring
    importance = models.IntegerField(default=5, help_text='1-10 scale')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'agent_memories'
        ordering = ['-importance', '-created_at']
    
    def __str__(self):
        return f"{self.memory_type}: {self.content[:50]}"


class SystemDocumentation(models.Model):
    """
    Auto-generated documentation for the system
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='documentation')
    
    doc_type = models.CharField(
        max_length=100,
        choices=[
            ('overview', 'Overview'),
            ('architecture', 'Architecture'),
            ('api', 'API Reference'),
            ('guide', 'Guide'),
        ]
    )
    
    title = models.CharField(max_length=200,null=True)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'system_documentation'
        ordering = ['doc_type', '-created_at']
    
    def __str__(self):
        return f"{self.system.name}: {self.title}"


class ChatConversation(models.Model):
    """
    A conversation thread between user and agent
    """

    CONVERSATION_TYPE_CHOICES = [
        ('repository', 'Repository Chat'),
        ('planner', 'System Planner'),
        ('graph', 'Graph Explorer'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)

    conversation_type = models.CharField(max_length=50, choices=CONVERSATION_TYPE_CHOICES, default='repository')
    title = models.CharField(max_length=200, default='New Conversation')

    # LLM configuration
    model_provider = models.CharField(max_length=50, default='ollama')
    llm_model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations'
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_conversations'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['repository', '-updated_at']),
        ]

    def __str__(self):
        return f"{self.conversation_type}: {self.title}"


class ChatMessage(models.Model):
    """
    A single message in a conversation
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    # Message role
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    # Content
    content = models.TextField()

    # Context used (for assistant messages)
    context_used = models.JSONField(
        null=True,
        blank=True,
        help_text='CRS artifacts/files used to generate response'
    )

    # Model info (for assistant messages)
    model_info = models.JSONField(
        null=True,
        blank=True,
        help_text='Model, provider, tokens used, etc.'
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return f"{self.role}: {preview}"


class AgentSession(models.Model):
    """
    Universal session log for both Chat (RAG) and Task (Autonomous) flows
    Enables full traceability and debugging of agent interactions
    """

    SESSION_TYPE_CHOICES = [
        ('chat', 'Chat (RAG)'),
        ('task', 'Task (Autonomous)'),
        ('hybrid', 'Hybrid (Chat → Task)'),
    ]

    STATUS_CHOICES = [
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    # Identity
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name='agent_sessions'
    )
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='agent_sessions'
    )

    # Classification
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES)
    intent_classified_as = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="'CHAT' or 'TASK' from intent classifier"
    )

    # Request
    user_request = models.TextField(help_text="Original user message")
    created_at = models.DateTimeField(auto_now_add=True)

    # Execution
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    plan = models.JSONField(
        null=True,
        blank=True,
        help_text="Agent execution plan (for tasks)"
    )
    steps = models.JSONField(
        default=list,
        help_text="Execution steps with timing and results"
    )

    # Results
    final_answer = models.TextField(null=True, blank=True)
    artifacts_used = models.JSONField(
        default=list,
        help_text="List of artifact IDs referenced"
    )
    tools_called = models.JSONField(
        default=list,
        help_text="Tools invoked during session"
    )

    # Metadata
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Context snapshot
    knowledge_context = models.JSONField(
        default=dict,
        help_text="Architecture style, domain, etc."
    )
    llm_model_used = models.ForeignKey(
        LLMModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='agent_sessions'
    )

    class Meta:
        db_table = 'agent_sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['repository', '-created_at']),
            models.Index(fields=['session_type', 'status']),
            models.Index(fields=['conversation', '-created_at']),
        ]

    def __str__(self):
        return f"{self.session_type.upper()} | {self.session_id} | {self.status}"


class BenchmarkRun(models.Model):
    """
    Tracks benchmark runs for system/model/mode combinations.
    """

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='benchmark_runs')
    system = models.ForeignKey(
        System,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='benchmark_runs'
    )

    selected_models = models.JSONField(default=list, blank=True)
    agent_modes = models.JSONField(default=list, blank=True)
    suite_definition = models.JSONField(default=dict, blank=True)

    run_jsonl_path = models.CharField(max_length=500, blank=True)
    context_trace_path = models.CharField(max_length=500, blank=True)
    report_output_path = models.CharField(max_length=500, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    current_phase = models.CharField(max_length=200, blank=True)
    progress = models.IntegerField(default=0, help_text='Progress percent 0-100')

    report_metrics = models.JSONField(default=dict, blank=True)
    report_artifacts = models.JSONField(default=list, blank=True)

    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'benchmark_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"BenchmarkRun {self.run_id} | {self.status}"


class ToolDefinition(models.Model):
    """
    Represents a tool available in the system.
    Syncs with the code-based ToolRegistry.
    """
    name = models.CharField(max_length=100, unique=True, help_text="Unique tools identifier (e.g., LIST_ARTIFACTS)")
    category = models.CharField(max_length=100, default="general")
    description = models.TextField(blank=True)
    
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tool_definitions'
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class AgentProfile(models.Model):
    """
    Defines a reusable Agent Configuration ('Species').
    """
    KNOWLEDGE_SCOPE_CHOICES = [
        ('system', 'Full System Context'),
        ('repository', 'Repository Only'),
        ('none', 'No RAG / Isolation'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # The "Soul"
    system_prompt_template = models.TextField(
        help_text="System prompt template. Use {{tools}} and {{context}} placeholders."
    )
    
    # The "Brain"
    default_model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_profiles'
    )
    temperature = models.FloatField(default=0.7)
    
    # The "Hands"
    tools = models.ManyToManyField(ToolDefinition, blank=True, related_name='agent_profiles')
    
    # Knowledge Context
    knowledge_scope = models.CharField(
        max_length=50, 
        choices=KNOWLEDGE_SCOPE_CHOICES,
        default='system'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_profiles'
        ordering = ['name']

    def __str__(self):
        return self.name



# ============================================================================
# Remote Service & Tool Models
# ============================================================================

class RemoteService(models.Model):
    """
    Represents an external service (Jira, Slack, Google Drive, etc.)
    that provides multiple actions/tools.
    """

    # Basic info
    name = models.CharField(max_length=255)  # "Jira", "Slack", "Google Drive"
    slug = models.SlugField(max_length=255)  # "jira", "slack", "google_drive"
    description = models.TextField()
    category = models.CharField(max_length=100, blank=True)  # "project_management", "communication"
    icon = models.CharField(max_length=50, blank=True)  # Emoji or icon name

    # Configuration
    base_url = models.URLField()  # "https://mycompany.atlassian.net"
    auth_type = models.CharField(max_length=50)  # "bearer", "oauth2", "api_key", "basic"
    auth_config = models.JSONField(default=dict)  # Encrypted credentials

    # API Documentation
    api_spec_url = models.URLField(null=True, blank=True)  # OpenAPI/Swagger URL
    api_spec_content = models.JSONField(null=True, blank=True)  # Cached spec
    api_docs_url = models.URLField(null=True, blank=True)  # Human docs URL

    # Knowledge Base
    knowledge_context = models.TextField(blank=True)  # AI-generated understanding
    examples = models.JSONField(default=list)  # Usage examples

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='remote_services')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    enabled = models.BooleanField(default=True)

    # Stats
    total_actions = models.IntegerField(default=0)
    enabled_actions = models.IntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'remote_services'
        unique_together = [['created_by', 'slug']]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'enabled']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return f"{self.name} ({self.created_by.username})"


class ServiceAction(models.Model):
    """
    Represents an action/tool within a service (e.g., JIRA_CREATE_ISSUE)
    """

    EXECUTION_PATTERN_CHOICES = [
        ('simple', 'Simple Request-Response'),
        ('async_polling', 'Async with Polling'),
        ('webhook', 'Webhook Callback'),
        ('multi_step', 'Multi-step Workflow'),
        ('streaming', 'Streaming Response'),
    ]

    service = models.ForeignKey(
        RemoteService,
        on_delete=models.CASCADE,
        related_name='actions'
    )

    # Action info
    name = models.CharField(max_length=255)  # "CREATE_ISSUE"
    action_group = models.CharField(max_length=100)  # "issues", "comments", "workflows"
    description = models.TextField()

    # Endpoint config
    endpoint_path = models.CharField(max_length=500)  # "/rest/api/3/issue"
    http_method = models.CharField(max_length=10, default='POST')  # "POST", "GET", "PUT", "DELETE"

    # Parameters (from API spec)
    parameters = models.JSONField(default=list)
    # [{"name": "summary", "type": "string", "required": true, ...}]

    # Request/Response config
    request_body_schema = models.JSONField(null=True, blank=True)
    response_schema = models.JSONField(null=True, blank=True)

    # Execution pattern
    execution_pattern = models.CharField(
        max_length=50,
        choices=EXECUTION_PATTERN_CHOICES,
        default='simple'
    )

    # For async/polling operations
    polling_config = models.JSONField(null=True, blank=True)
    # {"poll_endpoint": "/status/{job_id}", "poll_interval": 5, "max_attempts": 60, ...}

    # For webhook operations
    webhook_config = models.JSONField(null=True, blank=True)
    # {"webhook_url": "/webhooks/service/{action_id}", "secret": "...", ...}

    # Tool metadata
    tool_name = models.CharField(max_length=255, unique=True, db_index=True)
    # "JIRA_CREATE_ISSUE"

    enabled = models.BooleanField(default=True)
    version = models.CharField(max_length=50, default='1.0.0')

    # Usage stats
    execution_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)
    last_executed_at = models.DateTimeField(null=True, blank=True)
    average_execution_time = models.FloatField(null=True, blank=True)  # seconds

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_actions'
        unique_together = [['service', 'name']]
        ordering = ['service', 'action_group', 'name']
        indexes = [
            models.Index(fields=['service', 'action_group']),
            models.Index(fields=['tool_name']),
            models.Index(fields=['service', 'enabled']),
        ]

    def __str__(self):
        return f"{self.service.name}/{self.name}"

    def update_stats(self, success: bool, execution_time: float):
        """Update execution statistics"""
        self.execution_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        self.last_executed_at = timezone.now()

        # Update average execution time (running average)
        if self.average_execution_time is None:
            self.average_execution_time = execution_time
        else:
            # Weighted average (more weight on recent executions)
            self.average_execution_time = (
                0.7 * self.average_execution_time +
                0.3 * execution_time
            )

        self.save(update_fields=[
            'execution_count', 'success_count', 'failure_count',
            'last_executed_at', 'average_execution_time'
        ])


class ServiceKnowledgeEntry(models.Model):
    """
    Knowledge base entries for a service (docs, examples, guides)
    """

    ENTRY_TYPE_CHOICES = [
        ('api_guide', 'API Guide'),
        ('example', 'Code Example'),
        ('tutorial', 'Tutorial'),
        ('faq', 'FAQ'),
        ('troubleshooting', 'Troubleshooting'),
        ('changelog', 'Changelog'),
        ('best_practice', 'Best Practice'),
    ]

    service = models.ForeignKey(
        RemoteService,
        on_delete=models.CASCADE,
        related_name='knowledge_entries'
    )

    entry_type = models.CharField(max_length=50, choices=ENTRY_TYPE_CHOICES)
    title = models.CharField(max_length=500)
    content = models.TextField()
    source_url = models.URLField(null=True, blank=True)

    # AI metadata for semantic search
    embedding_vector = models.JSONField(null=True, blank=True)  # For semantic search
    relevance_score = models.FloatField(default=1.0)

    # Tags for categorization
    tags = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_knowledge_entries'
        ordering = ['-relevance_score', '-created_at']
        indexes = [
            models.Index(fields=['service', 'entry_type']),
            models.Index(fields=['service', '-relevance_score']),
        ]
        verbose_name_plural = 'Service knowledge entries'

    def __str__(self):
        return f"{self.service.name} - {self.title}"


class RemoteToolJob(models.Model):
    """
    Tracks async remote tool executions (for polling/webhook patterns)
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    action = models.ForeignKey(
        ServiceAction,
        on_delete=models.CASCADE,
        related_name='jobs'
    )

    job_id = models.CharField(max_length=255, db_index=True)  # External job ID
    internal_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Execution context
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    repository = models.ForeignKey('Repository', on_delete=models.SET_NULL, null=True, blank=True)
    session_id = models.CharField(max_length=255, blank=True)

    # Input/Output
    input_parameters = models.JSONField(default=dict)
    output_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    poll_attempts = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'remote_tool_jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job_id']),
            models.Index(fields=['internal_id']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.action.tool_name} - {self.job_id} ({self.status})"
