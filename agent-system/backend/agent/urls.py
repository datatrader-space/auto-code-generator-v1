# agent/urls.py
"""
URL Configuration for Agent API
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers

from agent import views

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
    
    # Include routers
    path('', include(router.urls)),
    path('', include(systems_router.urls)),
]