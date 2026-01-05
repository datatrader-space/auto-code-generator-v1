from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from agent.models import System, Repository, AgentProfile, LLMModel, LLMProvider, ChatConversation
from unittest.mock import patch, MagicMock

User = get_user_model()

class AgentFeaturesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.system = System.objects.create(name='Test System', user=self.user)
        self.repository = Repository.objects.create(name='Test Repo', system=self.system)
        
        self.provider = LLMProvider.objects.create(
            user=self.user, 
            provider_type='ollama', 
            name='Local Ollama'
        )
        self.model = LLMModel.objects.create(
            provider=self.provider, 
            model_id='llama3', 
            name='Llama 3'
        )
        
        self.agent = AgentProfile.objects.create(
            user=self.user,
            name='Test Agent',
            knowledge_scope='repository',
            repository=self.repository
        )

    def test_start_chat_with_model(self):
        """Test starting chat with a specific LLM model"""
        url = f'/api/agents/{self.agent.id}/chat/'
        data = {
            'system_id': self.system.id,
            'repository_id': self.repository.id,
            'llm_model_id': self.model.id
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        conv_id = response.data['conversation_id']
        conversation = ChatConversation.objects.get(id=conv_id)
        
        # Verify model was set
        self.assertEqual(conversation.llm_model, self.model)
        self.assertEqual(conversation.model_provider, 'ollama')

    @patch('agent.views.get_llm_router')
    def test_analyze_knowledge_doc(self, mock_get_router):
        """Test analyzing a knowledge doc"""
        # Mock Knowledge Agent doc retrieval
        with patch('agent.services.knowledge_agent.RepositoryKnowledgeAgent') as MockAgent:
            mock_agent_instance = MockAgent.return_value
            mock_agent_instance.spec_store.get_doc.return_value = {
                'kind': 'test_kind',
                'spec_id': 'test_id',
                'title': 'Test Doc',
                'content': 'This is a test document content.'
            }
            
            # Mock LLM Router
            mock_router = MagicMock()
            mock_get_router.return_value = mock_router
            mock_client = MagicMock()
            mock_router.client_for_config.return_value = mock_client
            # Mock stream response
            mock_client.query_stream.return_value = iter(['This ', 'is ', 'a ', 'summary.'])
            
            url = f'/api/systems/{self.system.id}/repositories/{self.repository.id}/knowledge/analyze_doc/'
            data = {
                'kind': 'test_kind',
                'spec_id': 'test_id'
            }
            
            response = self.client.post(url, data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['summary'], 'This is a summary.')
            self.assertEqual(response.data['doc_title'], 'Test Doc')
            
            # Verify LLM was called
            mock_client.query_stream.assert_called()
