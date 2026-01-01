# agent/rag.py
"""
RAG (Retrieval Augmented Generation) for CRS
Context retrieval and search functions
"""

import json
from typing import List, Dict, Any, Tuple
from agent.services.crs_runner import load_crs_payload
import logging

logger = logging.getLogger(__name__)


class CRSRetriever:
    """Retrieves relevant CRS context for user queries"""

    def __init__(self, repository=None, system=None):
        self.repository = repository
        self.system = system
        self._blueprints = None
        self._artifacts = None
        self._relationships = None

    def _load_crs_data(self):
        """Load CRS data from JSON files"""
        if not self.repository:
            return

        if self._blueprints is None:
            try:
                self._blueprints = load_crs_payload(self.repository, "blueprints")
            except Exception as e:
                logger.warning(f"Failed to load blueprints: {e}")
                self._blueprints = {}

        if self._artifacts is None:
            try:
                self._artifacts = load_crs_payload(self.repository, "artifacts")
            except Exception as e:
                logger.warning(f"Failed to load artifacts: {e}")
                self._artifacts = {}

        if self._relationships is None:
            try:
                self._relationships = load_crs_payload(self.repository, "relationships")
            except Exception as e:
                logger.warning(f"Failed to load relationships: {e}")
                self._relationships = {}

    def search_blueprints(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search for blueprints relevant to the query
        Uses simple keyword matching (can be enhanced with embeddings later)
        """
        if not self.repository:
            return []

        self._load_crs_data()
        keywords = self._extract_keywords(query)

        files = self._blueprints.get("files", [])

        # Score each blueprint
        scored = []
        for blueprint in files:
            score = self._score_blueprint(blueprint, keywords)
            if score > 0:
                scored.append((score, blueprint))

        # Sort by score and return top N
        scored.sort(reverse=True, key=lambda x: x[0])
        return [bp for score, bp in scored[:limit]]

    def search_artifacts(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for artifacts relevant to the query
        """
        if not self.repository:
            logger.warning("No repository set for artifact search")
            return []

        self._load_crs_data()
        keywords = self._extract_keywords(query)

        artifacts = self._artifacts.get("artifacts", [])
        query_lower = query.lower()
        if "admin" not in query_lower:
            artifacts = [
                a for a in artifacts
                if "admin.py" not in (a.get("file_path") or a.get("file") or "").lower()
            ]
        logger.info(f"Searching {len(artifacts)} artifacts for keywords: {keywords}")

        # Special handling for "models" query - look for Django Model classes
        if "models" in keywords or "model" in keywords:
            model_artifacts = []
            for artifact in artifacts:
                artifact_type = artifact.get("type", "").lower()
                name = artifact.get("name", "").lower()
                file_path = (artifact.get("file_path") or artifact.get("file") or "").lower()

                # Look for Model classes or models.py files
                if (artifact_type == "class" and "model" in name) or "models.py" in file_path:
                    model_artifacts.append(artifact)

            if model_artifacts:
                logger.info(f"Found {len(model_artifacts)} Django model artifacts")
                return model_artifacts[:limit]

        # Score each artifact
        scored = []
        for artifact in artifacts:
            score = self._score_artifact(artifact, keywords)
            if score > 0:
                scored.append((score, artifact))

        # Sort by score and return top N
        scored.sort(reverse=True, key=lambda x: x[0])
        results = [artifact for score, artifact in scored[:limit]]

        logger.info(f"RAG search returned {len(results)} artifacts")
        return results

    def get_relationships(self, artifacts: List[Dict] = None, limit: int = 20) -> List[Dict]:
        """
        Get relationships for given artifacts or for the repository
        """
        if not self.repository:
            return []

        self._load_crs_data()
        relationships = self._relationships.get("relationships", [])

        if artifacts:
            # Filter to relationships involving these artifacts
            artifact_names = [a.get("name") for a in artifacts]
            filtered = []
            for rel in relationships:
                if rel.get("source") in artifact_names or rel.get("target") in artifact_names:
                    filtered.append(rel)
            return filtered[:limit]

        return relationships[:limit]

    def build_context(self, query: str) -> Dict[str, Any]:
        """
        Build comprehensive context for a query
        Returns structured context with blueprints, artifacts, and relationships
        """
        # Search for relevant content
        blueprints = self.search_blueprints(query)
        artifacts = self.search_artifacts(query)
        relationships = self.get_relationships(artifacts)

        # Format context
        context = {
            'blueprints': [self._format_blueprint(bp) for bp in blueprints],
            'artifacts': [self._format_artifact(a) for a in artifacts],
            'relationships': [self._format_relationship(r) for r in relationships]
        }

        return context

    def build_context_prompt(self, query: str) -> str:
        """
        Build a formatted context prompt for the LLM
        """
        context = self.build_context(query)

        prompt_parts = []

        # Add a clear header
        if context['blueprints'] or context['artifacts'] or context['relationships']:
            prompt_parts.append("# Available Code Context\n\n")
        else:
            logger.warning(f"No context found for query: {query}")
            return "No relevant code found in this repository."

        # Add blueprints section
        if context['blueprints']:
            prompt_parts.append("## Files (Blueprints)\n\n")
            for bp in context['blueprints']:
                prompt_parts.append(f"**File**: `{bp['path']}`\n")
                prompt_parts.append(f"**Purpose**: {bp['purpose']}\n")
                if bp.get('key_components'):
                    components_str = ', '.join(str(c) for c in bp['key_components'])
                    prompt_parts.append(f"**Components**: {components_str}\n")
                prompt_parts.append("\n")

        # Add artifacts section
        if context['artifacts']:
            prompt_parts.append("## Code Elements (Artifacts)\n\n")
            for artifact in context['artifacts']:
                prompt_parts.append(f"**{artifact['name']}** ({artifact['type']})\n")
                if artifact.get('file'):
                    prompt_parts.append(f"- File: `{artifact['file']}`\n")
                if artifact.get('purpose'):
                    prompt_parts.append(f"- Purpose: {artifact['purpose']}\n")
                if artifact.get('signature'):
                    prompt_parts.append(f"- Signature: `{artifact['signature']}`\n")
                if artifact.get('methods'):
                    methods_str = ', '.join(str(m) for m in artifact['methods'][:5])
                    prompt_parts.append(f"- Methods: {methods_str}\n")
                prompt_parts.append("\n")

        # Add relationships section (simplified)
        if context['relationships'] and len(context['relationships']) > 0:
            prompt_parts.append("## Relationships\n\n")
            for rel in context['relationships'][:10]:  # Limit to 10 relationships
                prompt_parts.append(f"- {rel['source']} → {rel['type']} → {rel['target']}\n")
            prompt_parts.append("\n")

        result = ''.join(prompt_parts)
        logger.info(f"Built context prompt: {len(result)} chars, {len(context['blueprints'])} blueprints, {len(context['artifacts'])} artifacts")

        return result

    # Helper methods

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract searchable keywords from query"""
        # Simple tokenization (can be enhanced with NLP)
        # Remove common words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'how', 'what',
                      'where', 'when', 'why', 'does', 'do', 'can', 'could', 'would'}

        words = query.lower().split()
        keywords = [w.strip('?.,!') for w in words if w not in stop_words]
        return keywords

    def _score_blueprint(self, blueprint: Dict, keywords: List[str]) -> float:
        """Score a blueprint based on keyword matches"""
        score = 0.0

        # Search in path (high weight)
        path = blueprint.get("path", "").lower()
        for keyword in keywords:
            if keyword in path:
                score += 2.0

        # Search in purpose
        purpose = blueprint.get("purpose", "").lower()
        for keyword in keywords:
            if keyword in purpose:
                score += 1.5

        # Search in key components
        components = blueprint.get("key_components", [])
        for comp in components:
            comp_lower = str(comp).lower()
            for keyword in keywords:
                if keyword in comp_lower:
                    score += 1.0

        return score

    def _score_artifact(self, artifact: Dict, keywords: List[str]) -> float:
        """Score an artifact based on keyword matches"""
        score = 0.0

        # Search in name (high weight)
        name = artifact.get("name", "").lower()
        for keyword in keywords:
            if keyword in name:
                score += 2.0

        # Search in type
        artifact_type = artifact.get("type", "").lower()
        for keyword in keywords:
            if keyword in artifact_type:
                score += 1.5

        # Search in file path
        file_path = artifact.get("file", "").lower()
        for keyword in keywords:
            if keyword in file_path:
                score += 1.0

        # Search in source code if available
        source = artifact.get("source", "").lower()
        for keyword in keywords:
            if keyword in source:
                score += 0.5

        return score

    def _format_blueprint(self, blueprint: Dict) -> Dict[str, Any]:
        """Format blueprint for context"""
        return {
            'path': blueprint.get('path', ''),
            'purpose': blueprint.get('purpose', ''),
            'key_components': blueprint.get('key_components', []),
            'dependencies': blueprint.get('dependencies', []),
            'used_by': blueprint.get('used_by', [])
        }

    def _format_artifact(self, artifact: Dict) -> Dict[str, Any]:
        """Format artifact for context"""
        formatted = {
            'name': artifact.get('name', ''),
            'type': artifact.get('type', ''),
            'file': artifact.get('file', ''),
            'purpose': artifact.get('purpose', '')
        }

        # Add type-specific fields
        artifact_type = artifact.get('type', '')
        if artifact_type == 'function':
            formatted['signature'] = self._build_function_signature(artifact)
        elif artifact_type == 'class':
            formatted['methods'] = artifact.get('methods', [])
        elif artifact_type == 'api_endpoint':
            formatted['route'] = artifact.get('route', '')
            formatted['method'] = artifact.get('method', '')

        return formatted

    def _format_relationship(self, relationship: Dict) -> Dict[str, Any]:
        """Format relationship for context"""
        return {
            'source': relationship.get('source', 'Unknown'),
            'target': relationship.get('target', 'Unknown'),
            'type': relationship.get('type', ''),
            'context': relationship.get('context', '')
        }

    def _build_function_signature(self, artifact: Dict) -> str:
        """Build a function signature string"""
        name = artifact.get('name', 'unknown')
        params = artifact.get('parameters', [])
        return_type = artifact.get('return_type', 'void')

        if isinstance(params, list):
            param_str = ', '.join([
                f"{p.get('name', '')}: {p.get('type', 'Any')}"
                for p in params
            ]) if params else ''
        else:
            param_str = str(params)

        return f"{name}({param_str}) -> {return_type}"


class ConversationMemory:
    """Manages conversation memory and context"""

    def __init__(self, conversation):
        self.conversation = conversation

    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent messages from conversation"""
        messages = self.conversation.messages.order_by('-created_at')[:limit]
        return [
            {
                'role': msg.role,
                'content': msg.content
            }
            for msg in reversed(messages)
        ]

    def summarize_conversation(self) -> str:
        """Summarize the conversation context"""
        messages = self.get_recent_messages(limit=5)

        if not messages:
            return "No previous conversation history."

        summary_parts = ["Previous conversation:"]
        for msg in messages:
            role = "User" if msg['role'] == 'user' else "Assistant"
            content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            summary_parts.append(f"{role}: {content}")

        return '\n'.join(summary_parts)
