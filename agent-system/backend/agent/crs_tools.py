# agent/crs_tools.py
"""
CRS Tools - Functions the LLM can call to explore CRS data
Implements a tool-calling interface for local LLMs
"""

import json
import re
from typing import Dict, List, Any, Optional
from agent.rag import CRSRetriever
import logging

logger = logging.getLogger(__name__)


class CRSTools:
    """
    Provides queryable tools for LLM to explore CRS data

    Tools available:
    - search_blueprints: Find files/modules by keyword
    - search_artifacts: Find classes/functions by keyword
    - get_artifact_details: Get full details of specific artifact
    - list_all_files: Get complete file list
    - search_relationships: Find how components connect
    """

    def __init__(self, repository):
        self.repository = repository
        self.retriever = CRSRetriever(repository=repository)

    def get_tool_definitions(self) -> str:
        """Get description of available tools for system prompt"""
        return """
# Available CRS Query Tools

You can query the CRS database using these tools:

**[SEARCH_BLUEPRINTS: query="keyword"]**
- Searches for files/modules matching keyword
- Returns: file paths, purposes, key components

**[SEARCH_ARTIFACTS: query="keyword", type="class|function|endpoint"]**
- Searches for code elements
- Returns: names, types, files, signatures

**[GET_ARTIFACT: name="ArtifactName"]**
- Gets full details of specific artifact
- Returns: complete information including methods, source code

**[LIST_FILES]**
- Lists all files in repository
- Returns: complete file structure

**[SEARCH_RELATIONSHIPS: artifact="ArtifactName"]**
- Finds relationships for an artifact
- Returns: what it calls, imports, uses

# How to Use Tools

**Step 1**: Decide what information you need
**Step 2**: Use appropriate tool(s)
**Step 3**: Wait for results
**Step 4**: Answer user's question with the data

# Example Tool Usage

User: "What models exist?"

You: Let me search for Django models.
[SEARCH_ARTIFACTS: query="model", type="class"]

System: <returns list of model classes>

You: Based on the artifacts, I found these Django models:
1. User (class) in agent/models.py
2. System (class) in agent/models.py
...
"""

    def parse_tool_calls(self, llm_response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response

        Format: [TOOL_NAME: param="value", param2="value"]
        """
        tool_pattern = r'\[(SEARCH_BLUEPRINTS|SEARCH_ARTIFACTS|GET_ARTIFACT|LIST_FILES|SEARCH_RELATIONSHIPS):\s*([^\]]+)\]'
        matches = re.findall(tool_pattern, llm_response, re.IGNORECASE)

        tools = []
        for tool_name, params_str in matches:
            tool_name = tool_name.upper()

            # Parse parameters
            params = {}
            param_pattern = r'(\w+)="([^"]*)"'
            param_matches = re.findall(param_pattern, params_str)
            for param_name, param_value in param_matches:
                params[param_name] = param_value

            tools.append({
                'name': tool_name,
                'parameters': params
            })

        logger.info(f"Parsed {len(tools)} tool calls from LLM response")
        return tools

    def execute_tool(self, tool_name: str, parameters: Dict[str, str]) -> str:
        """Execute a tool and return formatted results"""

        tool_name = tool_name.upper()

        try:
            if tool_name == 'SEARCH_BLUEPRINTS':
                return self._search_blueprints(parameters.get('query', ''))

            elif tool_name == 'SEARCH_ARTIFACTS':
                return self._search_artifacts(
                    parameters.get('query', ''),
                    parameters.get('type')
                )

            elif tool_name == 'GET_ARTIFACT':
                return self._get_artifact(parameters.get('name', ''))

            elif tool_name == 'LIST_FILES':
                return self._list_files()

            elif tool_name == 'SEARCH_RELATIONSHIPS':
                return self._search_relationships(parameters.get('artifact', ''))

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return f"Error executing {tool_name}: {str(e)}"

    def _search_blueprints(self, query: str) -> str:
        """Search for files/modules"""
        blueprints = self.retriever.search_blueprints(query, limit=10)

        if not blueprints:
            return f"No blueprints found matching '{query}'"

        result = [f"Found {len(blueprints)} blueprints:\n"]
        for bp in blueprints:
            path = bp.get('path', 'unknown')
            purpose = bp.get('purpose', 'No purpose specified')
            components = bp.get('key_components', [])

            result.append(f"**{path}**")
            result.append(f"  Purpose: {purpose}")
            if components:
                result.append(f"  Components: {', '.join(str(c) for c in components[:5])}")
            result.append("")

        return '\n'.join(result)

    def _search_artifacts(self, query: str, artifact_type: Optional[str] = None) -> str:
        """Search for code elements"""
        artifacts = self.retriever.search_artifacts(query, limit=15)

        if not artifacts:
            return f"No artifacts found matching '{query}'"

        # Filter by type if specified
        if artifact_type:
            artifacts = [a for a in artifacts if a.get('type', '').lower() == artifact_type.lower()]

        if not artifacts:
            return f"No {artifact_type} artifacts found matching '{query}'"

        result = [f"Found {len(artifacts)} artifacts:\n"]
        for artifact in artifacts:
            name = artifact.get('name', 'unknown')
            atype = artifact.get('type', 'unknown')
            file = artifact.get('file', 'unknown')

            result.append(f"**{name}** ({atype})")
            result.append(f"  File: {file}")

            # Add type-specific info
            if atype == 'class':
                methods = artifact.get('methods', [])
                if methods:
                    method_names = [m.get('name', m) if isinstance(m, dict) else m for m in methods[:5]]
                    result.append(f"  Methods: {', '.join(str(m) for m in method_names)}")
            elif atype == 'function':
                params = artifact.get('parameters', [])
                if params:
                    result.append(f"  Parameters: {len(params)} params")

            result.append("")

        return '\n'.join(result)

    def _get_artifact(self, name: str) -> str:
        """Get full details of specific artifact"""
        self.retriever._load_crs_data()
        artifacts = self.retriever._artifacts.get('artifacts', [])

        # Find exact match
        artifact = None
        for a in artifacts:
            if a.get('name') == name:
                artifact = a
                break

        if not artifact:
            return f"Artifact '{name}' not found"

        # Format complete details
        result = [f"Artifact: **{name}**\n"]

        for key, value in artifact.items():
            if key == 'source' and value:
                result.append(f"Source Code:\n```python\n{value}\n```\n")
            elif key in ['methods', 'parameters'] and value:
                result.append(f"{key.title()}: {json.dumps(value, indent=2)}\n")
            else:
                result.append(f"{key.title()}: {value}")

        return '\n'.join(result)

    def _list_files(self) -> str:
        """List all files in repository"""
        self.retriever._load_crs_data()
        files = self.retriever._blueprints.get('files', [])

        if not files:
            return "No files found in blueprints"

        result = [f"Repository has {len(files)} files:\n"]

        # Group by directory
        by_dir = {}
        for f in files:
            path = f.get('path', '')
            if '/' in path:
                dir_name = path.rsplit('/', 1)[0]
            else:
                dir_name = '.'

            if dir_name not in by_dir:
                by_dir[dir_name] = []
            by_dir[dir_name].append(path)

        # Format output
        for dir_name in sorted(by_dir.keys()):
            result.append(f"{dir_name}/")
            for file_path in sorted(by_dir[dir_name]):
                file_name = file_path.split('/')[-1]
                result.append(f"  - {file_name}")
            result.append("")

        return '\n'.join(result)

    def _search_relationships(self, artifact_name: str) -> str:
        """Find relationships for an artifact"""
        self.retriever._load_crs_data()
        relationships = self.retriever._relationships.get('relationships', [])

        # Find relationships involving this artifact
        related = []
        for rel in relationships:
            if rel.get('source') == artifact_name or rel.get('target') == artifact_name:
                related.append(rel)

        if not related:
            return f"No relationships found for '{artifact_name}'"

        result = [f"Relationships for {artifact_name}:\n"]

        # Group by type
        by_type = {}
        for rel in related:
            rel_type = rel.get('type', 'unknown')
            if rel_type not in by_type:
                by_type[rel_type] = []
            by_type[rel_type].append(rel)

        for rel_type, rels in by_type.items():
            result.append(f"**{rel_type}:**")
            for rel in rels[:10]:  # Limit to 10 per type
                source = rel.get('source', '?')
                target = rel.get('target', '?')
                result.append(f"  {source} → {target}")
            result.append("")

        return '\n'.join(result)
