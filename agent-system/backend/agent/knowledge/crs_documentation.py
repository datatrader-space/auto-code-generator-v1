# agent/knowledge/crs_documentation.py
"""
CRS (Contextual Retrieval System) Documentation
Knowledge base for teaching LLMs about CRS format
"""

CRS_DOCUMENTATION = {
    "overview": """
# CRS (Contextual Retrieval System) Overview

CRS is a structured knowledge representation format for codebases that provides three layers of understanding:

1. **BLUEPRINTS**: High-level architectural understanding of code modules/files
2. **ARTIFACTS**: Detailed implementation information (functions, classes, API endpoints, models)
3. **RELATIONSHIPS**: Explicit connections between different parts of the system

This structured approach allows AI assistants to understand codebases deeply and answer questions accurately.
""",

    "blueprints": """
## BLUEPRINTS

Blueprints represent modules/files in the codebase. Each blueprint contains:

**Structure**:
- `path`: File location (e.g., "src/components/Header.vue", "backend/api/views.py")
- `purpose`: High-level description of what this module does
- `key_components`: List of main classes, functions, or exports
- `dependencies`: What this module imports or depends on
- `used_by`: Which other modules use this module
- `patterns`: Design patterns or architectural patterns used

**Example Blueprint**:
```json
{
  "path": "backend/agent/views.py",
  "purpose": "REST API views for agent system",
  "key_components": ["SystemViewSet", "RepositoryViewSet", "ChatConversationViewSet"],
  "dependencies": ["Django REST Framework", "agent.models", "agent.serializers"],
  "used_by": ["agent/urls.py"],
  "patterns": ["ViewSet pattern", "REST API"]
}
```

**When to reference blueprints**:
- Understanding overall architecture
- Finding which files are responsible for specific functionality
- Tracing dependencies between modules
""",

    "artifacts": """
## ARTIFACTS

Artifacts are detailed code elements extracted from the codebase. Types include:

### Function Artifacts
- `name`: Function name
- `parameters`: List of parameters with types
- `return_type`: What the function returns
- `purpose`: What the function does
- `location`: File path and line number

### Class Artifacts
- `name`: Class name
- `methods`: List of methods with signatures
- `properties`: Class properties/attributes
- `inheritance`: Parent classes
- `purpose`: What the class represents

### API Endpoint Artifacts
- `route`: URL pattern (e.g., "/api/systems/{id}/")
- `method`: HTTP method (GET, POST, PUT, DELETE)
- `parameters`: Query params, path params, request body
- `response`: Response structure
- `authentication`: Auth requirements

### Database Model Artifacts
- `name`: Model name
- `fields`: Field names and types
- `relationships`: Foreign keys, many-to-many
- `indexes`: Database indexes
- `purpose`: What data this model stores

**Example Artifact (Function)**:
```json
{
  "type": "function",
  "name": "create_conversation",
  "parameters": [
    {"name": "user", "type": "User"},
    {"name": "repository", "type": "Repository"},
    {"name": "conversation_type", "type": "str"}
  ],
  "return_type": "ChatConversation",
  "purpose": "Creates a new chat conversation for a repository"
}
```

**When to reference artifacts**:
- Understanding specific implementation details
- Finding exact function signatures
- Understanding API endpoints
- Database schema questions
""",

    "relationships": """
## RELATIONSHIPS

Relationships explicitly connect artifacts and show how the system works together.

### Relationship Types:

1. **IMPORTS**
   - Module A imports from Module B
   - Example: "views.py IMPORTS serializers.py"

2. **CALLS**
   - Function A calls Function B
   - Example: "handle_message() CALLS stream_llm_response()"

3. **EXTENDS**
   - Class A extends/inherits from Class B
   - Example: "RepositoryViewSet EXTENDS ModelViewSet"

4. **REFERENCES**
   - Component A references/uses Component B
   - Example: "ChatConversation REFERENCES Repository (foreign key)"

5. **IMPLEMENTS**
   - Class A implements Interface B
   - Example: "Consumer IMPLEMENTS WebSocketConsumer"

6. **USES_API**
   - Component A calls API endpoint B
   - Example: "RepositoryChat.vue USES_API /api/conversations/"

**Relationship Structure**:
```json
{
  "source": "RepositoryChatConsumer",
  "target": "ChatConversation",
  "type": "CREATES",
  "context": "Creates conversation when user sends first message"
}
```

**When to reference relationships**:
- Tracing data flow through the system
- Understanding how components interact
- Finding the impact of changes
- Debugging issues across modules
""",

    "usage_guidelines": """
## How to Use CRS Information

When answering questions:

1. **Start with Context**: Reference which blueprints and artifacts are relevant
2. **Be Specific**: Cite exact function names, file paths, line numbers
3. **Show Relationships**: Explain how components connect
4. **Provide Examples**: Use actual code from artifacts when helpful
5. **Organize Answers**: Use the blueprint → artifact → relationship hierarchy

**Example Answer Structure**:

Q: "How does the chat system work?"

A: "The chat system uses WebSocket connections for real-time communication:

**Architecture (Blueprints)**:
- Frontend: `src/components/RepositoryChat.vue` - Vue component for chat UI
- Backend: `agent/consumers.py` - WebSocket consumer handling messages

**Key Components (Artifacts)**:
- `RepositoryChatConsumer.receive()` - Handles incoming WebSocket messages
- `RepositoryChatConsumer.stream_llm_response()` - Streams AI responses
- `ChatConversation` model - Stores conversation history
- `ChatMessage` model - Stores individual messages

**Flow (Relationships)**:
1. RepositoryChat.vue CONNECTS_TO ws://localhost:8000/ws/chat/repository/{id}/
2. RepositoryChatConsumer.receive() CALLS stream_llm_response()
3. stream_llm_response() QUERIES local LLM
4. Response chunks SENT_TO frontend via WebSocket
5. ChatMessage CREATED with role='assistant' and saved to database"

This structure helps users understand both the 'what' and the 'how' of the system.
"""
}

# System prompts for different chat types

REPOSITORY_CHAT_SYSTEM_PROMPT = """You are an AI assistant analyzing a specific code repository using CRS (Contextual Retrieval System).

{crs_overview}

**Your Capabilities**:
- You have access to blueprints (high-level architecture)
- You have access to artifacts (detailed code elements)
- You have access to relationships (how components connect)
- You can reference specific files, functions, and code structures

**Your Task**:
Answer questions about this repository by:
1. Referencing relevant blueprints to explain architecture
2. Citing specific artifacts for implementation details
3. Tracing relationships to show how components interact
4. Providing concrete examples from the actual codebase

**Important**:
- Always cite file paths when referencing code
- Use actual function/class names from the artifacts
- Explain relationships between components
- Be precise and specific in your answers

The context provided below contains relevant blueprints, artifacts, and relationships for the current question.
"""

PLANNER_CHAT_SYSTEM_PROMPT = """You are an AI system architect analyzing multiple repositories using CRS (Contextual Retrieval System).

{crs_overview}

**Your Capabilities**:
- You can see the architecture across multiple repositories
- You understand how different repos interact
- You can plan changes that span multiple codebases
- You can assess the impact of architectural decisions

**Your Task**:
Help plan system-wide changes by:
1. Understanding the current multi-repo architecture
2. Identifying all affected components across repos
3. Planning changes in the correct order
4. Considering dependencies and relationships
5. Assessing impact and risks

**Important**:
- Consider cross-repository dependencies
- Think about deployment order
- Identify breaking changes
- Plan migration strategies when needed

The context provided below contains relevant information from across the system.
"""

GRAPH_CHAT_SYSTEM_PROMPT = """You are an AI assistant helping explore code relationships using CRS (Contextual Retrieval System).

{crs_overview}

**Your Capabilities**:
- You can trace relationships between any components
- You can find paths between artifacts
- You can identify dependency chains
- You can discover related components

**Your Task**:
Help explore the codebase graph by:
1. Tracing how data flows through the system
2. Finding all components related to a feature
3. Identifying circular dependencies
4. Discovering hidden connections

**Important**:
- Show the complete relationship chain
- Identify both direct and indirect relationships
- Highlight potential issues (circular deps, tight coupling)
- Suggest improvements when relevant

The context provided below contains the relationship graph for exploration.
"""


def get_system_prompt(conversation_type='repository'):
    """Get the appropriate system prompt based on conversation type"""

    crs_overview = CRS_DOCUMENTATION['overview']

    prompts = {
        'repository': REPOSITORY_CHAT_SYSTEM_PROMPT,
        'planner': PLANNER_CHAT_SYSTEM_PROMPT,
        'graph': GRAPH_CHAT_SYSTEM_PROMPT
    }

    prompt_template = prompts.get(conversation_type, REPOSITORY_CHAT_SYSTEM_PROMPT)
    return prompt_template.format(crs_overview=crs_overview)


def get_crs_documentation_context():
    """Get formatted CRS documentation for context injection"""

    return f"""
# CRS Format Reference

{CRS_DOCUMENTATION['overview']}

{CRS_DOCUMENTATION['blueprints']}

{CRS_DOCUMENTATION['artifacts']}

{CRS_DOCUMENTATION['relationships']}

{CRS_DOCUMENTATION['usage_guidelines']}
"""
