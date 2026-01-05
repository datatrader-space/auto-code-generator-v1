from django.contrib import admin

# Register your models here.
# agent/admin.py
"""
Django Admin Configuration for Agent System
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from agent.models import (
    User, System, Repository, RepositoryQuestion,
    SystemKnowledge, Task, AgentMemory, GitHubOAuthConfig,
    ChatConversation, ChatMessage, LLMProvider, LLMModel, LLMRequestLog,
    AgentSession,AgentProfile
)
admin.site.register(AgentProfile)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom user admin"""
    
    list_display = ['username', 'email', 'slack_user_id', 'github_username', 'is_staff', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    search_fields = ['username', 'email', 'slack_user_id', 'github_username']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Integration', {
            'fields': ('slack_user_id', 'slack_workspace_id', 'github_username', 'github_token')
        }),
        ('Preferences', {
            'fields': ('preferences',),
            'classes': ('collapse',)
        }),
    )


class RepositoryInline(admin.TabularInline):
    """Inline repositories in system admin"""
    model = Repository
    extra = 0
    fields = ['name', 'github_url', 'status']
    readonly_fields = ['status']
    show_change_link = True


@admin.register(System)
class SystemAdmin(admin.ModelAdmin):
    """System admin"""
    
    list_display = ['name', 'user', 'status', 'repos_count', 'knowledge_count', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('user', 'name', 'description', 'status')
        }),
        ('Intent & Constraints', {
            'fields': ('intent_constraints',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [RepositoryInline]
    
    def repos_count(self, obj):
        return obj.repositories.count()
    repos_count.short_description = 'Repositories'
    
    def knowledge_count(self, obj):
        return obj.knowledge.count()
    knowledge_count.short_description = 'Knowledge Items'


class RepositoryQuestionInline(admin.TabularInline):
    """Inline questions in repository admin"""
    model = RepositoryQuestion
    extra = 0
    fields = ['question_key', 'question_text', 'question_type', 'answer', 'required']
    readonly_fields = ['question_key', 'question_text', 'question_type', 'required']


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    """Repository admin"""
    
    list_display = ['name', 'system', 'github_url', 'status', 'questions_answered', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'github_url', 'system__name']
    readonly_fields = ['clone_path', 'status', 'analysis', 'config', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'name', 'github_url', 'github_branch')
        }),
        ('Status', {
            'fields': ('status', 'error_message')
        }),
        ('Paths', {
            'fields': ('clone_path',),
            'classes': ('collapse',)
        }),
        ('Analysis', {
            'fields': ('analysis', 'config'),
            'classes': ('collapse',)
        }),
        ('Sync', {
            'fields': ('last_synced_at', 'last_commit_sha'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [RepositoryQuestionInline]
    
    def questions_answered(self, obj):
        total = obj.questions.count()
        answered = obj.questions.filter(answer__isnull=False).count()
        return f"{answered}/{total}"
    questions_answered.short_description = 'Questions'


@admin.register(RepositoryQuestion)
class RepositoryQuestionAdmin(admin.ModelAdmin):
    """Repository question admin"""
    
    list_display = ['repository', 'question_key', 'question_type', 'category', 'has_answer', 'required']
    list_filter = ['question_type', 'category', 'required']
    search_fields = ['repository__name', 'question_key', 'question_text']
    readonly_fields = ['question_key', 'question_text', 'question_type', 'options', 
                       'required', 'category', 'order', 'created_at']
    
    fieldsets = (
        (None, {
            'fields': ('repository', 'question_key', 'question_text', 'question_type')
        }),
        ('Options', {
            'fields': ('options', 'required', 'category', 'order')
        }),
        ('Answer', {
            'fields': ('answer', 'answered_at')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def has_answer(self, obj):
        return obj.answer is not None
    has_answer.boolean = True
    has_answer.short_description = 'Answered'


@admin.register(SystemKnowledge)
class SystemKnowledgeAdmin(admin.ModelAdmin):
    """System knowledge admin"""
    
    list_display = ['system', 'knowledge_type', 'title', 'created_at']
    list_filter = ['knowledge_type', 'created_at']
    search_fields = ['system__name', 'title']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'knowledge_type', 'title')
        }),
        ('Content', {
            'fields': ('description', 'metadata')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """Task admin"""
    
    list_display = ['task_id', 'system', 'user', 'short_title', 'status', 'approved', 'created_at']
    list_filter = ['status', 'approved', 'created_at']
    search_fields = ['task_id', 'title', 'description', 'system__name', 'user__username']
    readonly_fields = ['task_id', 'plan', 'result', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'user', 'task_id', 'title', 'description', 'status')
        }),
        ('Plan', {
            'fields': ('plan',),
            'classes': ('collapse',)
        }),
        ('Approval', {
            'fields': ('approved', 'approval_notes')
        }),
        ('Results', {
            'fields': ('result', 'error_message'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ['affected_repos']
    
    def short_title(self, obj):
        return obj.title[:50] + '...' if obj.title and len(obj.title) > 50 else obj.title
    short_title.short_description = 'Title'


@admin.register(AgentMemory)
class AgentMemoryAdmin(admin.ModelAdmin):
    """Agent memory admin"""
    
    list_display = ['system', 'memory_type', 'importance', 'created_at']
    list_filter = ['memory_type', 'created_at']
    search_fields = ['system__name', 'content']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'memory_type', 'importance')
        }),
        ('Content', {
            'fields': ('content', 'metadata')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(GitHubOAuthConfig)
class GitHubOAuthConfigAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'callback_url', 'scope', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['client_id', 'callback_url']


class ChatMessageInline(admin.TabularInline):
    """Inline messages in conversation admin"""
    model = ChatMessage
    extra = 0
    fields = ['role', 'content_preview', 'created_at']
    readonly_fields = ['role', 'content_preview', 'created_at']

    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content'


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    """Chat conversation admin"""

    list_display = ['title', 'conversation_type', 'user', 'system', 'repository',
                    'message_count', 'created_at', 'updated_at']
    list_filter = ['conversation_type', 'created_at']
    search_fields = ['title', 'user__username', 'system__name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('user', 'system', 'conversation_type', 'title')
        }),
        ('Context', {
            'fields': ('repository',)
        }),
        ('Settings', {
            'fields': ('model_provider', 'llm_model')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [ChatMessageInline]

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """Chat message admin"""

    list_display = ['id', 'conversation', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['conversation__title', 'content']
    readonly_fields = ['created_at']

    fieldsets = (
        (None, {
            'fields': ('conversation', 'role', 'content')
        }),
        ('Metadata', {
            'fields': ('context_used', 'model_info'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content'


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider_type', 'user', 'is_active', 'created_at']
    list_filter = ['provider_type', 'is_active', 'created_at']
    search_fields = ['name', 'user__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LLMModel)
class LLMModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'model_id', 'provider', 'is_active', 'created_at']
    list_filter = ['provider__provider_type', 'is_active', 'created_at']
    search_fields = ['name', 'model_id', 'provider__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LLMRequestLog)
class LLMRequestLogAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'conversation', 'model', 'request_type', 'status',
        'latency_ms', 'total_tokens', 'created_at'
    ]
    list_filter = ['request_type', 'status', 'created_at']
    search_fields = ['conversation__title', 'error_message']
    readonly_fields = ['created_at']


# Customize admin site
admin.site.site_header = "CRS Agent Administration"
admin.site.site_title = "CRS Agent Admin"
admin.site.index_title = "Welcome to CRS Agent Admin"


@admin.register(AgentSession)
class AgentSessionAdmin(admin.ModelAdmin):
    """Agent session admin for debugging"""
    
    list_display = ['session_id', 'session_type', 'repository', 'status', 'duration_ms', 'created_at']
    list_filter = ['session_type', 'status', 'created_at']
    search_fields = ['session_id', 'user_request', 'repository__name']
    readonly_fields = [
        'session_id', 'conversation', 'repository', 'session_type',
        'intent_classified_as', 'user_request', 'status', 'plan', 'steps',
        'final_answer', 'artifacts_used', 'tools_called', 'duration_ms',
        'error_message', 'knowledge_context', 'llm_model_used',
        'created_at', 'completed_at'
    ]
    
    fieldsets = (
        (None, {
            'fields': ('session_id', 'session_type', 'status', 'intent_classified_as')
        }),
        ('Context', {
            'fields': ('conversation', 'repository', 'llm_model_used')
        }),
        ('Request', {
            'fields': ('user_request',)
        }),
        ('Execution', {
            'fields': ('plan', 'steps', 'tools_called'),
            'classes': ('collapse',)
        }),
        ('Results', {
            'fields': ('final_answer', 'artifacts_used', 'error_message'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('knowledge_context', 'duration_ms', 'created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
