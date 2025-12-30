"""
WebSocket consumers for real-time chat
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async

from agent.models import Repository, System, ChatConversation, ChatMessage
from agent.services.crs_context import CRSContext
from llm.router import get_llm_router

logger = logging.getLogger(__name__)


class BaseChatConsumer(AsyncWebsocketConsumer):
    """
    Base consumer for all chat types

    Handles:
    - WebSocket connection/disconnection
    - Message receiving/sending
    - Streaming LLM responses
    """

    async def connect(self):
        """Accept WebSocket connection"""
        await self.accept()
        logger.info(f"WebSocket connected: {self.scope['user']}")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        logger.info(f"WebSocket disconnected: {close_code}")

    async def receive(self, text_data):
        """
        Receive message from WebSocket

        Expected format:
        {
            "type": "chat_message",
            "message": "user message text",
            "conversation_id": 123 (optional, for continuing conversation)
        }
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'ping':
                await self.send_json({'type': 'pong'})
            else:
                await self.send_json({
                    'type': 'error',
                    'error': f'Unknown message type: {message_type}'
                })

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            await self.send_json({
                'type': 'error',
                'error': 'Invalid JSON'
            })
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await self.send_json({
                'type': 'error',
                'error': str(e)
            })

    async def handle_chat_message(self, data):
        """
        Handle incoming chat message - to be overridden by subclasses
        """
        raise NotImplementedError("Subclasses must implement handle_chat_message")

    async def send_json(self, data):
        """Send JSON message to WebSocket"""
        await self.send(text_data=json.dumps(data))

    async def stream_llm_response(self, user_message, context, conversation):
        """
        Stream LLM response in chunks

        Args:
            user_message: User's message text
            context: CRS context or other relevant context
            conversation: ChatConversation instance
        """
        # Build messages for LLM
        messages = await self.build_llm_messages(conversation, user_message, context)

        # Get LLM router
        router = await sync_to_async(get_llm_router)()

        # Determine provider
        provider = 'local' if conversation.model_provider == 'local' else 'cloud'

        # Send typing indicator
        await self.send_json({
            'type': 'assistant_typing',
            'typing': True
        })

        full_response = ""
        model_info = {}

        try:
            # Stream response chunks
            client = router.local_client if provider == 'local' else router.cloud_client

            async for chunk in sync_to_async(lambda: list(client.query_stream(messages)))():
                for text_chunk in chunk:
                    full_response += text_chunk

                    # Send chunk to frontend
                    await self.send_json({
                        'type': 'assistant_message_chunk',
                        'chunk': text_chunk
                    })

            # Send completion
            await self.send_json({
                'type': 'assistant_message_complete',
                'full_message': full_response
            })

            # Save assistant message to database
            await self.save_assistant_message(
                conversation,
                full_response,
                context,
                model_info
            )

        except Exception as e:
            logger.error(f"LLM streaming error: {e}", exc_info=True)
            await self.send_json({
                'type': 'error',
                'error': f'LLM error: {str(e)}'
            })

        finally:
            # Stop typing indicator
            await self.send_json({
                'type': 'assistant_typing',
                'typing': False
            })

    @database_sync_to_async
    def save_assistant_message(self, conversation, content, context_used, model_info):
        """Save assistant message to database"""
        ChatMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=content,
            context_used=context_used,
            model_info=model_info
        )

    async def build_llm_messages(self, conversation, user_message, context):
        """
        Build message list for LLM

        To be overridden by subclasses for specific context formatting
        """
        raise NotImplementedError("Subclasses must implement build_llm_messages")


class RepositoryChatConsumer(BaseChatConsumer):
    """
    Repository-specific chat consumer

    Context is locked to a single repository's CRS data
    """

    async def connect(self):
        self.repository_id = self.scope['url_route']['kwargs']['repository_id']
        self.repository = await self.get_repository()

        if not self.repository:
            await self.close()
            return

        await super().connect()

    @database_sync_to_async
    def get_repository(self):
        """Get repository from database"""
        try:
            return Repository.objects.select_related('system').get(id=self.repository_id)
        except Repository.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_conversation(self, conversation_id=None):
        """Get existing or create new conversation"""
        if conversation_id:
            try:
                return ChatConversation.objects.get(
                    id=conversation_id,
                    repository=self.repository
                )
            except ChatConversation.DoesNotExist:
                pass

        # Create new conversation
        return ChatConversation.objects.create(
            user=self.scope['user'],
            system=self.repository.system,
            repository=self.repository,
            conversation_type='repository',
            model_provider='local'
        )

    @database_sync_to_async
    def save_user_message(self, conversation, content):
        """Save user message to database"""
        return ChatMessage.objects.create(
            conversation=conversation,
            role='user',
            content=content
        )

    async def handle_chat_message(self, data):
        """Handle repository chat message"""
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            await self.send_json({'type': 'error', 'error': 'Empty message'})
            return

        # Get or create conversation
        conversation = await self.get_or_create_conversation(conversation_id)

        # Save user message
        await self.save_user_message(conversation, user_message)

        # Get CRS context
        context = await self.get_crs_context(user_message)

        # Stream LLM response
        await self.stream_llm_response(user_message, context, conversation)

    @database_sync_to_async
    def get_crs_context(self, query):
        """Get relevant CRS context for the query"""
        crs_ctx = CRSContext(self.repository)
        crs_ctx.load_all()

        return {
            'summary': crs_ctx.build_context_summary(),
            'search_results': crs_ctx.search_context(query, limit=5)
        }

    async def build_llm_messages(self, conversation, user_message, context):
        """Build messages with CRS context"""
        # Get conversation history
        history = await self.get_conversation_history(conversation)

        messages = [
            {
                'role': 'system',
                'content': f"""You are a helpful coding assistant with access to this repository's code.

{context.get('summary', '')}

Use the context below to answer questions about the code:
{context.get('search_results', '')}

Be concise and specific. Reference file names and functions when relevant."""
            }
        ]

        # Add conversation history
        for msg in history:
            messages.append({
                'role': msg.role,
                'content': msg.content
            })

        # Add current user message
        messages.append({
            'role': 'user',
            'content': user_message
        })

        return messages

    @database_sync_to_async
    def get_conversation_history(self, conversation, limit=10):
        """Get recent conversation history"""
        return list(conversation.messages.order_by('-created_at')[:limit][::-1])


class PlannerChatConsumer(BaseChatConsumer):
    """
    Planner chat consumer

    Context includes all repositories in the system
    """

    async def connect(self):
        self.system_id = self.scope['url_route']['kwargs']['system_id']
        self.system = await self.get_system()

        if not self.system:
            await self.close()
            return

        await super().connect()

    @database_sync_to_async
    def get_system(self):
        """Get system from database"""
        try:
            return System.objects.get(id=self.system_id)
        except System.DoesNotExist:
            return None

    async def handle_chat_message(self, data):
        """Handle planner chat message"""
        # Similar to RepositoryChatConsumer but with multi-repo context
        await self.send_json({
            'type': 'info',
            'message': 'Planner chat coming soon!'
        })

    async def build_llm_messages(self, conversation, user_message, context):
        """Build messages for planner chat"""
        return [
            {'role': 'system', 'content': 'You are a system planner assistant.'},
            {'role': 'user', 'content': user_message}
        ]


class GraphChatConsumer(BaseChatConsumer):
    """
    Graph exploration chat consumer

    For visual queries about relationships and flows
    """

    async def connect(self):
        self.system_id = self.scope['url_route']['kwargs']['system_id']
        await super().connect()

    async def handle_chat_message(self, data):
        """Handle graph chat message"""
        await self.send_json({
            'type': 'info',
            'message': 'Graph chat coming soon!'
        })

    async def build_llm_messages(self, conversation, user_message, context):
        """Build messages for graph chat"""
        return [
            {'role': 'system', 'content': 'You are a graph exploration assistant.'},
            {'role': 'user', 'content': user_message}
        ]
