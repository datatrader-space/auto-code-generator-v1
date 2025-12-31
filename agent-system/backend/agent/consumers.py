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
        Stream LLM response in chunks with CRS tool support

        Args:
            user_message: User's message text
            context: CRS context or other relevant context
            conversation: ChatConversation instance
        """
        # Import CRS tools
        from agent.crs_tools import CRSTools

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
        max_tool_iterations = 3  # Prevent infinite loops

        try:
            client = router.local_client if provider == 'local' else router.cloud_client

            # Tool-calling loop
            for iteration in range(max_tool_iterations):
                # Get LLM response
                chunks = await sync_to_async(lambda: list(client.query_stream(messages)))()

                iteration_response = ""
                for text_chunk in chunks:
                    iteration_response += text_chunk

                    # Send chunk to frontend
                    await self.send_json({
                        'type': 'assistant_message_chunk',
                        'chunk': text_chunk
                    })

                full_response = iteration_response

                # Check for tool calls
                crs_tools = CRSTools(repository=getattr(self, 'repository', None))
                tool_calls = crs_tools.parse_tool_calls(iteration_response)

                if not tool_calls:
                    # No tools requested, we're done
                    break

                # Execute tools and gather results
                logger.info(f"LLM requested {len(tool_calls)} tool(s)")
                tool_results = []

                for tool_call in tool_calls:
                    tool_name = tool_call['name']
                    tool_params = tool_call['parameters']

                    logger.info(f"Executing tool: {tool_name} with params: {tool_params}")
                    result = await sync_to_async(crs_tools.execute_tool)(tool_name, tool_params)
                    tool_results.append(f"\n**Tool Result ({tool_name}):**\n{result}\n")

                # Send tool results to user
                tool_results_text = '\n'.join(tool_results)
                await self.send_json({
                    'type': 'assistant_message_chunk',
                    'chunk': tool_results_text
                })

                full_response += tool_results_text

                # Add tool results to messages and continue
                messages.append({
                    'role': 'assistant',
                    'content': iteration_response
                })
                messages.append({
                    'role': 'system',
                    'content': f"Tool Results:\n{tool_results_text}\n\nNow answer the user's original question using this data."
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

        # Save user message
        await self.save_user_message(conversation, user_message)

        # Get CRS context
        context = await self.get_crs_context(user_message)

        # Stream LLM response
        await self.stream_llm_response(user_message, context, conversation)

    @database_sync_to_async
    def get_crs_context(self, query):
        """Get relevant CRS context for the query using RAG"""
        crs_context = CRSContext(self.repository)
        crs_context.load_all()

        if not crs_context.has_payloads():
            message = "CRS not ready for this repo."
            logger.warning("CRS payloads missing for repository %s", self.repository.name)
            return {
                'status_message': message,
                'search_results': message
            }

        context_prompt = crs_context.search_context(query, limit=10)

        return {
            'search_results': context_prompt
        }

    async def build_llm_messages(self, conversation, user_message, context):
        """
        Build messages with tool-first approach

        Forces LLM to plan tool usage before answering
        """
        from agent.crs_tools import CRSTools

        # Get conversation history
        history = await self.get_conversation_history(conversation)

        status_message = context.get('status_message')

        # Get tool definitions
        crs_tools = CRSTools(repository=self.repository)
        tool_definitions = crs_tools.get_tool_definitions()

        # Build tool-first system prompt with router
        system_prompt = f"""You are a code repository assistant with access to CRS (Contextual Retrieval System) tools.

# YOUR JOB

1. **PLAN** which tools to use
2. **REQUEST** tools using the exact format shown below
3. **WAIT** for tool results
4. **ANSWER** the user's question with the data

---

{tool_definitions}

---

# CRITICAL RULES

## For Inventory Questions ("list all X", "what models exist", "show serializers")
→ You MUST use LIST_ARTIFACTS
→ NEVER try to answer from memory or search results
→ Example questions: "what models exist?", "list all viewsets", "show me serializers"
→ Correct: `[LIST_ARTIFACTS: kind="django_model"]`
→ Wrong: Answering without using LIST_ARTIFACTS

## For Location Questions ("where is X", "find X", "how does X work")
→ Use SEARCH_CRS first
→ Then use GET_ARTIFACT or READ_FILE for details
→ Example: `[SEARCH_CRS: query="authentication", limit="10"]`

## For Flow Analysis ("what calls X", "how are X and Y connected")
→ Use CRS_RELATIONSHIPS
→ Example: `[CRS_RELATIONSHIPS: artifact_id="..."]`

---

# RESPONSE FORMAT

When you need to use tools, respond like this:

```
Let me search for that information.

[TOOL_NAME: param="value"]
```

After receiving tool results, provide your answer with citations:
- Always reference file:line locations
- Quote artifact_ids for traceability
- Be specific and concrete

---

# EXAMPLES

**User:** "What models exist in this repository?"

**You (CORRECT):**
```
Let me list all Django models in the repository.

[LIST_ARTIFACTS: kind="django_model"]
```

**You (WRONG):**
```
Based on my knowledge, there are models like User, System... [WRONG - this is guessing]
```

---

**User:** "Where is the WebSocket consumer defined?"

**You (CORRECT):**
```
Let me search for WebSocket consumers.

[SEARCH_CRS: query="websocket consumer", limit="10"]
```

---

**User:** "What does RepositoryViewSet do?"

**You (CORRECT):**
```
Let me search for that class first.

[SEARCH_CRS: query="RepositoryViewSet", limit="5"]
```
Then after getting artifact_id:
```
[GET_ARTIFACT: artifact_id="drf_viewset:RepositoryViewSet:agent/views.py:45-120"]
```

---

Now answer the user's question by requesting the appropriate tools."""

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
