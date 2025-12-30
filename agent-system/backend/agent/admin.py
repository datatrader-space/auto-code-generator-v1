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
    SystemKnowledge, Task, AgentMemory
)


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
    fields = ['name', 'github_url', 'status', 'crs_status']
    readonly_fields = ['status', 'crs_status']
    show_change_link = True


@admin.register(System)
class SystemAdmin(admin.ModelAdmin):
    """System admin"""
    
    list_display = ['name', 'user', 'status', 'repos_count', 'knowledge_count', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'slug', 'user__username']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('user', 'name', 'slug', 'description', 'status')
        }),
        ('Paths', {
            'fields': ('workspace_path', 'system_spec_path'),
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
    
    list_display = ['name', 'system', 'github_url', 'status', 'crs_status', 'questions_answered', 'created_at']
    list_filter = ['status', 'crs_status', 'created_at']
    search_fields = ['name', 'github_url', 'system__name']
    readonly_fields = ['clone_path', 'crs_workspace_path', 'status', 'analysis', 'config', 
                       'artifacts_count', 'relationships_count', 'last_crs_run', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'name', 'github_url', 'github_branch')
        }),
        ('Status', {
            'fields': ('status', 'error_message', 'crs_status')
        }),
        ('Paths', {
            'fields': ('clone_path', 'crs_workspace_path'),
            'classes': ('collapse',)
        }),
        ('Analysis', {
            'fields': ('analysis', 'config'),
            'classes': ('collapse',)
        }),
        ('CRS Data', {
            'fields': ('artifacts_count', 'relationships_count', 'last_crs_run'),
            'classes': ('collapse',)
        }),
        ('Sync', {
            'fields': ('last_synced', 'last_commit_sha'),
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
    
    list_display = ['system', 'knowledge_type', 'spec_id', 'source', 'confidence', 'created_at']
    list_filter = ['knowledge_type', 'source', 'created_at']
    search_fields = ['system__name', 'spec_id']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'knowledge_type', 'spec_id')
        }),
        ('Content', {
            'fields': ('content',)
        }),
        ('Metadata', {
            'fields': ('source', 'confidence', 'spec_file_path')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """Task admin"""
    
    list_display = ['id', 'system', 'user', 'short_description', 'status', 'requires_approval', 
                    'approved', 'created_at']
    list_filter = ['status', 'requires_approval', 'approved', 'created_at']
    search_fields = ['description', 'system__name', 'user__username']
    readonly_fields = ['user', 'parsed_intent', 'execution_plan', 'impact_analysis', 
                       'slack_message_ts', 'approved_at', 'changes', 'github_prs',
                       'created_at', 'started_at', 'completed_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'user', 'description', 'status')
        }),
        ('Analysis', {
            'fields': ('parsed_intent', 'execution_plan', 'impact_analysis'),
            'classes': ('collapse',)
        }),
        ('Approval', {
            'fields': ('requires_approval', 'slack_message_ts', 'approved', 'approved_at', 'approval_notes')
        }),
        ('Results', {
            'fields': ('changes', 'github_prs', 'error_message'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ['affected_repos']
    
    def short_description(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    short_description.short_description = 'Description'


@admin.register(AgentMemory)
class AgentMemoryAdmin(admin.ModelAdmin):
    """Agent memory admin"""
    
    list_display = ['system', 'memory_type', 'confidence', 'learned_from_task', 'created_at']
    list_filter = ['memory_type', 'created_at']
    search_fields = ['system__name', 'content']
    readonly_fields = ['created_at']
    
    fieldsets = (
        (None, {
            'fields': ('system', 'memory_type', 'confidence')
        }),
        ('Content', {
            'fields': ('content',)
        }),
        ('Context', {
            'fields': ('learned_from_task', 'created_at')
        }),
    )


# Customize admin site
admin.site.site_header = "CRS Agent Administration"
admin.site.site_title = "CRS Agent Admin"
admin.site.index_title = "Welcome to CRS Agent Admin"