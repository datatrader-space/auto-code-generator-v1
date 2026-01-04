# agent/urls.py
"""
URL Configuration for Agent API
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers

from agent import views
from agent import oauth_views
from agent import auth_views
from agent.view_handlers import tool_views
from agent import agent_views
from agent.view_handlers import service_views

# Main router
router = DefaultRouter()
router.register(r'agents', agent_views.AgentProfileViewSet)
router.register(r'systems', views.SystemViewSet, basename='system')
router.register(r'conversations', views.ChatConversationViewSet, basename='conversation')
router.register(r'sessions', views.AgentSessionViewSet, basename='agent-session')
router.register(r'llm/providers', views.LLMProviderViewSet, basename='llm-provider')
router.register(r'llm/models', views.LLMModelViewSet, basename='llm-model')
router.register(r'benchmarks/runs', views.BenchmarkRunViewSet, basename='benchmark-run')
router.register(r'benchmarks/reports', views.BenchmarkReportViewSet, basename='benchmark-report')

# Nested routers for system resources
systems_router = nested_routers.NestedDefaultRouter(
    router,
    r'systems',
    lookup='system'
)
systems_router.register(
    r'repositories',
    views.RepositoryViewSet,
    basename='system-repositories'
)
systems_router.register(
    r'knowledge',
    views.SystemKnowledgeViewSet,
    basename='system-knowledge'
)
systems_router.register(
    r'documentation',
    views.SystemDocumentationViewSet,
    basename='system-documentation'
)
systems_router.register(
    r'tasks',
    views.TaskViewSet,
    basename='system-tasks'
)
systems_router.register(
    r'memories',
    views.AgentMemoryViewSet,
    basename='system-memories'
)

urlpatterns = [
    # API root
    path('', views.api_root, name='api-root'),

    # LLM health
    path('llm/health/', views.llm_health, name='llm-health'),
    path('llm/stats/', views.llm_stats, name='llm-stats'),

    # Benchmarks
    path('benchmarks/run', views.benchmark_run, name='benchmark-run'),
    path('benchmarks', views.benchmark_list, name='benchmark-list'),
    path('benchmarks/<uuid:run_id>/status', views.benchmark_status, name='benchmark-status'),
    path('benchmarks/<uuid:run_id>/report', views.benchmark_report, name='benchmark-report'),
    path('benchmarks/reports/<str:run_id>/download', views.benchmark_report_download, name='benchmark-report-download'),

    # Authentication endpoints
    path('auth/register', auth_views.register_user, name='auth-register'),
    path('auth/login', auth_views.login_user, name='auth-login'),
    path('auth/logout', auth_views.logout_user, name='auth-logout'),
    path('auth/me', auth_views.current_user, name='auth-me'),
    path('auth/check', auth_views.check_auth, name='auth-check'),

    # GitHub OAuth endpoints
    path('auth/github/config', oauth_views.github_config, name='github-config'),
    path('auth/github/login', oauth_views.github_login, name='github-login'),
    path('auth/github/callback', oauth_views.github_callback, name='github-callback'),
    path('auth/github/test', oauth_views.test_token, name='github-test-token'),
    path('auth/github/repos', oauth_views.list_github_repos, name='github-list-repos'),
    path('auth/github/repo-info', oauth_views.get_repo_info, name='github-repo-info'),

    # Tool Management
    path('tools/', tool_views.list_tools, name='tools-list'),
    path('tools/execute/', tool_views.execute_tool, name='tool-execute'),
    path('tools/documentation/', tool_views.get_tool_documentation, name='tool-docs'),
    path('tools/register/remote/', tool_views.register_remote_tool, name='register-remote-tool'),
    path('tools/create/yaml/', tool_views.create_yaml_tool, name='create-yaml-tool'),
    path('tools/<str:tool_name>/update/', tool_views.update_tool, name='update-tool'),
    path('tools/<str:tool_name>/delete/', tool_views.delete_tool, name='delete-tool'),

    path('tools/definitions/', agent_views.ToolDefinitionViewSet.as_view({'get': 'list'}), name='tool-definitions'),
    path('tools/<str:tool_name>/', tool_views.get_tool_detail, name='tool-detail'),

    # Service Management
    path('services/', service_views.list_services, name='services-list'),
    path('services/<int:service_id>/', service_views.get_service_detail, name='service-detail'),
    path('services/create/', service_views.create_service, name='create-service'),
    path('services/<int:service_id>/update/', service_views.update_service, name='update-service'),
    path('services/<int:service_id>/delete/', service_views.delete_service, name='delete-service'),
    path('services/<int:service_id>/actions/create/', service_views.create_service_actions, name='create-service-actions'),
    path('services/discover/', service_views.discover_actions, name='discover-actions'),

    # Include routers
    path('', include(router.urls)),
    path('', include(systems_router.urls)),
]
