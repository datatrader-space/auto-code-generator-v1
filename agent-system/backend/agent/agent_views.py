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
        model_id = request.data.get('llm_model_id')
        
        # Create a real conversation linked to this profile
        from agent.models import ChatConversation, System, Repository
        
        conversation = ChatConversation.objects.create(
            user=request.user,
            system_id=system_id,
            repository_id=repo_id,
            llm_model_id=model_id,
            title=f"Chat with {profile.name}",
            conversation_type='repository', # Using repository chat infrastructure
            metadata={
                'agent_profile_id': profile.id,
                'agent_name': profile.name
            }
        )
        
        return Response({
            "message": f"Started chat with agent {profile.name}",
            "profile_id": conversation.id, # Using conversation ID as profile_id for frontend compat
            "conversation_id": conversation.id,
            "system_id": system_id
        })
