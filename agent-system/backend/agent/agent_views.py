from rest_framework import viewsets, decorators, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from agent.models import AgentProfile, ToolDefinition
from agent.serializers import AgentProfileSerializer, ToolDefinitionSerializer
from agent.tools.registry import get_tool_registry

class ToolDefinitionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for available tools.
    Syncs with codebase registry on list.
    """
    queryset = ToolDefinition.objects.filter(enabled=True)
    serializer_class = ToolDefinitionSerializer
    permission_classes = [IsAuthenticated]
    
    def list(self, request, *args, **kwargs):
        # Optional: Sync on list (can be optimized to background task)
        self._sync_registry()
        return super().list(request, *args, **kwargs)
        
    def _sync_registry(self):
        """Syncs database with code registry"""
        registry = get_tool_registry()
        code_tools = registry.get_all_tools()
        
        # 1. Ensure all code tools exist in DB
        for name, meta in code_tools.items():
            ToolDefinition.objects.get_or_create(
                name=name,
                defaults={
                    'category': meta.category,
                    'description': meta.description,
                    'enabled': meta.enabled
                }
            )

class AgentProfileViewSet(viewsets.ModelViewSet):
    """
    CRUD for Agent Profiles (The "Species" definitions)
    """
    queryset = AgentProfile.objects.all()
    serializer_class = AgentProfileSerializer
    permission_classes = [IsAuthenticated]
    
    @decorators.action(detail=True, methods=['post'], url_path='chat')
    def start_chat(self, request, pk=None):
        """
        Start a new chat session using this agent profile.
        Body: 
            system_id: int (Required)
            repository_id: int (Optional, overrides System default)
        """
        profile = self.get_object()
        
        system_id = request.data.get('system_id')
        repo_id = request.data.get('repository_id')
        
        if not system_id and profile.knowledge_scope == 'system':
             return Response(
                {"error": "System ID required for system-scope agents"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # This logic will eventually spawn a ChatConversation linked to this profile
        # For now, we return a mock success to unblock frontend dev
        return Response({
            "message": f"Started chat with agent {profile.name}",
            "profile_id": profile.id,
            "system_id": system_id
        })
