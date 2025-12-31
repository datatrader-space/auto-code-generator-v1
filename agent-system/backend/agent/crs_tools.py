# agent/crs_tools.py
"""
CRS Tools - Tool-first agent system for querying code repositories
Based on structured tool calls with citeable, grounded outputs
"""

import json
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
from agent.rag import CRSRetriever
from agent.services.crs_runner import get_crs_summary, load_crs_payload
import logging

logger = logging.getLogger(__name__)


class CRSTools:
    """
    Provides 6 core tools for LLM to explore CRS data deterministically

    Core Philosophy:
    - Inventory questions MUST use list_artifacts (not search)
    - Search is for "where is X" / "what does X do"
    - All outputs are structured and citeable (file_path:line_number)
    """

    def __init__(self, repository):
        self.repository = repository
        self.retriever = CRSRetriever(repository=repository)

    def get_tool_definitions(self) -> str:
        """Return tool descriptions for system prompt"""
        return """
# Available CRS Query Tools

You have access to 6 deterministic tools for exploring the codebase.

## Tool Call Format (STRICT)

You MUST output tool calls in this EXACT format:

```
===TOOL_CALLS===
[{"name":"TOOL_NAME","parameters":{"param":"value"}}]
===END_TOOL_CALLS===
```

**Rules:**
- Use the delimiters `===TOOL_CALLS===` and `===END_TOOL_CALLS===`
- Output valid JSON array of tool call objects
- Each object has `name` (required) and `parameters` (optional dict)
- Tool names are case-insensitive
- You can call multiple tools in one block

**Example - Single Tool:**
```
===TOOL_CALLS===
[{"name":"LIST_ARTIFACTS","parameters":{"kind":"django_model"}}]
===END_TOOL_CALLS===
```

**Example - Multiple Tools:**
```
===TOOL_CALLS===
[
  {"name":"CRS_STATUS","parameters":{}},
  {"name":"LIST_ARTIFACTS","parameters":{"kind":"django_model"}}
]
===END_TOOL_CALLS===
```

---

## Available Tools

### 1. CRS_STATUS
- **Purpose**: Check repository and CRS analysis status
- **Parameters**: None
- **Returns**: Status, artifact counts, last run time
- **Use when**: Uncertain if CRS data is ready

### 2. LIST_ARTIFACTS
- **Purpose**: Get complete inventory of code elements (DETERMINISTIC)
- **Parameters**:
  - `kind` (required): django_model | drf_serializer | drf_viewset | drf_apiview | url_pattern | admin_register
  - `filter` (optional): Text filter for names/paths
- **Returns**: All artifacts of that type with file:line locations
- **CRITICAL**: This is the ONLY correct way to answer "list all X" questions

### 3. GET_ARTIFACT
- **Purpose**: Get full details of a specific artifact
- **Parameters**:
  - `artifact_id` (required): Full artifact ID from LIST_ARTIFACTS or SEARCH_CRS
- **Returns**: Complete artifact details, metadata, evidence

### 4. SEARCH_CRS
- **Purpose**: Keyword search for code elements
- **Parameters**:
  - `query` (required): Keywords to search
  - `limit` (optional): Max results (default 10)
- **Returns**: Matching artifacts/blueprints with file:line anchors
- **NOT for inventory** - use LIST_ARTIFACTS for "list all X"

### 5. CRS_RELATIONSHIPS
- **Purpose**: Find how an artifact connects to other code
- **Parameters**:
  - `artifact_id` (required): Artifact to analyze
- **Returns**: Imports, calls, usage graph (incoming/outgoing)

### 6. READ_FILE
- **Purpose**: Get raw source code
- **Parameters**:
  - `path` (required): File path relative to repo root
  - `start_line` (optional): First line to read (default 1)
  - `end_line` (optional): Last line to read (default 100)
- **Returns**: File contents with line numbers

---

## Tool Selection Rules

**For "list/show all/what X exist" questions:**
→ MUST use LIST_ARTIFACTS (never guess, never use search)

**For "where is X" / "find X":**
→ Use SEARCH_CRS, then GET_ARTIFACT or READ_FILE for details

**For "what calls X" / "flow analysis":**
→ Use CRS_RELATIONSHIPS

**Always check CRS_STATUS first if data availability is uncertain**
"""

    def parse_tool_calls(self, llm_response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response using strict JSON protocol

        Expected format:
        ===TOOL_CALLS===
        [{"name":"LIST_ARTIFACTS","parameters":{"kind":"django_model"}}]
        ===END_TOOL_CALLS===
        """
        # Look for delimited JSON block
        pattern = r'===TOOL_CALLS===\s*(\[.*?\])\s*===END_TOOL_CALLS==='
        match = re.search(pattern, llm_response, re.DOTALL)

        if not match:
            logger.debug("No tool calls found in response (no ===TOOL_CALLS=== block)")
            return []

        json_str = match.group(1).strip()

        try:
            tools = json.loads(json_str)

            if not isinstance(tools, list):
                logger.error(f"Tool calls must be a JSON array, got: {type(tools)}")
                return []

            # Validate structure
            validated = []
            for tool in tools:
                if not isinstance(tool, dict):
                    logger.warning(f"Skipping non-dict tool call: {tool}")
                    continue

                if 'name' not in tool:
                    logger.warning(f"Skipping tool call without 'name': {tool}")
                    continue

                validated.append({
                    'name': tool['name'].upper(),
                    'parameters': tool.get('parameters', {})
                })

            logger.info(f"Parsed {len(validated)} valid tool calls: {[t['name'] for t in validated]}")
            return validated

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tool calls JSON: {e}\nJSON string: {json_str}")
            return []

    def execute_tool(self, tool_name: str, parameters: Dict[str, str]) -> str:
        """Execute a tool and return structured results"""

        tool_name = tool_name.upper()

        try:
            if tool_name == 'CRS_STATUS':
                return self._crs_status()

            elif tool_name == 'LIST_ARTIFACTS':
                return self._list_artifacts(
                    kind=parameters.get('kind', ''),
                    filter_text=parameters.get('filter', '')
                )

            elif tool_name == 'GET_ARTIFACT':
                return self._get_artifact(parameters.get('artifact_id', ''))

            elif tool_name == 'SEARCH_CRS':
                return self._search_crs(
                    query=parameters.get('query', ''),
                    limit=int(parameters.get('limit', '10'))
                )

            elif tool_name == 'CRS_RELATIONSHIPS':
                return self._crs_relationships(parameters.get('artifact_id', ''))

            elif tool_name == 'READ_FILE':
                return self._read_file(
                    path=parameters.get('path', ''),
                    start_line=int(parameters.get('start_line', '1')),
                    end_line=int(parameters.get('end_line', '100'))
                )

            else:
                return f"❌ Unknown tool: {tool_name}"

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return f"❌ Error executing {tool_name}: {str(e)}"

    # ==================== TOOL IMPLEMENTATIONS ====================

    def _crs_status(self) -> str:
        """Get CRS status and artifact counts"""
        try:
            summary = get_crs_summary(self.repository)

            result = [
                "📊 **CRS Status**\n",
                f"Repository: {self.repository.name}",
                f"Status: {summary.get('status', 'unknown')}",
                f"CRS Status: {summary.get('crs_status', 'unknown')}",
                f"\n**Artifact Counts:**",
                f"  - Blueprint Files: {summary.get('blueprint_files', 0)}",
                f"  - Artifacts: {summary.get('artifacts', 0)}",
                f"  - Relationships: {summary.get('relationships', 0)}",
            ]

            if summary.get('status') != 'ready':
                result.append("\n⚠️  CRS not ready - run analysis first")

            return '\n'.join(result)

        except Exception as e:
            logger.error(f"CRS status error: {e}")
            return f"❌ CRS data not available: {str(e)}\n\nPlease run CRS analysis on this repository first."

    def _list_artifacts(self, kind: str, filter_text: str = '') -> str:
        """
        List all artifacts of a specific kind (deterministic inventory)
        This is the ONLY correct way to answer "list all X" questions
        """
        if not kind:
            return "❌ Missing 'kind' parameter. Valid kinds: django_model, drf_serializer, drf_viewset, drf_apiview, url_pattern, admin_register"

        try:
            self.retriever._load_crs_data()
            all_artifacts = self.retriever._artifacts.get('artifacts', [])

            # Filter by type
            filtered = [a for a in all_artifacts if a.get('type', '').lower() == kind.lower()]

            # Apply optional text filter
            if filter_text:
                filter_lower = filter_text.lower()
                filtered = [
                    a for a in filtered
                    if filter_lower in a.get('name', '').lower()
                    or filter_lower in a.get('file_path', '').lower()
                ]

            if not filtered:
                return f"📋 No {kind} artifacts found" + (f" matching '{filter_text}'" if filter_text else "")

            result = [f"📋 **{kind.upper()} Inventory** ({len(filtered)} items)\n"]

            for artifact in filtered[:50]:  # Limit to 50 for readability
                name = artifact.get('name', 'unknown')
                file_path = artifact.get('file_path', 'unknown')
                anchor = artifact.get('anchor', {})
                start_line = anchor.get('start_line', 0)
                artifact_id = artifact.get('artifact_id', 'unknown')

                # Citation format: file_path:line
                citation = f"{file_path}:{start_line}"

                result.append(f"**{name}**")
                result.append(f"  📍 {citation}")
                result.append(f"  🆔 {artifact_id}")

                # Add type-specific metadata
                meta = artifact.get('meta', {})
                if kind == 'django_model':
                    fields = meta.get('fields', [])
                    if fields:
                        # Handle both dict and string field formats
                        field_names = []
                        for field in fields[:5]:
                            if isinstance(field, dict):
                                field_names.append(field.get('name', str(field)))
                            else:
                                field_names.append(str(field))
                        result.append(f"  📝 Fields: {', '.join(field_names)}")
                        if len(fields) > 5:
                            result.append(f"     ... and {len(fields) - 5} more")

                elif kind in ['drf_serializer']:
                    serializer_fields = meta.get('serializer_fields', [])
                    if serializer_fields:
                        # Handle both dict and string formats
                        field_names = []
                        for field in serializer_fields[:5]:
                            if isinstance(field, dict):
                                field_names.append(field.get('name', str(field)))
                            else:
                                field_names.append(str(field))
                        result.append(f"  📝 Fields: {', '.join(field_names)}")

                elif kind in ['drf_viewset', 'drf_apiview']:
                    methods = meta.get('methods', [])
                    if methods:
                        # Handle both dict and string formats
                        method_names = []
                        for method in methods[:5]:
                            if isinstance(method, dict):
                                method_names.append(method.get('name', str(method)))
                            else:
                                method_names.append(str(method))
                        result.append(f"  🔧 Methods: {', '.join(method_names)}")

                result.append("")

            if len(filtered) > 50:
                result.append(f"... and {len(filtered) - 50} more (showing first 50)")

            return '\n'.join(result)

        except Exception as e:
            logger.error(f"List artifacts error: {e}", exc_info=True)
            return f"❌ Error listing {kind}: {str(e)}"

    def _get_artifact(self, artifact_id: str) -> str:
        """Get full details of a specific artifact"""
        if not artifact_id:
            return "❌ Missing 'artifact_id' parameter"

        try:
            self.retriever._load_crs_data()
            all_artifacts = self.retriever._artifacts.get('artifacts', [])

            # Find exact match
            artifact = None
            for a in all_artifacts:
                if a.get('artifact_id') == artifact_id:
                    artifact = a
                    break

            if not artifact:
                return f"❌ Artifact not found: {artifact_id}"

            # Format complete details with citations
            name = artifact.get('name', 'unknown')
            atype = artifact.get('type', 'unknown')
            file_path = artifact.get('file_path', 'unknown')
            anchor = artifact.get('anchor', {})
            start_line = anchor.get('start_line', 0)
            end_line = anchor.get('end_line', 0)
            confidence = artifact.get('confidence', 'unknown')
            meta = artifact.get('meta', {})

            result = [
                f"🔍 **Artifact Details**\n",
                f"**Name:** {name}",
                f"**Type:** {atype}",
                f"**Location:** {file_path}:{start_line}-{end_line}",
                f"**Confidence:** {confidence}",
                f"**ID:** {artifact_id}\n",
            ]

            # Add metadata
            if meta:
                result.append("**Metadata:**")
                for key, value in meta.items():
                    if isinstance(value, list) and value:
                        result.append(f"  - {key}: {', '.join(str(v) for v in value[:10])}")
                    elif value:
                        result.append(f"  - {key}: {value}")

            # Add evidence if available
            evidence = artifact.get('evidence', [])
            if evidence:
                result.append(f"\n**Evidence:** {len(evidence)} items")

            return '\n'.join(result)

        except Exception as e:
            logger.error(f"Get artifact error: {e}", exc_info=True)
            return f"❌ Error retrieving artifact: {str(e)}"

    def _search_crs(self, query: str, limit: int = 10) -> str:
        """
        Search CRS data using keyword matching
        Returns results with file:line citations
        NOT for inventory - use LIST_ARTIFACTS for that
        """
        if not query:
            return "❌ Missing 'query' parameter"

        try:
            # Search both blueprints and artifacts
            blueprints = self.retriever.search_blueprints(query, limit=5)
            artifacts = self.retriever.search_artifacts(query, limit=limit)

            if not blueprints and not artifacts:
                return f"🔍 No results found for '{query}'"

            result = [f"🔍 **Search Results for '{query}'**\n"]

            # Show blueprint matches (files)
            if blueprints:
                result.append(f"**📁 Files ({len(blueprints)}):**")
                for bp in blueprints:
                    path = bp.get('path', 'unknown')
                    purpose = bp.get('purpose', 'No purpose')
                    result.append(f"  • {path}")
                    result.append(f"    {purpose}")
                result.append("")

            # Show artifact matches (code elements)
            if artifacts:
                result.append(f"**🎯 Code Elements ({len(artifacts)}):**")
                for artifact in artifacts:
                    name = artifact.get('name', 'unknown')
                    atype = artifact.get('type', 'unknown')
                    file_path = artifact.get('file_path', 'unknown')
                    anchor = artifact.get('anchor', {})
                    start_line = anchor.get('start_line', 0)
                    artifact_id = artifact.get('artifact_id', 'unknown')

                    citation = f"{file_path}:{start_line}"

                    result.append(f"  • **{name}** ({atype})")
                    result.append(f"    📍 {citation}")
                    result.append(f"    🆔 {artifact_id}")
                result.append("")

            result.append("\n💡 Use GET_ARTIFACT with artifact_id to see full details")

            return '\n'.join(result)

        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            return f"❌ Error searching: {str(e)}"

    def _crs_relationships(self, artifact_id: str) -> str:
        """Find relationships for an artifact (imports, calls, used_by)"""
        if not artifact_id:
            return "❌ Missing 'artifact_id' parameter"

        try:
            self.retriever._load_crs_data()
            all_relationships = self.retriever._relationships.get('relationships', [])

            # Find relationships involving this artifact
            incoming = []  # Things that use this artifact
            outgoing = []  # Things this artifact uses

            for rel in all_relationships:
                source = rel.get('source', '')
                target = rel.get('target', '')
                rel_type = rel.get('type', 'unknown')

                if source == artifact_id:
                    outgoing.append((rel_type, target))
                elif target == artifact_id:
                    incoming.append((rel_type, source))

            if not incoming and not outgoing:
                return f"🔗 No relationships found for artifact_id: {artifact_id}"

            result = [f"🔗 **Relationships for {artifact_id}**\n"]

            if outgoing:
                result.append(f"**Outgoing ({len(outgoing)})** - This artifact uses:")
                by_type = {}
                for rel_type, target in outgoing:
                    by_type.setdefault(rel_type, []).append(target)

                for rel_type, targets in by_type.items():
                    result.append(f"  **{rel_type}:**")
                    for target in targets[:10]:
                        result.append(f"    → {target}")
                    if len(targets) > 10:
                        result.append(f"    ... and {len(targets) - 10} more")
                result.append("")

            if incoming:
                result.append(f"**Incoming ({len(incoming)})** - Used by:")
                by_type = {}
                for rel_type, source in incoming:
                    by_type.setdefault(rel_type, []).append(source)

                for rel_type, sources in by_type.items():
                    result.append(f"  **{rel_type}:**")
                    for source in sources[:10]:
                        result.append(f"    ← {source}")
                    if len(sources) > 10:
                        result.append(f"    ... and {len(sources) - 10} more")

            return '\n'.join(result)

        except Exception as e:
            logger.error(f"Relationships error: {e}", exc_info=True)
            return f"❌ Error finding relationships: {str(e)}"

    def _read_file(self, path: str, start_line: int = 1, end_line: int = 100) -> str:
        """Read raw file contents with line numbers"""
        if not path:
            return "❌ Missing 'path' parameter"

        try:
            # Construct full path from repository clone
            if not self.repository.clone_path:
                return "❌ Repository not cloned"

            full_path = Path(self.repository.clone_path) / path

            if not full_path.exists():
                return f"❌ File not found: {path}"

            if not full_path.is_file():
                return f"❌ Not a file: {path}"

            # Read file with line numbers
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Validate line ranges
            total_lines = len(lines)
            start_line = max(1, min(start_line, total_lines))
            end_line = max(start_line, min(end_line, total_lines))

            result = [
                f"📄 **File: {path}**",
                f"📍 Lines {start_line}-{end_line} of {total_lines}\n",
                "```python"
            ]

            for i in range(start_line - 1, end_line):
                line_num = i + 1
                line_content = lines[i].rstrip()
                result.append(f"{line_num:4d} | {line_content}")

            result.append("```")

            if end_line < total_lines:
                result.append(f"\n... {total_lines - end_line} more lines")

            return '\n'.join(result)

        except Exception as e:
            logger.error(f"Read file error: {e}", exc_info=True)
            return f"❌ Error reading file: {str(e)}"
