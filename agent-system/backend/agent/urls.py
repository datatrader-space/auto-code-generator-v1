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

# Main router
router = DefaultRouter()
router.register(r'systems', views.SystemViewSet, basename='system')

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

    # Authentication endpoints
    path('auth/register', auth_views.register_user, name='auth-register'),
    path('auth/login', auth_views.login_user, name='auth-login'),
    path('auth/logout', auth_views.logout_user, name='auth-logout'),
    path('auth/me', auth_views.current_user, name='auth-me'),
    path('auth/check', auth_views.check_auth, name='auth-check'),

    # GitHub OAuth endpoints
    path('auth/github/login', oauth_views.github_login, name='github-login'),
    path('auth/github/callback', oauth_views.github_callback, name='github-callback'),
    path('auth/github/test', oauth_views.test_token, name='github-test-token'),
    path('auth/github/repos', oauth_views.list_github_repos, name='github-list-repos'),
    path('auth/github/repo-info', oauth_views.get_repo_info, name='github-repo-info'),

    # Include routers
    path('', include(router.urls)),
    path('', include(systems_router.urls)),
]