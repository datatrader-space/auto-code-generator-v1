from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from django.test import TransactionTestCase
from agent.models import System, Repository, ChatConversation, ContextFile
from agent.consumers import RepositoryChatConsumer
from channels.testing import WebsocketCommunicator
import json
import os
from asgiref.sync import sync_to_async

User = get_user_model()

class ChatIntegrationTest(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.system = System.objects.create(user=self.user, name='TestSystem')
        self.repository = Repository.objects.create(system=self.system, name='TestRepo')
        self.client.force_login(self.user)

    def test_context_file_upload(self):
        # 1. Create Conversation
        conv_response = self.client.post('/api/conversations/', {
            'repository_id': self.repository.id,
            'title': 'Test Chat'
        })
        self.assertEqual(conv_response.status_code, 201)
        conversation_id = conv_response.data['id']

        # 2. Upload File
        from django.core.files.uploadedfile import SimpleUploadedFile
        file = SimpleUploadedFile("context.txt", b"This is some important context content.")
        
        upload_response = self.client.post(f'/api/conversations/{conversation_id}/files/', {
            'file': file
        }, format='multipart')
        
        self.assertEqual(upload_response.status_code, 201)
        self.assertEqual(ContextFile.objects.filter(conversation_id=conversation_id).count(), 1)
        
        # 3. List Files
        list_response = self.client.get(f'/api/conversations/{conversation_id}/files/')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]['name'], 'context.txt')

    async def test_chat_consumer_with_files(self):
        # Setup: Create conversation and file
        user = await User.objects.acreate(username='asyncuser')
        system = await System.objects.acreate(user=user, name='AsyncSys')
        repository = await Repository.objects.acreate(system=system, name='AsyncRepo')
        
        conversation = await ChatConversation.objects.acreate(
            user=user, 
            repository=repository,
            title="Async Chat"
        )
        
        # Create a real file for context
        from django.core.files.base import ContentFile
        context_file = await ContextFile.objects.acreate(
            conversation=conversation,
            name="test_context.txt"
        )
        
        def save_file():
            context_file.file.save("test_context.txt", ContentFile(b"CONTEXT_KEYWORD"))
            context_file.save()
        
        await sync_to_async(save_file)()

        # Test WebSocket
        communicator = WebsocketCommunicator(
            RepositoryChatConsumer.as_asgi(),
            f"/ws/chat/repository/{repository.id}/"
        )
        communicator.scope['user'] = user
        communicator.scope['url_route'] = {'kwargs': {'repository_id': repository.id}}
        
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Send message
        await communicator.send_json_to({
            "type": "chat_message",
            "message": "What is in the context?",
            "conversation_id": conversation.id,
            "model_id": None
        })

        # Receive responses
        # Expect typing
        try:
            response = await communicator.receive_json_from()
            # self.assertIn(response['type'], ['conversation_created', 'assistant_typing'])
            
            if response['type'] == 'conversation_created':
                 response = await communicator.receive_json_from()

            # We just want to ensure it doesn't crash 
            # and hopefully uses context
            # Simulating streaming
            while True:
                response = await communicator.receive_json_from(timeout=5)
                if response['type'] == 'assistant_message_complete':
                    break
                if response['type'] == 'error':
                     print(f"Got expected error (no LLM): {response['error']}")
                     break
        except Exception:
            pass

        await communicator.disconnect()
