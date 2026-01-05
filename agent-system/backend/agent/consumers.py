"""
WebSocket consumers for real-time chat
"""

import json
import logging
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async

from agent.models import Repository, System, ChatConversation, ChatMessage, LLMModel, LLMRequestLog, ContextFile
from agent.services.crs_context import CRSContext
from agent.rag import CRSRetriever, ConversationMemory
from agent.knowledge.crs_documentation import (
    get_system_prompt,
    get_crs_documentation_context
)
from llm.router import get_llm_router
from django.contrib.auth import get_user_model
from django.utils import timezone
from agent.services.agent_runner import AgentRunner
from agent.services.knowledge_agent import RepositoryKnowledgeAgent
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
            ('route', 'url_pattern'),
            ('endpoint', 'url_pattern'),
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
                from llm.router import LLMConfig
                router = await sync_to_async(get_llm_router)()
                
                provider_type = conversation.model_provider or 'ollama'
                config = LLMConfig(
                    provider=provider_type,
                    model=None, #/default
                    base_url='http://localhost:11434', # Prevent NoneType error in Ollama client
                    max_tokens=4000
                )
                
                client = await sync_to_async(router.client_for_config)(config)
                model_info = {'provider': provider_type, 'model': None}

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
                """ await self.create_llm_request_log(
                    conversation=conversation,
                    model_info=model_info,
                    request_type='stream',
                    status='error',
                    latency_ms=self._calculate_latency_ms(request_started),
                    usage=last_usage,
                    error=str(e)
                ) """
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
            model_info = llm_config.get('model_info', {'provider': 'ollama'})
        else:
            # Fallback to basic config
            from llm.router import LLMConfig
            config = LLMConfig(
                provider=conversation.model_provider or 'ollama',
                model=None,
                base_url='http://localhost:11434' if (conversation.model_provider or 'ollama') == 'ollama' else None
            )
            client = await sync_to_async(router.client_for_config)(config)
            model_info = {'provider': config.provider}

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
                # Removed redundant model_info block
            else:
                 # Standard router logic handled above
                 pass
            print(model_info)
            # Removed hardcoded client overwrite logic
            # client = router.local_client if model_info['provider'] == 'ollama' else router.cloud_client

            # Tool-calling loop
            for iteration in range(max_tool_iterations):
                logger.info(f"Tool iteration {iteration + 1}/{max_tool_iterations}")

                # FIX: Re-inject system reminder if history is getting long to prevent context drift
                if iteration > 0:
                     messages.append({
                        'role': 'system', 
                        'content': f"REMINDER: You are the code repository assistant. You just received tool results. Use them to answer the user's question: '{user_message}'.\n\nDO NOT simulate a conversation. DO NOT generate 'User:' or 'Assistant:' lines. Just provide the answer."
                     })

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
                
                logger.info(f"LLM Response (Iteration {iteration+1}): {iteration_response[:200]}...")

                # Check for tool calls - robust parsing
                import json, re
                tool_calls = []
                
                # 1. Try to find JSON blocks using brace counting (handles nested dicts)
                cursor = 0
                while True:
                    start_brace = iteration_response.find('{', cursor)
                    if start_brace == -1:
                        break
                    
                    depth = 0
                    end_brace = -1
                    for i in range(start_brace, len(iteration_response)):
                        if iteration_response[i] == '{':
                            depth += 1
                        elif iteration_response[i] == '}':
                            depth -= 1
                            if depth == 0:
                                end_brace = i
                                break
                    
                    if end_brace != -1:
                        json_str = iteration_response[start_brace:end_brace+1]
                        try:
                            call = json.loads(json_str)
                            # Normalize keys
                            tool_name = call.get('tool') or call.get('name') or call.get('action') or call.get('function')
                            params = call.get('parameters') or call.get('arguments') or call.get('params') or call.get('args') or {}
                            
                            if tool_name and isinstance(tool_name, str):
                                tool_calls.append({'name': tool_name, 'parameters': params})
                        except:
                            pass
                        cursor = end_brace + 1
                    else:
                        cursor = start_brace + 1

                # 2. Key-value function search Fallback: TOOL_NAME(key="val") OR TOOL_NAME("val", "val")
                if not tool_calls:
                    func_pattern = r'([A-Z_]+)\((.*?)\)'
                    func_matches = re.findall(func_pattern, iteration_response, re.DOTALL)
                    for tool_name, params_str in func_matches:
                        if tool_name in ["JSON", "TOOL", "CALL"]: continue # Skip false positives
                        
                        param_dict = {}
                        # Try key="value"
                        kv_pairs = list(re.finditer(r'(\w+)=["\'](.*?)["\']', params_str))
                        if kv_pairs:
                            for param_match in kv_pairs:
                                param_dict[param_match.group(1)] = param_match.group(2)
                        
                        # Fallback: Positional args "val1", "val2"
                        elif params_str.strip():
                             # Naive split by comma inside quotes - robust enough for simple calls
                             # matches "val1", "val2" or 'val1', 'val2'
                             parts = [p.strip().strip('"').strip("'") for p in params_str.split(',')]
                             if tool_name in ['WRITE_FILE', 'CREATE_FILE'] and len(parts) >= 1:
                                  param_dict = {'path': parts[0], 'content': parts[1] if len(parts) > 1 else ''}
                             elif tool_name == 'READ_FILE' and len(parts) >= 1:
                                  param_dict = {'path': parts[0]}
                        
                        if param_dict or (not params_str.strip()):
                            tool_calls.append({'name': tool_name, 'parameters': param_dict})
                
                logger.info(f"Parsed {len(tool_calls)} valid tool calls: {tool_calls}")

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
                    
                    # Notify frontend of tool call
                    await self.send_json({
                        'type': 'tool_call',
                        'tool': tool_name,
                        'tool_input': tool_params
                    })

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

            # Send completion with final answer AND trace data
            await self.send_json({
                'type': 'assistant_message_complete',
                'full_message': final_answer,
                'trace': debug_trace
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
            """  await self.create_llm_request_log(
                conversation=conversation,
                model_info=model_info,
                request_type='stream',
                status='error',
                latency_ms=self._calculate_latency_ms(request_started),
                usage=last_usage,
                error=str(e)
            ) """
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
        
        # Return final answer for session tracking
        return final_answer

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
        print(model_info)
        return True
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

        # Allow connection even if repository is None (Free Agent mode)
        # self.repository will be None if ID is 0 or invalid
        if not self.repository and str(self.repository_id) != '0':
            # Only close if it was a real ID that failed lookup, 
            # but for now let's be permissive to support '0'
            pass

        # Initialize sub-agents
        self._agent_runner = None
        self._knowledge_agent = None

        await super().connect()

    @property
    def agent_runner(self):
        """Lazy-load Agent Runner"""
        if self._agent_runner is None:
            from asgiref.sync import async_to_sync
            
            def socket_callback(event):
                """Bridge synchronous agent execution to asynchronous WebSocket consumer"""
                async_to_sync(self.send_json)(event)

            self._agent_runner = AgentRunner(
                repository=self.repository,
                socket_callback=socket_callback
            )
        return self._agent_runner

    @property
    def knowledge_agent(self):
        """Lazy-load Knowledge Agent"""
        if self._knowledge_agent is None:
            self._knowledge_agent = RepositoryKnowledgeAgent(self.repository)
        return self._knowledge_agent

    @database_sync_to_async
    def get_repository(self):
        """Get repository from database"""
        try:
            return Repository.objects.select_related('system').get(id=self.repository_id)
        except Repository.DoesNotExist:
            return None

    @database_sync_to_async
    def get_llm_config(self, conversation):
        """Get LLM configuration for this conversation, prioritizing agent profile's default_model"""
        from llm.router import LLMConfig
        from agent.models import AgentProfile
        
        # Check if conversation is linked to an agent profile
        if conversation.metadata and conversation.metadata.get('agent_profile_id'):
            try:
                agent_profile = AgentProfile.objects.select_related('default_model__provider').get(
                    id=conversation.metadata['agent_profile_id']
                )
                if agent_profile.default_model:
                    # Use agent's configured model
                    llm_model = agent_profile.default_model
                    config = LLMConfig(
                        provider=llm_model.provider.provider_type,
                        model=llm_model.model_id,
                        base_url=llm_model.provider.base_url
                    )
                    return {
                        'config': config,
                        'model_info': {
                            'provider': llm_model.provider.provider_type,
                            'model_name': llm_model.name,
                            'model_id': llm_model.model_id
                        }
                    }
            except AgentProfile.DoesNotExist:
                pass
        
        # Fallback to conversation's llm_model if set
        if conversation.llm_model:
            config = LLMConfig(
                provider=conversation.llm_model.provider.provider_type,
                model=conversation.llm_model.model_id,
                base_url=conversation.llm_model.provider.base_url
            )
            return {
                'config': config,
                'model_info': {
                    'provider': conversation.llm_model.provider.provider_type,
                    'model_name': conversation.llm_model.name
                }
            }
        
        # No specific model configured
        return None

    @database_sync_to_async
    def get_or_create_conversation(self, conversation_id=None):
        """Get existing or create new conversation"""
        if conversation_id:
            try:
                # If we have a repository, prefer matching it, but allow loose match if self.repository is None
                # or if the conversation is decoupled.
                if self.repository:
                    return ChatConversation.objects.select_related('llm_model').get(
                        id=conversation_id,
                        repository=self.repository
                    )
                else:
                    return ChatConversation.objects.select_related('llm_model').get(id=conversation_id)
            except ChatConversation.DoesNotExist:
                 # Try finding it without repo filter if we are in free mode or repo mismatch
                 if self.repository:
                     try:
                         return ChatConversation.objects.select_related('llm_model').get(id=conversation_id)
                     except ChatConversation.DoesNotExist:
                         return None
                 return None
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
        """
        Handle repository chat message - Super Agent Router
        """
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

        # --- CREATE SESSION LOG ---
        import uuid
        import time
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        session_start_time = time.time()
        
        session = await self._create_session_log(
            session_id=session_id,
            user_request=user_message,
            conversation=conversation
        )

        # --- INTENT CLASSIFICATION ---
        # Determine if this is a conversational request or an automated task
        intent = await self._classify_intent(user_message)
        logger.info(f"Classified intent for message: {intent}")
        
        # Update session with intent
        await self._update_session_log(session, intent_classified_as=intent)

        if intent == 'TASK':
            await self._handle_task_request(user_message, conversation, session, session_start_time)
        else:
            await self._handle_chat_request(user_message, conversation, session, session_start_time)

    async def _handle_chat_request(self, user_message, conversation, session, session_start_time):
        """Handle standard conversational (RAG) request"""
        import time
        
        steps = []
        tools_used = []
        response_text = ""
        
        try:
            # Get CRS context
            context_start = time.time()
            context = await self.get_crs_context(user_message)
            context_duration = int((time.time() - context_start) * 1000)

            # Track context retrieval as implicit tool usage
            context_summary = {
                'blueprints_found': len(context.get('blueprints', [])) if isinstance(context.get('blueprints'), list) else 0,
                'artifacts_found': len(context.get('artifacts', [])) if isinstance(context.get('artifacts'), list) else 0,
                'relationships_found': len(context.get('relationships', [])) if isinstance(context.get('relationships'), list) else 0,
            }
            
            # Track CRS search as a step if context was retrieved
            if context.get('crs_ready'):
                tools_used.append('SEARCH_CRS')
                
                # Get actual artifacts for detailed tracking
                artifacts_detail = []
                blueprints_detail = []
                relationships_detail = []
                
                # Capture artifacts with more detail
                if isinstance(context.get('artifacts'), list):
                    for a in context.get('artifacts', [])[:20]:  # First 20 artifacts
                        artifact_info = {
                            'name': a.get('name', 'Unknown'),
                            'type': a.get('type', 'Unknown'),
                            'file': a.get('file_path') or a.get('file', 'Unknown'),
                            'description': a.get('description', '')[:200] if a.get('description') else '',
                            'content_preview': a.get('content', '')[:300] if a.get('content') else ''
                        }
                        artifacts_detail.append(artifact_info)
                
                # Capture blueprints
                if isinstance(context.get('blueprints'), list):
                    for b in context.get('blueprints', [])[:10]:
                        blueprint_info = {
                            'file': b.get('file', 'Unknown'),
                            'content_preview': b.get('content', '')[:200] if b.get('content') else ''
                        }
                        blueprints_detail.append(blueprint_info)
                
                # Capture relationships
                if isinstance(context.get('relationships'), list):
                    for r in context.get('relationships', [])[:10]:
                        rel_info = {
                            'from': r.get('from', 'Unknown'),
                            'to': r.get('to', 'Unknown'),
                            'type': r.get('type', 'Unknown')
                        }
                        relationships_detail.append(rel_info)
                
                steps.append({
                    'action': 'SEARCH_CRS',
                    'params': {'query': user_message},
                    'result': {
                        'artifacts_found': context.get('artifact_count', 0),
                        'context_summary': context_summary,
                        'artifacts': artifacts_detail,
                        'blueprints': blueprints_detail,
                        'relationships': relationships_detail,
                        'crs_status': 'ready',
                        'search_quality': 'high' if len(artifacts_detail) > 5 else 'medium' if len(artifacts_detail) > 0 else 'low'
                    },
                    'duration_ms': context_duration,
                    'status': 'success'
                })
            else:
                # CRS not ready, track as limited search
                tools_used.append('SEARCH_CRS')
                steps.append({
                    'action': 'SEARCH_CRS',
                    'params': {'query': user_message},
                    'result': {
                        'crs_status': context.get('status_message', 'not ready'),
                        'artifacts_found': 0
                    },
                    'duration_ms': context_duration,
                    'status': 'limited'
                })

            # Stream LLM response and capture it
            llm_start = time.time()
            
            # Build messages to see what we're sending to LLM
            llm_messages = await self.build_llm_messages(conversation, user_message, context)
            
            response_text = await self.stream_llm_response(user_message, context, conversation)
            llm_duration = int((time.time() - llm_start) * 1000)
            
            # Track LLM call as a step with detailed info
            tools_used.append('LLM_QUERY')
            steps.append({
                'action': 'LLM_QUERY',
                'params': {
                    'user_message': user_message,
                    'context_size': len(str(context)),
                    'message_count': len(llm_messages),
                    'system_prompt_length': len(llm_messages[0].get('content', '')) if llm_messages else 0
                },
                'result': {
                    'response_length': len(response_text) if response_text else 0,
                    'response_preview': response_text[:200] if response_text else 'No response',
                    'model_used': await sync_to_async(lambda: conversation.llm_model.name if conversation.llm_model else 'default')()
                },
                'duration_ms': llm_duration,
                'status': 'success'
            })
            
            # Complete session with captured data
            duration_ms = int((time.time() - session_start_time) * 1000)
            await self._update_session_log(
                session,
                status='success',
                completed_at=timezone.now(),
                duration_ms=duration_ms,
                final_answer=response_text if response_text else 'Response generated but not captured',
                steps=steps,
                tools_called=tools_used,
                knowledge_context={
                    **session.knowledge_context,
                    'context_retrieved': context_summary,
                    'tools_executed': len(steps),
                    'total_duration_ms': duration_ms,
                    'context_retrieval_ms': context_duration,
                    'llm_query_ms': llm_duration
                }
            )
        except Exception as e:
            logger.error(f"Chat request failed: {e}", exc_info=True)
            await self._update_session_log(
                session,
                status='failed',
                error_message=str(e),
                completed_at=timezone.now(),
                steps=steps,
                tools_called=tools_used,
                final_answer=response_text if response_text else None
            )
            raise

    async def _handle_task_request(self, user_message, conversation, session, session_start_time):
        """Handle autonomous task request via Agent Runner"""
        import time
        
        try:
            # Update session type
            await self._update_session_log(session, session_type='task')
            
            await self.send_json({
                'type': 'agent_event',
                'event': 'session_start',
                'data': {'status': 'planning', 'message': 'Handing over to Agent Runner...', 'session_id': session.session_id}
            })
            
            # Execute Agent Runner in a thread (since it is synchronous)
            # We use the lazy-loaded self.agent_runner which has the socket_callback wired up
            result = await sync_to_async(self.agent_runner.execute)(
                session_id=session.session_id,
                request=user_message
            )
            
            # Extract execution data from agent runner's current_session
            agent_session_data = self.agent_runner.current_session
            
            # Complete session with captured execution data
            duration_ms = int((time.time() - session_start_time) * 1000)
            await self._update_session_log(
                session,
                status='success' if result.get('status') == 'success' else 'failed',
                completed_at=timezone.now(),
                duration_ms=duration_ms,
                plan=agent_session_data.get('plan'),
                steps=agent_session_data.get('steps', []),
                tools_called=self._extract_tools_called(agent_session_data),
                final_answer=self._extract_final_answer(agent_session_data),
                artifacts_used=agent_session_data.get('patches_applied', []),
                error_message=agent_session_data.get('error') if result.get('status') != 'success' else None
            )
            
            await self.send_json({
                'type': 'agent_event',
                'event': 'session_complete',
                'data': {'status': 'completed', 'message': 'Agent Runner finished.', 'session_id': session.session_id}
            })

        except Exception as e:
            logger.error(f"Agent Runner Execution Error: {e}", exc_info=True)
            
            await self._update_session_log(
                session,
                status='failed',
                error_message=str(e),
                completed_at=timezone.now()
            )
            
            await self.send_json({
                'type': 'error',
                'error': f"Agent Runner failed: {str(e)}"
            })
    
    def _extract_final_answer(self, agent_session_data):
        """Extract final answer from agent execution"""
        # Try to get answer from last QUERY step
        steps = agent_session_data.get('steps', [])
        for step in reversed(steps):
            if step.get('action') in ['QUERY', 'SEARCH']:
                data = step.get('data', {})
                answer = data.get('answer')
                if answer:
                    return answer[:1000]  # First 1000 chars
        
        # Fallback: return status message
        return f"Task completed with status: {agent_session_data.get('status')}"
    
    def _extract_tools_called(self, agent_session_data):
        """Extract list of tools/actions called from steps"""
        steps = agent_session_data.get('steps', [])
        tools = []
        for step in steps:
            action = step.get('action')
            if action and action not in tools:
                tools.append(action)
        return tools

    @database_sync_to_async
    def _create_session_log(self, session_id, user_request, conversation):
        """Create initial session log entry"""
        from agent.models import AgentSession
        
        return AgentSession.objects.create(
            session_id=session_id,
            conversation=conversation,
            repository=self.repository,
            session_type='chat',  # Will be updated if it becomes a task
            user_request=user_request,
            status='running',
            knowledge_context={
                'architecture_style': self.repository.config.get('paradigm', 'unknown') if (self.repository and self.repository.config) else 'unknown',
                'domain': self.repository.config.get('domain', 'unknown') if (self.repository and self.repository.config) else 'unknown',
            }
        )
    
    @database_sync_to_async
    def _update_session_log(self, session, **kwargs):
        """Update session log fields"""
        for key, value in kwargs.items():
            setattr(session, key, value)
        session.save()
        return session

    async def _classify_intent(self, user_message):
        """
        Classify user intent: 'CHAT' vs 'TASK'
        
        Simple heuristic + fast LLM check.
        """
        # Fast heuristics
        lower_msg = user_message.lower()
        if any(w in lower_msg for w in ['create', 'implement', 'refactor', 'fix', 'change', 'update', 'delete', 'add']):
            # Likely a task, but verify with LLM to avoid false positives on "How do I create..."
            # For now, let's trust the router if configured, otherwise default to CHAT if ambiguous
            pass

        try:
            # Use small/fast model for classification
            router = get_llm_router()
            
            messages = [
                {"role": "system", "content": "You are a classifier. Output ONLY valid JSON."},
                {"role": "user", "content": f"""Classify this message into one of two categories:
1. CHAT: The user is asking a question, asking for explanation, or general conversation.
2. TASK: The user is explicitly asking for files to be created, modified, code to be written/refactored, or an action to be performed on the codebase.

User message: "{user_message}"

Output ONLY the JSON: {{"intent": "CHAT" | "TASK"}}"""}
            ]
            
            response = router.query(messages, json_mode=True)
            content = response.get('content', '')
            
            # Basic parsing
            if '"intent": "TASK"' in content or "'intent': 'TASK'" in content:
                return 'TASK'
            return 'CHAT'

        except Exception as e:
            logger.warning(f"Intent classification failed: {e}. Defaulting to CHAT.")
            return 'CHAT'

    async def get_crs_context(self, query):
        """
        Get CRS context - tool-first approach (Enhanced for Super Agent)
        Now explicitly checks for RepositoryKnowledgeAgent readiness.
        """
        from agent.services.crs_runner import get_crs_summary

        try:
            summary = get_crs_summary(self.repository)

            if summary.get('status') != 'ready':
                # FIX: Do not block tools. Return partial context.
                return {
                    'crs_ready': False,
                    'status_message': f"Analysis incomplete ({summary.get('status', 'unknown')}). Semantic Search unavailable, but File Access is open.",
                    'artifact_count': 0
                }

            # CRS is ready - return minimal context
            # Tools will handle actual data retrieval
            return {
                'crs_ready': True,
                'artifact_count': summary.get('artifacts', 0)
            }

        except Exception as e:
            logger.warning(f"CRS context error: {e}")
            # Even on error, allow file access if repo exists
            return {
                'crs_ready': False,
                'status_message': f"CRS unavailable: {str(e)}. File Access only.",
                'artifact_count': 0
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

        # Get tool definitions from agent profile (not hardcoded)
        tool_definitions = ""
        
        # Check if conversation is linked to an agent profile
        agent_profile = None
        if conversation.metadata and conversation.metadata.get('agent_profile_id'):
            from agent.models import AgentProfile
            try:
                agent_profile = await sync_to_async(AgentProfile.objects.prefetch_related('tools').get)(
                    id=conversation.metadata['agent_profile_id']
                )
            except AgentProfile.DoesNotExist:
                pass
        
        # Load tools from agent profile if available
        if agent_profile:
            configured_tools = await sync_to_async(list)(agent_profile.tools.all())
            if configured_tools:
                # Build tool definitions from agent's configured tools
                tool_list = []
                for tool in configured_tools:
                    tool_list.append(f"**{tool.name}**: {tool.description}")
                tool_definitions = "\n".join(tool_list)
            # else: agent has no tools configured, tool_definitions stays empty
        elif self.repository:
            # Fallback for repository-based chats without agent profiles
            crs_tools = CRSTools(repository=self.repository)
            tool_definitions = crs_tools.get_tool_definitions()
        # else: No agent, no repository = no tools

        # Get CRS status summary for context
        crs_status_context = ""
        if self.repository:
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

        # Fetch uploaded context files
        context_files = await sync_to_async(list)(
            ContextFile.objects.filter(conversation=conversation)
        )
        
        uploaded_context_prompt = ""
        if context_files:
            uploaded_context_prompt = "\n\n# User Uploaded Context Files:\n"
            for cf in context_files:
                try:
                    # Read file content
                    path = await sync_to_async(lambda: cf.file.path)()
                    
                    # Async file read
                    def read_file():
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            return f.read()

                    content = await sync_to_async(read_file)()
                    
                    uploaded_context_prompt += f"\n## File: {cf.name}\n```\n{content[:20000]} # Truncated if too long\n```\n"
                except Exception as e:
                    logger.error(f"Failed to read context file {cf.id}: {e}")

        # Build tool-first system prompt with router
        
        # Check if conversation is linked to an Agent Profile
        agent_profile = None
        if conversation.metadata and conversation.metadata.get('agent_profile_id'):
            from agent.models import AgentProfile
            try:
                agent_profile = await sync_to_async(AgentProfile.objects.get)(id=conversation.metadata['agent_profile_id'])
                logger.info(f"Using Agent Profile: {agent_profile.name}")
                
                # Fetch Agent Knowledge Files
                agent_files = await sync_to_async(list)(
                    ContextFile.objects.filter(agent_profile=agent_profile)
                )
                if agent_files:
                    uploaded_context_prompt += f"\n\n# Agent Knowledge Base ({agent_profile.name}):\n"
                    for af in agent_files:
                        try:
                            # Prefer analysis if available, otherwise content
                            content_to_use = af.analysis if af.analysis else "No analysis available."
                            # If content is small, maybe include raw? For now, trust analysis.
                            # Or read file if analysis is empty?
                            
                            uploaded_context_prompt += f"\n## Knowledge: {af.name}\nAnalysis/Summary:\n{content_to_use}\n"
                            
                            # Optional: Read raw content if critical
                        except Exception as e:
                            logger.error(f"Failed to read agent file {af.id}: {e}")

            except Exception as e:
                logger.error(f"Failed to load Agent Profile: {e}")

        # Build system prompt based on agent configuration
        if agent_profile:
            # Use agent's custom system prompt
            system_prompt_base = agent_profile.system_prompt_template
            
            # Inject knowledge context if agent has files
            if uploaded_context_prompt:
                knowledge_section = f"\n\n# KNOWLEDGE CONTEXT\n{uploaded_context_prompt}"
            else:
                knowledge_section = ""
            
            # Build tools list if agent has configured tools
            try:
                configured_tools = list(agent_profile.tools.all())
                if configured_tools:
                    tools_description = "\n".join([
                        f"- {tool.name}: {tool.description}" 
                        for tool in configured_tools
                    ])
                    system_prompt_base = system_prompt_base.replace('{{tools}}', f"Available Tools:\n{tools_description}")
                    print(system_prompt_base)
                else:
                    system_prompt_base = system_prompt_base.replace('{{tools}}', 'No tools configured.')
            except:
                system_prompt_base = system_prompt_base.replace('{{tools}}', 'No tools available.')
                
            base_system_prompt = f"{system_prompt_base}{knowledge_section}"
                
        else:
            # No agent profile: Generic assistant
            base_system_prompt = f"""You are a helpful AI assistant.

{uploaded_context_prompt if uploaded_context_prompt else ''}

Answer the user's questions to the best of your ability."""

        # Only include tool definitions if tools exist
        if tool_definitions and tool_definitions.strip():
            system_prompt = f"""{base_system_prompt}

---

{tool_definitions}

---

Use the available tools to help answer the user's question."""
        else:
            system_prompt = base_system_prompt

        # REMOVED: Hardcoded CRS override that ignored agent configuration
        # if status_message:
        #     system_prompt = f"""You are analyzing a code repository...
        
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


# =============================================================================
# KNOWLEDGE EXTRACTION CONSUMER
# =============================================================================

class KnowledgeConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time knowledge extraction events
    
    Streams events during repository knowledge analysis:
    - Extraction started
    - Progress updates (profile, domain model, patterns, etc.)
    - Extraction complete
    - Errors
    """
    
    async def connect(self):
        """Accept WebSocket connection"""
        self.repository_id = self.scope['url_route']['kwargs']['repository_id']
        self.room_group_name = f'knowledge_{self.repository_id}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Knowledge WebSocket connected for repository {self.repository_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"Knowledge WebSocket disconnected: {close_code}")
    
    async def receive(self, text_data):
        """
        Receive message from WebSocket
        
        Expected commands:
        - {"type": "start_extraction", "force": false}
        - {"type": "ping"}
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'start_extraction':
                await self.start_extraction(data.get('force', False))
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
    
    async def start_extraction(self, force=False):
        """Start knowledge extraction"""
        try:
            from agent.services.knowledge_agent import RepositoryKnowledgeAgent
            from django.utils import timezone
            
            # Get repository
            repository = await self.get_repository()
            
            # Check CRS status
            from agent.services.crs_runner import get_crs_summary
            crs_summary = await sync_to_async(get_crs_summary)(repository)
            
            if crs_summary.get('status') != 'ready':
                await self.send_json({
                    'type': 'error',
                    'error': 'CRS must be ready before knowledge extraction'
                })
                return
            
            # Skip status check - fields don't exist
            
            # Create agent with socket callback
            def socket_callback(event):
                """Callback to send events through WebSocket"""
                import asyncio
                asyncio.create_task(self.send_json(event))
            
            knowledge_agent = RepositoryKnowledgeAgent(
                repository=repository,
                socket_callback=socket_callback
            )
            
            # Run extraction
            result = await sync_to_async(knowledge_agent.analyze_repository)()
            
            # No need to update repository fields since they don't exist
        
        except Exception as e:
            logger.error(f"Knowledge extraction failed: {e}", exc_info=True)
            await self.send_json({
                'type': 'knowledge_extraction_error',
                'error': str(e)
            })
    
    async def send_json(self, data):
        """Send JSON message to WebSocket"""
        await self.send(text_data=json.dumps(data))
    
    @database_sync_to_async
    def get_repository(self):
        """Get repository from database"""
        return Repository.objects.get(id=self.repository_id)
    
    # Event handlers for group messages
    async def knowledge_event(self, event):
        """Handle knowledge extraction events from group"""
        await self.send_json(event)


# =============================================================================
# AGENT RUNNER CONSUMER
# =============================================================================

class AgentRunnerConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time agent execution events
    
    Streams events during autonomous agent execution:
    - Session creation
    - Planning
    - Step execution
    - Patch operations
    - Verification
    - Rollback
    - Session completion
    """
    
    async def connect(self):
        """Accept WebSocket connection"""
        self.repository_id = self.scope['url_route']['kwargs']['repository_id']
        self.room_group_name = f'agent_{self.repository_id}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Agent Runner WebSocket connected for repository {self.repository_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"Agent Runner WebSocket disconnected: {close_code}")
    
    async def receive(self, text_data):
        """
        Receive message from WebSocket
        
        Expected commands:
        - {"type": "execute", "request": "Add payment method"}
        - {"type": "ping"}
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'execute':
                await self.execute_agent(data.get('request', ''))
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
    
    async def execute_agent(self, request):
        """Execute agent runner"""
        if not request:
            await self.send_json({
                'type': 'error',
                'error': 'Request cannot be empty'
            })
            return
        
        try:
            from agent.services.agent_runner import AgentRunner
            import uuid
            
            # Get repository
            repository = await self.get_repository()
            
            # Generate session ID
            session_id = f"session_{uuid.uuid4().hex[:12]}"
            
            # Create agent runner with socket callback
            # Create agent runner with socket callback
            from asgiref.sync import async_to_sync
            
            def socket_callback(event):
                """Callback to send events through WebSocket"""
                # Since AgentRunner runs in a sync thread (via sync_to_async),
                # we need to bridge back to the async consumer to send the message.
                async_to_sync(self.send_json)(event)
            
            agent_runner = AgentRunner(
                repository=repository,
                socket_callback=socket_callback
            )
            
            # Execute
            result = await sync_to_async(agent_runner.execute)(
                session_id=session_id,
                request=request
            )
            
            # Final result already sent via socket_callback events
            # Just log completion
            logger.info(f"Agent execution completed: {session_id} - {result.get('status')}")
        
        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            await self.send_json({
                'type': 'agent_session_error',
                'error': str(e)
            })
    
    async def send_json(self, data):
        """Send JSON message to WebSocket"""
        await self.send(text_data=json.dumps(data))
    
    @database_sync_to_async
    def get_repository(self):
        """Get repository from database"""
        return Repository.objects.get(id=self.repository_id)
    
    # Event handlers for group messages
    async def agent_event(self, event):
        """Handle agent execution events from group"""
        await self.send_json(event)
