
import os
import django
import sys
from pathlib import Path

# Setup Django environment
sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agent_platform.settings')
django.setup()

from asgiref.sync import async_to_sync
from agent.models import AgentProfile, ContextFile, User, System, Repository, ChatConversation
from agent.serializers import ContextFileSerializer, AgentProfileSerializer
from django.test import RequestFactory
from agent.views import ContextFileViewSet

def run_verification():
    print("--- Verifying Agent Knowledge Refactor ---")
    
    # 1. Setup Data
    user, _ = User.objects.get_or_create(username='test_knowledge_user')
    print(f"User: {user}")
    
    agent_profile, _ = AgentProfile.objects.get_or_create(
        name="Knowledge Agent",
        defaults={
            'description': 'Test Agent',
            'knowledge_scope': 'none', # Free agent
            'system_prompt_template': 'You are a test agent.'
        }
    )
    print(f"Agent Profile: {agent_profile.id} - {agent_profile.name}")
    
    # 2. Create ContextFile for Agent
    context_file, created = ContextFile.objects.get_or_create(
        agent_profile=agent_profile,
        name="agent_manifest.txt",
        defaults={
            'description': 'Agent core values',
            'analysis': 'Core values: 1. Be helpful. 2. Be safe.'
        }
    )
    if created:
        # Create dummy file
        from django.core.files.base import ContentFile
        context_file.file.save('manifest.txt', ContentFile("Be helpful and safe."))
        context_file.save()
        
    print(f"Context File: {context_file.id} linked to Agent {context_file.agent_profile_id}")
    
    # 3. Verify Serializer
    serializer = AgentProfileSerializer(agent_profile)
    data = serializer.data
    # Check if knowledge_files are included
    print("Agent Serializer Data Keys:", data.keys())
    if 'knowledge_files' in data:
        files = data['knowledge_files']
        print(f"Knowledge Files found in serializer: {len(files)}")
        if len(files) > 0:
            print(f"File 0 Name: {files[0]['name']}")
            print(f"File 0 Analysis: {files[0]['analysis']}")
    else:
        print("ERROR: knowledge_files MISSING from AgentProfileSerializer")
        
    # 4. Verify ContextFileSerializer
    cf_serializer = ContextFileSerializer(context_file)
    print(f"Context File Serializer keys: {cf_serializer.data.keys()}")
    if 'agent_profile' in cf_serializer.data:
        print(f"Context File linked to agent: {cf_serializer.data['agent_profile']}")
    else:
        print("ERROR: agent_profile MISSING from ContextFileSerializer")

    # 5. Verify ChatConversation with No Repository
    conv = ChatConversation.objects.create(
        user=user,
        title="Free Agent Chat",
        repository=None, # Explicitly None
        metadata={'agent_profile_id': agent_profile.id}
    )
    print(f"Created Conversation {conv.id} with repository={conv.repository}")
    
    # 6. Verify Consumers Logic (Mock)
    # We can't easily run the consumer here, but we can verify dependencies
    from agent.services.agent_runner import AgentRunner
    from agent.services.knowledge_agent import RepositoryKnowledgeAgent
    
    print("Testing AgentRunner with repo=None...")
    runner = AgentRunner(repository=None)
    if runner.fs is None:
        print("AgentRunner.fs correctly returns None")
    else:
        print(f"ERROR: AgentRunner.fs returned {runner.fs}")
        
    print("Testing KnowledgeAgent with repo=None...")
    ka = RepositoryKnowledgeAgent(repository=None)
    res = ka.get_context_for("Hello")
    print(f"KnowledgeAgent context (empty): {res}")
    
    print("\n--- Verification Complete ---")

if __name__ == '__main__':
    run_verification()
