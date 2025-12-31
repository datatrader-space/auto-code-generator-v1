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
from agent.rag import CRSRetriever, ConversationMemory
from agent.knowledge.crs_documentation import (
    get_system_prompt,
    get_crs_documentation_context
)
from llm.router import get_llm_router
from django.contrib.auth import get_user_model
User = get_user_model()

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

            # Get all chunks from the generator (sync operation converted to async)
            chunks = await sync_to_async(lambda: list(client.query_stream(messages)))()

            # Iterate over chunks
            for text_chunk in chunks:
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

        # Get actual user instance (resolve lazy object)
      
        user = self.scope['user']
        if user.is_authenticated:
            user = User.objects.get(pk=user.pk)
        else:
            # Use admin user for anonymous sessions (for development)
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                user = User.objects.first()

        # Create new conversation
        return ChatConversation.objects.create(
            user=user,
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
        is_new = conversation_id is None
        conversation = await self.get_or_create_conversation(conversation_id)

        # If new conversation, notify frontend
        if is_new:
            await self.send_json({
                'type': 'conversation_created',
                'conversation_id': conversation.id
            })

        # Save user message
        await self.save_user_message(conversation, user_message)

        # Get CRS context
        context = await self.get_crs_context(user_message)

        # Stream LLM response
        await self.stream_llm_response(user_message, context, conversation)

    @database_sync_to_async
    def get_crs_context(self, query):
        """Get relevant CRS context for the query using RAG"""
        # Use RAG retriever to find relevant blueprints and artifacts
        retriever = CRSRetriever(repository=self.repository)

        # Build context with CRS documentation + search results
        context_prompt = retriever.build_context_prompt(query)

        # Also get CRS documentation for teaching the model
        crs_docs = get_crs_documentation_context()

        return {
            'crs_documentation': crs_docs,
            'search_results': context_prompt
        }

    async def build_llm_messages(self, conversation, user_message, context):
        """Build messages with CRS context - simplified for local LLM performance"""
        # Get conversation history
        history = await self.get_conversation_history(conversation)

        # Simplified system prompt for better local LLM performance
        search_results = context.get('search_results', '')

        # Create concise system prompt
        system_prompt = f"""You are analyzing a code repository. Below is relevant code from the repository:

{search_results}

Instructions:
- Answer using the code context above
- Reference specific files and classes
- Be concrete and specific
- If context is insufficient, say so"""

        messages = [
            {
                'role': 'system',
                'content': system_prompt
            }
        ]

        # Add conversation history (last 5 messages for context)
        for msg in history[-5:]:
            messages.append({
                'role': msg.role,
                'content': msg.content
            })

        # Add current user message
        messages.append({
            'role': 'user',
            'content': user_message
        })

        logger.info(f"Built prompt with {len(system_prompt)} chars of context")
        return messages

    @database_sync_to_async
    def get_conversation_history(self, conversation, limit=10):
        """Get recent conversation history"""
        return list(conversation.messages.order_by('-created_at')[:limit][::-1])


class PlannerChatConsumer(BaseChatConsumer):
    """
    Planner chat consumer

    Context includes all repositories in the system
    Allows planning across multiple repositories
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
            return System.objects.prefetch_related('repositories').get(id=self.system_id)
        except System.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_conversation(self, conversation_id=None):
        """Get existing or create new planner conversation"""
        if conversation_id:
            try:
                return ChatConversation.objects.get(
                    id=conversation_id,
                    system=self.system,
                    conversation_type='planner'
                )
            except ChatConversation.DoesNotExist:
                pass

        # Get actual user instance (resolve lazy object)
        
        user = self.scope['user']
        if user.is_authenticated:
            user = User.objects.get(pk=user.pk)
        else:
            # Use admin user for anonymous sessions (for development)
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                user = User.objects.first()

        # Create new conversation
        return ChatConversation.objects.create(
            user=user,
            system=self.system,
            conversation_type='planner',
            title='Planner Chat',
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
        """Handle planner chat message"""
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            await self.send_json({'type': 'error', 'error': 'Empty message'})
            return

        # Get or create conversation
        is_new = conversation_id is None
        conversation = await self.get_or_create_conversation(conversation_id)

        # If new conversation, notify frontend
        if is_new:
            await self.send_json({
                'type': 'conversation_created',
                'conversation_id': conversation.id
            })

        # Save user message
        await self.save_user_message(conversation, user_message)

        # Get multi-repo context
        context = await self.get_multi_repo_context(user_message)

        # Stream LLM response
        await self.stream_llm_response(user_message, context, conversation)

    @database_sync_to_async
    def get_multi_repo_context(self, query):
        """Get context from all repositories in the system using RAG"""
        repos = list(self.system.repositories.filter(crs_status='completed'))

        if not repos:
            return {
                'repositories': [],
                'crs_documentation': get_crs_documentation_context(),
                'summary': 'No repositories with CRS analysis found in this system.',
                'search_results': ''
            }

        # Build context from all repositories using RAG
        repo_contexts = []
        all_search_results = []

        for repo in repos:
            try:
                # Use RAG retriever for each repository
                retriever = CRSRetriever(repository=repo)
                context_prompt = retriever.build_context_prompt(query)

                repo_contexts.append({
                    'name': repo.name,
                    'summary': f"Repository: {repo.name}"
                })

                if context_prompt.strip():
                    all_search_results.append(f"\n### Repository: {repo.name}\n{context_prompt}")

            except Exception as e:
                logger.error(f"Error loading CRS context for {repo.name}: {e}")
                repo_contexts.append({
                    'name': repo.name,
                    'error': str(e)
                })

        # Combine all search results
        combined_search = '\n'.join(all_search_results) if all_search_results else 'No relevant code found.'

        return {
            'repositories': repo_contexts,
            'crs_documentation': get_crs_documentation_context(),
            'summary': f"System has {len(repos)} repositories with CRS analysis.",
            'search_results': combined_search
        }

    async def build_llm_messages(self, conversation, user_message, context):
        """Build messages for planner chat with multi-repo context"""
        # Get conversation history
        history = await self.get_conversation_history(conversation)

        # Get planner system prompt
        system_prompt = get_system_prompt('planner')

        # Build repo list
        repo_list = '\n'.join([
            f"- {repo['name']}"
            for repo in context.get('repositories', [])
        ])

        # Build full system prompt
        full_system_prompt = f"""{system_prompt}

---

{context.get('crs_documentation', '')}

---

# System Overview

{context.get('summary', '')}

Available Repositories:
{repo_list}

---

# Context for Current Query

{context.get('search_results', '')}

---

Answer the user's question using the blueprints, artifacts, and relationships provided above.
Consider cross-repository dependencies and plan changes accordingly."""

        messages = [
            {
                'role': 'system',
                'content': full_system_prompt
            }
        ]

        # Add conversation history (last 10 messages)
        for msg in history[-10:]:
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


class GraphChatConsumer(BaseChatConsumer):
    """
    Graph exploration chat consumer

    For visual queries about relationships, flows, and architecture
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
            return System.objects.prefetch_related('repositories').get(id=self.system_id)
        except System.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_conversation(self, conversation_id=None):
        """Get existing or create new graph conversation"""
        if conversation_id:
            try:
                return ChatConversation.objects.get(
                    id=conversation_id,
                    system=self.system,
                    conversation_type='graph'
                )
            except ChatConversation.DoesNotExist:
                pass

        # Get actual user instance (resolve lazy object)
        
        user = self.scope['user']
        if user.is_authenticated:
            user = User.objects.get(pk=user.pk)
        else:
            # Use admin user for anonymous sessions (for development)
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                user = User.objects.first()

        # Create new conversation
        return ChatConversation.objects.create(
            user=user,
            system=self.system,
            conversation_type='graph',
            title='Graph Exploration',
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
        """Handle graph chat message"""
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            await self.send_json({'type': 'error', 'error': 'Empty message'})
            return

        # Get or create conversation
        conversation = await self.get_or_create_conversation(conversation_id)

        # Save user message
        await self.save_user_message(conversation, user_message)

        # Get graph context (relationships across all repos)
        context = await self.get_graph_context(user_message)

        # Stream LLM response
        await self.stream_llm_response(user_message, context, conversation)

    @database_sync_to_async
    def get_graph_context(self, query):
        """Get relationship graph context from all repositories"""
        repos = list(self.system.repositories.filter(crs_status='completed'))

        if not repos:
            return {
                'repositories': [],
                'summary': 'No repositories with CRS analysis found.',
                'relationships': {}
            }

        # Build relationship graph from all repositories
        all_relationships = {}
        repo_summaries = []

        for repo in repos:
            try:
                crs_ctx = CRSContext(repo)
                crs_ctx.load_all()

                # Get relationships
                relationships = crs_ctx._relationships or {}

                # Add repo context to relationships
                for artifact, rel_data in relationships.items():
                    key = f"{repo.name}::{artifact}"
                    all_relationships[key] = {
                        'repository': repo.name,
                        'artifact': artifact,
                        **rel_data
                    }

                repo_summaries.append({
                    'name': repo.name,
                    'artifact_count': len(crs_ctx._artifacts or {}),
                    'relationship_count': len(relationships)
                })

            except Exception as e:
                logger.error(f"Error loading graph context for {repo.name}: {e}")

        # Find relevant relationships based on query
        query_lower = query.lower()
        relevant_relationships = {
            k: v for k, v in all_relationships.items()
            if query_lower in k.lower() or query_lower in str(v).lower()
        }

        # Format relationship summary
        rel_summary = ""
        if relevant_relationships:
            rel_summary = "\n\nRelevant Relationships:\n"
            for key, rel_data in list(relevant_relationships.items())[:10]:
                rel_summary += f"\n{key}:\n"
                if rel_data.get('imports'):
                    rel_summary += f"  Imports: {', '.join(rel_data['imports'][:5])}\n"
                if rel_data.get('calls'):
                    rel_summary += f"  Calls: {', '.join(rel_data['calls'][:5])}\n"
                if rel_data.get('used_by'):
                    rel_summary += f"  Used by: {', '.join(rel_data['used_by'][:5])}\n"

        return {
            'repositories': repo_summaries,
            'summary': f"System has {len(repos)} repositories. Found {len(all_relationships)} total relationships.",
            'relationships': relevant_relationships,
            'relationship_summary': rel_summary
        }

    async def build_llm_messages(self, conversation, user_message, context):
        """Build messages for graph chat with relationship context"""
        # Get conversation history
        history = await self.get_conversation_history(conversation)

        # Build repository summary
        repo_list = '\n'.join([
            f"- {repo['name']}: {repo['artifact_count']} artifacts, {repo['relationship_count']} relationships"
            for repo in context.get('repositories', [])
        ])

        messages = [
            {
                'role': 'system',
                'content': f"""You are a code architecture and relationship exploration assistant.

System Overview:
{context.get('summary', '')}

Repositories:
{repo_list}

{context.get('relationship_summary', '')}

Your role:
- Help visualize and understand code relationships
- Explain dependency flows and call chains
- Identify architectural patterns
- Suggest relationship improvements
- Trace data flows through the system
- Identify circular dependencies or coupling issues

Be specific and reference repository names, artifacts, and relationship types."""
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
