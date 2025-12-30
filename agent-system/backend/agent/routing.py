"""
WebSocket routing for Agent System
"""

from django.urls import re_path
from agent import consumers

websocket_urlpatterns = [
    # Repository chat: ws://localhost:8000/ws/chat/repository/{repo_id}/
    re_path(
        r'ws/chat/repository/(?P<repository_id>\d+)/$',
        consumers.RepositoryChatConsumer.as_asgi()
    ),

    # Planner chat: ws://localhost:8000/ws/chat/planner/{system_id}/
    re_path(
        r'ws/chat/planner/(?P<system_id>\d+)/$',
        consumers.PlannerChatConsumer.as_asgi()
    ),

    # Graph chat: ws://localhost:8000/ws/chat/graph/{system_id}/
    re_path(
        r'ws/chat/graph/(?P<system_id>\d+)/$',
        consumers.GraphChatConsumer.as_asgi()
    ),
]
