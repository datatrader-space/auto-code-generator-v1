"""
WebSocket consumers for real-time chat
"""

import json
import logging
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async

from agent.models import Repository, System, ChatConversation, ChatMessage, LLMModel, LLMRequestLog
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

    def _detect_inventory_intent(self, user_message: str):
        """
        Detect if user is asking an inventory question
        Returns (is_inventory, artifact_kind) tuple
        """
        message_lower = user_message.lower()

        # Inventory patterns
        inventory_patterns = [
            ('model', 'django_model'),
            ('serializer', 'drf_serializer'),
            ('viewset', 'drf_viewset'),
            ('api view', 'drf_apiview'),
            ('apiview', 'drf_apiview'),
            ('url', 'url_pattern'),
        ]

        # Check for inventory keywords
        inventory_keywords = ['list', 'show', 'what', 'all', 'exist', 'have', 'contains']

        has_inventory_keyword = any(kw in message_lower for kw in inventory_keywords)

        if has_inventory_keyword:
            for pattern, kind in inventory_patterns:
                if pattern in message_lower:
                    logger.info(f"Detected inventory intent: {kind}")
                    return (True, kind)

        return (False, None)

    async def stream_llm_response(self, user_message, context, conversation):
        """
        Stream LLM response in chunks with CRS tool support

        Args:
            user_message: User's message text
            context: CRS context or other relevant context
            conversation: ChatConversation instance
        """
        # Import CRS tools
        from agent.crs_tools import CRSTools

        # SERVER-SIDE INVENTORY ROUTING (highest ROI fix)
        # If user is asking for inventory, call LIST_ARTIFACTS directly
        is_inventory, artifact_kind = self._detect_inventory_intent(user_message)

        request_started = time.monotonic()
        last_usage = None
        model_info = {'provider': conversation.model_provider or 'local', 'model': None}

        if is_inventory and artifact_kind:
            logger.info(f"Server-side inventory routing: {artifact_kind}")

            await self.send_json({'type': 'assistant_typing', 'typing': True})

            try:
                crs_tools = CRSTools(repository=getattr(self, 'repository', None))

                # Execute LIST_ARTIFACTS directly
                result = await sync_to_async(crs_tools.execute_tool)(
                    'LIST_ARTIFACTS',
                    {'kind': artifact_kind}
                )

                # Send tool result
                await self.send_json({
                    'type': 'tool_result',
                    'tool_name': 'LIST_ARTIFACTS',
                    'result': result
                })

                # Let LLM format the answer
                router = await sync_to_async(get_llm_router)()
                config = {
                    'provider': conversation.model_provider or 'local'
                }
                client = await sync_to_async(router.client_for_config)(config)
                model_info = {'provider': config['provider'], 'model': config.get('model_name')}

                # Simple prompt for formatting
                format_messages = [
                    {'role': 'system', 'content': 'You are a helpful assistant. Format the tool results clearly for the user. Include file:line citations.'},
                    {'role': 'user', 'content': f"User asked: {user_message}\n\nTool Results:\n{result}\n\nPlease format this as a clear answer."}
                ]

                chunks = await sync_to_async(lambda: list(client.query_stream(format_messages)))()
                last_usage = getattr(client, 'last_usage', None)
                formatted_answer = ''.join(chunks)

                for chunk in chunks:
                    await self.send_json({
                        'type': 'assistant_message_chunk',
                        'chunk': chunk
                    })

                await self.send_json({
                    'type': 'assistant_message_complete',
                    'full_message': formatted_answer
                })

                await self.save_assistant_message(
                    conversation,
                    formatted_answer,
                    context,
                    {'provider': config['provider']}
                )
                await self.create_llm_request_log(
                    conversation=conversation,
                    model_info=model_info,
                    request_type='stream',
                    status='success',
                    latency_ms=self._calculate_latency_ms(request_started),
                    usage=last_usage
                )

                logger.info(f"Server-side inventory routing succeeded for {artifact_kind}")
                return

            except Exception as e:
                await self.create_llm_request_log(
                    conversation=conversation,
                    model_info=model_info,
                    request_type='stream',
                    status='error',
                    latency_ms=self._calculate_latency_ms(request_started),
                    usage=last_usage,
                    error=str(e)
                )
                logger.error(f"Server-side inventory routing failed: {e}")
                # Fall through to normal tool loop
            finally:
                await self.send_json({'type': 'assistant_typing', 'typing': False})

        # Normal tool-calling loop for non-inventory or if inventory routing failed
        # Build messages for LLM
        messages = await self.build_llm_messages(conversation, user_message, context)

        # Get LLM router and proper client
        router = await sync_to_async(get_llm_router)()

        # Get LLM config (handles model selection)
        llm_config = await self.get_llm_config(conversation)

        if llm_config:
            config = llm_config['config']
            client = await sync_to_async(router.client_for_config)(config)
            model_info = llm_config.get('model_info', {'provider': 'local'})
        else:
            # Fallback to basic config
            config = {'provider': conversation.model_provider or 'local'}
            client = await sync_to_async(router.client_for_config)(config)
            model_info = {'provider': config['provider']}

        # Send typing indicator
        await self.send_json({
            'type': 'assistant_typing',
            'typing': True
        })

        final_answer = ""  # Only the actual answer, not tool dumps
        debug_trace = []   # Tool calls + results for logging
        max_tool_iterations = 3  # Prevent infinite loops

        try:
            crs_tools = CRSTools(repository=getattr(self, 'repository', None))
            # Stream response chunks
            if llm_config:
                config = llm_config['config']
                client = router.client_for_config(config)
                model_info = {
                    'provider': llm_config['provider'],
                    'model': llm_config['model']
                }
            else:
                client = router.local_client if conversation.model_provider == 'local' else router.cloud_client
                model_info = {
                    'provider': conversation.model_provider,
                    'model': getattr(router.local_config if conversation.model_provider == 'local' else router.cloud_config, 'model', None)
                }
        
            client = router.local_client if model_info['provider'] == 'local' else router.cloud_client

            # Tool-calling loop
            for iteration in range(max_tool_iterations):
                logger.info(f"Tool iteration {iteration + 1}/{max_tool_iterations}")

                # Get LLM response (still buffered for now, TODO: fix streaming)
                chunks = await sync_to_async(lambda: list(client.query_stream(messages)))()
                last_usage = getattr(client, 'last_usage', None) or last_usage

                iteration_response = ""
                for text_chunk in chunks:
                    iteration_response += text_chunk

                    # Send chunk to frontend (assistant thinking/planning)
                    await self.send_json({
                        'type': 'assistant_message_chunk',
                        'chunk': text_chunk
                    })

                # Check for tool calls
                tool_calls = crs_tools.parse_tool_calls(iteration_response)

                if not tool_calls:
                    # No tools requested - this is the final answer
                    final_answer = iteration_response
                    logger.info("No tool calls found - treating as final answer")
                    break

                # Tools were requested - execute them
                logger.info(f"LLM requested {len(tool_calls)} tool(s): {[t['name'] for t in tool_calls]}")

                tool_results_for_llm = []
                for tool_call in tool_calls:
                    tool_name = tool_call['name']
                    tool_params = tool_call['parameters']

                    logger.info(f"Executing {tool_name} with params: {tool_params}")
                    result = await sync_to_async(crs_tools.execute_tool)(tool_name, tool_params)

                    # Send tool result to frontend as separate event (not mixed with assistant)
                    await self.send_json({
                        'type': 'tool_result',
                        'tool_name': tool_name,
                        'result': result
                    })

                    tool_results_for_llm.append(f"**{tool_name}:**\n{result}")
                    debug_trace.append(f"[{tool_name}] -> {len(result)} chars")

                # Combine tool results
                combined_results = '\n\n'.join(tool_results_for_llm)

                # Add assistant's tool request as message
                messages.append({
                    'role': 'assistant',
                    'content': iteration_response
                })

                # Add tool results as USER message (FIX: was 'system' before)
                messages.append({
                    'role': 'user',
                    'content': f"Tool Results:\n\n{combined_results}\n\nNow answer the user's original question using this data. Provide a clear, formatted response with citations."
                })

            # If we hit max iterations without final answer, treat last response as answer
            if not final_answer and iteration_response:
                final_answer = iteration_response
                logger.warning("Hit max tool iterations - using last response as final answer")

            # Send completion with ONLY the final answer (no tool dumps)
            await self.send_json({
                'type': 'assistant_message_complete',
                'full_message': final_answer
            })

            # Save ONLY final answer to database (no tool results pollution)
            await self.save_assistant_message(
                conversation,
                final_answer,
                context,
                model_info
            )
            await self.create_llm_request_log(
                conversation=conversation,
                model_info=model_info,
                request_type='stream',
                status='success',
                latency_ms=self._calculate_latency_ms(request_started),
                usage=last_usage
            )

            logger.info(f"Tool trace: {' -> '.join(debug_trace)}")

        except Exception as e:
            await self.create_llm_request_log(
                conversation=conversation,
                model_info=model_info,
                request_type='stream',
                status='error',
                latency_ms=self._calculate_latency_ms(request_started),
                usage=last_usage,
                error=str(e)
            )
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

    def _calculate_latency_ms(self, started_at):
        if not started_at:
            return None
        return int((time.monotonic() - started_at) * 1000)

    def _extract_token_counts(self, usage):
        if not usage:
            return {}
        prompt_tokens = usage.get('prompt_tokens')
        completion_tokens = usage.get('completion_tokens')
        total_tokens = usage.get('total_tokens')
        if prompt_tokens is None and 'input_tokens' in usage:
            prompt_tokens = usage.get('input_tokens')
        if completion_tokens is None and 'output_tokens' in usage:
            completion_tokens = usage.get('output_tokens')
        if total_tokens is None and 'total_tokens' in usage:
            total_tokens = usage.get('total_tokens')
        if total_tokens is None:
            total_tokens = usage.get('totalTokenCount')
        if prompt_tokens is None:
            prompt_tokens = usage.get('promptTokenCount')
        if completion_tokens is None:
            completion_tokens = usage.get('candidatesTokenCount')
        return {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens
        }

    @database_sync_to_async
    def create_llm_request_log(
        self,
        *,
        conversation,
        model_info,
        request_type,
        status,
        latency_ms,
        usage,
        error=None
    ):
        token_counts = self._extract_token_counts(usage)
        provider = model_info.get('provider') or 'unknown'
        model = model_info.get('model') or ''
        return LLMRequestLog.objects.create(
            user=conversation.user,
            conversation=conversation,
            provider=provider,
            model=model,
            request_type=request_type,
            status=status,
            latency_ms=latency_ms,
            prompt_tokens=token_counts.get('prompt_tokens'),
            completion_tokens=token_counts.get('completion_tokens'),
            total_tokens=token_counts.get('total_tokens'),
            error=error or ''
        )

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

    @database_sync_to_async
    def set_conversation_model(self, conversation, model_id):
        if not model_id:
            return conversation

        model = LLMModel.objects.select_related('provider').filter(
            id=model_id,
            provider__user=conversation.user
        ).first()
        if not model:
            return conversation

        conversation.llm_model = model
        conversation.model_provider = model.provider.provider_type
        conversation.save(update_fields=['llm_model', 'model_provider', 'updated_at'])
        return conversation

    @database_sync_to_async
    def get_llm_config(self, conversation):
        if not conversation.llm_model_id:
            return None

        model = LLMModel.objects.select_related('provider').filter(
            id=conversation.llm_model_id,
            provider__user=conversation.user
        ).first()
        if not model:
            return None

        from llm.router import LLMConfig
        provider = model.provider
        config = LLMConfig(
            provider=provider.provider_type,
            model=model.model_id,
            base_url=provider.base_url or None,
            api_key=provider.api_key or None,
            max_tokens=model.metadata.get('max_tokens') or provider.metadata.get('max_tokens') or 4000,
            temperature=model.metadata.get('temperature') or provider.metadata.get('temperature') or 0.7
        )
        return {
            'provider': provider.provider_type,
            'model': model.model_id,
            'config': config
        }

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
        model_id = data.get('model_id')
        message_id = data.get('message_id')

        if not user_message:
            await self.send_json({'type': 'error', 'error': 'Empty message'})
            return

        logger.info(
            "Repository chat message received (message_id=%s, conversation_id=%s)",
            message_id,
            conversation_id
        )

        # Get or create conversation
        is_new = conversation_id is None
        conversation = await self.get_or_create_conversation(conversation_id)

        # If new conversation, notify frontend
        if is_new:
            await self.send_json({
                'type': 'conversation_created',
                'conversation_id': conversation.id
            })

        conversation = await self.set_conversation_model(conversation, model_id)

        # Save user message
        await self.save_user_message(conversation, user_message)

        # Get CRS context
        context = await self.get_crs_context(user_message)

        # Stream LLM response
        await self.stream_llm_response(user_message, context, conversation)

    @database_sync_to_async
    def get_crs_context(self, query):
        """
        Get CRS context - tool-first approach

        No longer returns search blobs - tools handle data retrieval
        Just checks if CRS is ready
        """
        from agent.services.crs_runner import get_crs_summary

        try:
            summary = get_crs_summary(self.repository)

            if summary.get('status') != 'ready':
                return {
                    'status_message': f"CRS status: {summary.get('status', 'unknown')}. Analysis must complete first."
                }

            # CRS is ready - return minimal context
            # Tools will handle actual data retrieval
            return {
                'crs_ready': True,
                'artifact_count': summary.get('artifacts', 0)
            }

        except Exception as e:
            logger.warning(f"CRS context error: {e}")
            return {
                'status_message': f"CRS not available: {str(e)}"
            }

    async def build_llm_messages(self, conversation, user_message, context):
        """
        Build messages with tool-first approach

        Forces LLM to plan tool usage before answering
        """
        from agent.crs_tools import CRSTools
        from agent.services.crs_runner import get_crs_summary

        # Get conversation history
        history = await self.get_conversation_history(conversation)

        status_message = context.get('status_message')

        # Get tool definitions
        crs_tools = CRSTools(repository=self.repository)
        tool_definitions = crs_tools.get_tool_definitions()

        # Get CRS status summary for context
        crs_status_context = ""
        try:
            summary = await sync_to_async(get_crs_summary)(self.repository)
            crs_status_context = f"""
# Repository CRS Status

- Repository: {self.repository.name}
- Status: {summary.get('status', 'unknown')}
- Django Models: ~{summary.get('artifacts', 0) // 4} (estimated)
- Total Artifacts: {summary.get('artifacts', 0)}
- Blueprint Files: {summary.get('blueprint_files', 0)}
- Relationships: {summary.get('relationships', 0)}

This gives you context on what data is available.
"""
        except Exception as e:
            logger.warning(f"Could not load CRS summary: {e}")

        # Build tool-first system prompt with router
        system_prompt = f"""You are a code repository assistant with access to CRS (Contextual Retrieval System) tools.

{crs_status_context}

# YOUR JOB

1. **PLAN** which tools to use
2. **REQUEST** tools in the JSON format below
3. **WAIT** for tool results
4. **ANSWER** the user's question with citations

---

{tool_definitions}

---

# CRITICAL: Inventory Questions

For "list/show all/what X exist" questions, you MUST use LIST_ARTIFACTS.
NEVER answer from memory or make assumptions.

Examples of inventory questions:
- "What models exist?"
- "List all serializers"
- "Show me viewsets"
- "What are the models?"

---

Now answer the user's question using the appropriate tools."""

        if status_message:
            system_prompt = f"""You are analyzing a code repository.

CRS Status: {status_message}

The CRS system is not ready yet. Please explain to the user that:
1. CRS analysis must be run on this repository first
2. They should wait for CRS to complete, then try again
3. CRS provides structured code knowledge (blueprints, artifacts, relationships)

Keep your response brief and helpful."""

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

        logger.info(f"Built tool-first prompt with {len(system_prompt)} chars")
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
        model_id = data.get('model_id')

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

        conversation = await self.set_conversation_model(conversation, model_id)

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
        """Build messages for planner chat - multi-repo tool-based planning"""
        # Get conversation history
        history = await self.get_conversation_history(conversation)

        repo_list = '\n'.join([f"- {repo['name']}" for repo in context.get('repositories', [])])

        # Tool-first system prompt for multi-repo planning
        # Note: For now, planner uses simpler context-based approach
        # TODO: Implement multi-repo CRS tools in future
        system_prompt = f"""You are a multi-repository planner with access to code from multiple repositories.

# System Repositories
{repo_list}

# Your Planning Process

1. **ANALYZE** code structure across all repositories
2. **IDENTIFY** files and components that need changes
3. **CONSIDER** cross-repository dependencies
4. **PROVIDE** step-by-step implementation plan

# Planning Guidelines

- Be specific about file paths and component names
- Consider API contracts between repositories
- Think about data flow and dependencies
- Provide actionable implementation steps

# Example Planning Format

**Repository: backend**
- Modify `agent/models.py:45` - add User.email field
- Update `agent/serializers.py:120` - add email to UserSerializer

**Repository: frontend**
- Update `src/components/UserForm.vue:30` - add email input field
- Modify `src/services/api.js:15` - include email in API calls

**Dependencies:**
- Frontend calls `POST /api/users/` with email field
- Backend validates email format before saving

Now create a plan for the user's request with specific file:line references."""

        messages = [
            {
                'role': 'system',
                'content': system_prompt
            }
        ]

        # Add conversation history (last 5 messages)
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

        logger.info(f"Built planner prompt with {len(system_prompt)} chars")
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
        model_id = data.get('model_id')

        if not user_message:
            await self.send_json({'type': 'error', 'error': 'Empty message'})
            return

        # Get or create conversation
        conversation = await self.get_or_create_conversation(conversation_id)

        conversation = await self.set_conversation_model(conversation, model_id)

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
