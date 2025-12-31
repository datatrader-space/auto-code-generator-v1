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
import json


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
        ordering = ['name']

    def __str__(self):
        return f"{self.provider.name}/{self.model_id}"


class LLMRequestLog(models.Model):
    """Track usage of configured LLM providers/models."""

    """Log entries for LLM request/response usage."""

    REQUEST_TYPE_CHOICES = [
        ('chat', 'Chat'),
        ('stream', 'Stream'),
    ]
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
    ]

    REQUEST_TYPES = [
        ('chat', 'Chat'),
        ('stream', 'Stream'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='llm_request_logs')
    conversation = models.ForeignKey(
        'ChatConversation',
        on_delete=models.SET_NULL,
        related_name='llm_request_logs',
        null=True,
        blank=True
    )
    llm_model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        related_name='request_logs',
        null=True,
        blank=True
    )
    provider_type = models.CharField(max_length=50, blank=True)
    model_id = models.CharField(max_length=200, blank=True)
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPES, default='chat')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='llm_request_logs')
    conversation = models.ForeignKey(
        'ChatConversation',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='llm_request_logs'
    )
    provider = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=200, blank=True)
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    latency_ms = models.IntegerField(null=True, blank=True)
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'llm_request_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}:{self.provider_type}:{self.model_id}:{self.status}"
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['provider', 'model']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.provider}/{self.model or 'default'} - {self.status}"


class System(models.Model):
    """
    A system is a collection of related repositories
    Example: "E-commerce Platform" with 4 repos (datahouse, worker, storage, central)
    """
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='systems')
    
    # Basic info
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    
    # Status
    STATUS_CHOICES = [
        ('initializing', 'Initializing'),
        ('analyzing', 'Analyzing Structure'),
        ('questions_pending', 'Questions Pending'),
        ('ready', 'Ready'),
        ('error', 'Error'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='initializing')
    
    # Paths
    workspace_path = models.CharField(max_length=500, blank=True)
    # Points to: workspaces/{user_id}/{system_id}/
    
    system_spec_path = models.CharField(max_length=500, blank=True)
    # Points to: crs_workspaces/{user_id}/{system_id}/system_meta/
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Intent & constraints
    intent_constraints = models.JSONField(default=dict, blank=True)
    # {
    #   "summary": "What the system should do",
    #   "constraints": ["PII never leaves EU", "Must use Redis for caching"]
    # }
    
    class Meta:
        db_table = 'agent_systems'
        unique_together = [['user', 'slug']]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username}/{self.name}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Repository(models.Model):
    """
    A repository within a system
    Can be Django, services, FastAPI, or any other paradigm
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='repositories')
    
    # Basic info
    name = models.CharField(max_length=200)
    github_url = models.URLField()
    github_branch = models.CharField(max_length=100, default='main')
    
    # Local paths
    clone_path = models.CharField(max_length=500, blank=True)
    # workspaces/{user_id}/{system_id}/{repo_name}/
    
    crs_workspace_path = models.CharField(max_length=500, blank=True)
    # crs_workspaces/{user_id}/{system_id}/{repo_name}_crs/
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending Clone'),
        ('cloning', 'Cloning'),
        ('analyzing', 'Analyzing Structure'),
        ('questions_generated', 'Questions Generated'),
        ('questions_answered', 'Questions Answered'),
        ('crs_ready', 'CRS Ready'),
        ('crs_running', 'CRS Running'),
        ('ready', 'Ready'),
        ('error', 'Error'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    
    # Analysis results (from LLM)
    analysis = models.JSONField(null=True, blank=True)
    # {
    #   "paradigm": "django|services|fastapi|other",
    #   "patterns": ["class-based", "function-based"],
    #   "key_concepts": ["model", "service"],
    #   "file_tree": {...},
    #   "sample_files": {...},
    #   "can_use_standard_crs": true|false,
    #   "confidence": 0.95
    # }
    
    # Configuration (from answers)
    config = models.JSONField(default=dict, blank=True)
    # {
    #   "paradigm": "services",
    #   "artifact_types": ["service_class", "service_method"],
    #   "api_calls_to": ["datahouse"],
    #   "fields_used": ["Order.status"],
    #   "extractor": "custom_generated"
    # }
    
    # CRS state
    crs_status = models.CharField(max_length=50, default='not_started')
    last_crs_run = models.DateTimeField(null=True, blank=True)
    artifacts_count = models.IntegerField(default=0)
    relationships_count = models.IntegerField(default=0)
    
    # Sync
    last_synced = models.DateTimeField(null=True, blank=True)
    last_commit_sha = models.CharField(max_length=40, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'agent_repositories'
        unique_together = [['system', 'name']]
        ordering = ['name']
    
    def __str__(self):
        return f"{self.system.name}/{self.name}"


class RepositoryQuestion(models.Model):
    """
    Questions generated by LLM to understand repository structure
    User answers these to help agent build knowledge
    """
    
    repository = models.ForeignKey(
        Repository, 
        on_delete=models.CASCADE, 
        related_name='questions'
    )
    
    # Question
    question_key = models.CharField(max_length=100)
    # e.g., "paradigm_confirm", "api_calls_target", "fields_used"
    
    question_text = models.TextField()
    question_type = models.CharField(max_length=50)
    # yes_no, multiple_choice, text, list
    
    options = models.JSONField(null=True, blank=True)
    # For multiple_choice: ["API calls", "Direct import", "Message queue"]
    
    # Answer
    answer = models.JSONField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    required = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    category = models.CharField(max_length=50, blank=True)
    # structure, dependencies, patterns, fields
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'agent_repository_questions'
        ordering = ['repository', 'order']
    
    def __str__(self):
        return f"{self.repository.name}: {self.question_key}"


class RepositoryReasoningTrace(models.Model):
    """
    Stores AI reasoning traces for repository analysis and question generation.
    """

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='reasoning_traces'
    )
    stage = models.CharField(max_length=100)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'agent_repository_reasoning_traces'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.repository.name}: {self.stage}"


class SystemKnowledge(models.Model):
    """
    System-level knowledge derived from LLM analysis + user answers
    This is what guides CRS and agent behavior
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='knowledge')
    
    # Knowledge type
    KNOWLEDGE_TYPES = [
        ('architecture', 'System Architecture'),
        ('flow', 'Cross-Repo Flow'),
        ('contract', 'API Contract'),
        ('constraint', 'Business Rule'),
        ('pattern', 'Communication Pattern'),
        ('norm', 'Coding Convention'),
    ]
    knowledge_type = models.CharField(max_length=50, choices=KNOWLEDGE_TYPES)
    
    # Identity
    spec_id = models.CharField(max_length=200)
    # e.g., "order_creation_flow", "datahouse_api_contract"
    
    # Content
    content = models.JSONField()
    # Flexible schema based on knowledge_type
    
    # Provenance
    source = models.CharField(max_length=50)
    # llm_inference, user_provided, learned
    
    confidence = models.FloatField(default=1.0)
    # 0.0 to 1.0
    
    # File reference (optional)
    spec_file_path = models.CharField(max_length=500, blank=True)
    # Points to: system_meta/state/specs/docs/{kind}/{spec_id}.json
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'agent_system_knowledge'
        unique_together = [['system', 'knowledge_type', 'spec_id']]
        ordering = ['knowledge_type', 'spec_id']
    
    def __str__(self):
        return f"{self.system.name}: {self.knowledge_type}/{self.spec_id}"


class SystemDocumentation(models.Model):
    """
    Auto-generated documentation derived from CRS + knowledge outputs.
    """

    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='documentation')
    doc_type = models.CharField(max_length=100, default='overview')
    content = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_system_documentation'
        unique_together = [['system', 'doc_type']]
        ordering = ['doc_type']

    def __str__(self):
        return f"{self.system.name}: {self.doc_type}"


class Task(models.Model):
    """
    User task for the agent to execute
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='tasks')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    
    # Task description
    description = models.TextField()
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('analyzing', 'Analyzing'),
        ('planning', 'Planning'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('executing', 'Executing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    
    # AI processing
    parsed_intent = models.JSONField(null=True, blank=True)
    # What LLM understood from description
    
    execution_plan = models.JSONField(null=True, blank=True)
    # Step-by-step plan
    
    # Impact
    affected_repos = models.ManyToManyField(Repository, related_name='affected_by_tasks')
    impact_analysis = models.JSONField(null=True, blank=True)
    
    # Approval
    requires_approval = models.BooleanField(default=True)
    slack_message_ts = models.CharField(max_length=100, blank=True)
    approved = models.BooleanField(null=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    
    # Results
    changes = models.JSONField(null=True, blank=True)
    # Diffs, patches applied
    
    github_prs = models.JSONField(null=True, blank=True)
    # PR URLs if created
    
    error_message = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'agent_tasks'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Task #{self.id}: {self.description[:50]}"


class AgentMemory(models.Model):
    """
    What the agent has learned
    """
    
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='memories')
    
    # Memory type
    MEMORY_TYPES = [
        ('pattern', 'Pattern Discovered'),
        ('preference', 'User Preference'),
        ('error', 'Error Encountered'),
        ('suggestion', 'Improvement Suggestion'),
        ('correction', 'User Correction'),
    ]
    memory_type = models.CharField(max_length=50, choices=MEMORY_TYPES)
    
    # Content
    content = models.JSONField()
    
    # Confidence
    confidence = models.FloatField(default=1.0)
    
    # Context
    learned_from_task = models.ForeignKey(
        Task, 
        null=True, 
        blank=True,
        on_delete=models.SET_NULL,
        related_name='generated_memories'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'agent_memories'
        ordering = ['-created_at']

    def __str__(self):
        return f"Memory: {self.memory_type} - {self.created_at}"


class ChatConversation(models.Model):
    """
    Chat conversation - context for a series of messages

    Types:
    - repository: Chat about a specific repository (context locked)
    - planner: Multi-repo planning chat (all repos available)
    - graph: Visual graph exploration chat
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_conversations')
    system = models.ForeignKey(System, on_delete=models.CASCADE, related_name='chat_conversations')

    # Conversation type
    CONVERSATION_TYPES = [
        ('repository', 'Repository Chat'),
        ('planner', 'Planner Chat'),
        ('graph', 'Graph Exploration'),
    ]
    conversation_type = models.CharField(max_length=20, choices=CONVERSATION_TYPES)

    # Context
    repository = models.ForeignKey(
        Repository,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='chat_conversations',
        help_text='For repository-specific chats'
    )

    # Metadata
    title = models.CharField(max_length=200, blank=True)  # Auto-generated from first message
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Settings
    model_provider = models.CharField(max_length=50, default='local')  # 'local', 'cloud'
    llm_model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        related_name='chat_conversations',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'chat_conversations'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'system', 'conversation_type']),
            models.Index(fields=['repository']),
        ]

    def __str__(self):
        return f"{self.conversation_type}: {self.title or 'Untitled'}"


class ChatMessage(models.Model):
    """
    Individual chat message
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
