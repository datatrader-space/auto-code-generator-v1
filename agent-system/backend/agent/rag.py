# agent/rag.py
"""
RAG (Retrieval Augmented Generation) for CRS
Context retrieval and search functions
"""

import json
from typing import List, Dict, Any, Tuple
from agent.models import Blueprint, Artifact, Relationship


class CRSRetriever:
    """Retrieves relevant CRS context for user queries"""

    def __init__(self, repository=None, system=None):
        self.repository = repository
        self.system = system

    def search_blueprints(self, query: str, limit: int = 5) -> List[Blueprint]:
        """
        Search for blueprints relevant to the query
        Uses simple keyword matching (can be enhanced with embeddings later)
        """
        if not self.repository:
            return []

        keywords = self._extract_keywords(query)
        blueprints = Blueprint.objects.filter(repository=self.repository)

        # Score each blueprint
        scored = []
        for bp in blueprints:
            score = self._score_blueprint(bp, keywords)
            if score > 0:
                scored.append((score, bp))

        # Sort by score and return top N
        scored.sort(reverse=True, key=lambda x: x[0])
        return [bp for score, bp in scored[:limit]]

    def search_artifacts(self, query: str, limit: int = 10) -> List[Artifact]:
        """
        Search for artifacts relevant to the query
        """
        if not self.repository:
            return []

        keywords = self._extract_keywords(query)
        artifacts = Artifact.objects.filter(repository=self.repository)

        # Score each artifact
        scored = []
        for artifact in artifacts:
            score = self._score_artifact(artifact, keywords)
            if score > 0:
                scored.append((score, artifact))

        # Sort by score and return top N
        scored.sort(reverse=True, key=lambda x: x[0])
        return [artifact for score, artifact in scored[:limit]]

    def get_relationships(self, artifacts: List[Artifact] = None, limit: int = 20) -> List[Relationship]:
        """
        Get relationships for given artifacts or for the repository
        """
        if not self.repository:
            return []

        relationships = Relationship.objects.filter(repository=self.repository)

        if artifacts:
            # Filter to relationships involving these artifacts
            artifact_ids = [a.id for a in artifacts]
            relationships = relationships.filter(
                source_artifact_id__in=artifact_ids
            ) | relationships.filter(
                target_artifact_id__in=artifact_ids
            )

        return list(relationships[:limit])

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

        # Add blueprints section
        if context['blueprints']:
            prompt_parts.append("## Relevant Blueprints\n")
            for bp in context['blueprints']:
                prompt_parts.append(f"### {bp['path']}\n")
                prompt_parts.append(f"**Purpose**: {bp['purpose']}\n")
                if bp['key_components']:
                    prompt_parts.append(f"**Key Components**: {', '.join(bp['key_components'])}\n")
                prompt_parts.append("\n")

        # Add artifacts section
        if context['artifacts']:
            prompt_parts.append("## Relevant Artifacts\n")
            for artifact in context['artifacts']:
                prompt_parts.append(f"### {artifact['name']} ({artifact['type']})\n")
                prompt_parts.append(f"**Location**: {artifact['location']}\n")
                if artifact.get('purpose'):
                    prompt_parts.append(f"**Purpose**: {artifact['purpose']}\n")
                if artifact.get('signature'):
                    prompt_parts.append(f"**Signature**: `{artifact['signature']}`\n")
                prompt_parts.append("\n")

        # Add relationships section
        if context['relationships']:
            prompt_parts.append("## Relevant Relationships\n")
            for rel in context['relationships']:
                prompt_parts.append(
                    f"- {rel['source']} **{rel['type']}** {rel['target']}"
                )
                if rel.get('context'):
                    prompt_parts.append(f" ({rel['context']})")
                prompt_parts.append("\n")

        return ''.join(prompt_parts)

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

    def _score_blueprint(self, blueprint: Blueprint, keywords: List[str]) -> float:
        """Score a blueprint based on keyword matches"""
        score = 0.0

        # Search in path (high weight)
        path_lower = blueprint.path.lower()
        for keyword in keywords:
            if keyword in path_lower:
                score += 2.0

        # Search in content_json
        if blueprint.content_json:
            content_str = json.dumps(blueprint.content_json).lower()
            for keyword in keywords:
                if keyword in content_str:
                    score += 1.0

        return score

    def _score_artifact(self, artifact: Artifact, keywords: List[str]) -> float:
        """Score an artifact based on keyword matches"""
        score = 0.0

        # Search in name (high weight)
        name_lower = artifact.name.lower()
        for keyword in keywords:
            if keyword in name_lower:
                score += 2.0

        # Search in type
        type_lower = artifact.artifact_type.lower()
        for keyword in keywords:
            if keyword in type_lower:
                score += 1.5

        # Search in content_json
        if artifact.content_json:
            content_str = json.dumps(artifact.content_json).lower()
            for keyword in keywords:
                if keyword in content_str:
                    score += 1.0

        return score

    def _format_blueprint(self, blueprint: Blueprint) -> Dict[str, Any]:
        """Format blueprint for context"""
        content = blueprint.content_json or {}
        return {
            'path': blueprint.path,
            'purpose': content.get('purpose', ''),
            'key_components': content.get('key_components', []),
            'dependencies': content.get('dependencies', []),
            'used_by': content.get('used_by', [])
        }

    def _format_artifact(self, artifact: Artifact) -> Dict[str, Any]:
        """Format artifact for context"""
        content = artifact.content_json or {}
        formatted = {
            'name': artifact.name,
            'type': artifact.artifact_type,
            'location': content.get('location', artifact.name)
        }

        # Add type-specific fields
        if artifact.artifact_type == 'function':
            formatted['signature'] = self._build_function_signature(content)
            formatted['purpose'] = content.get('purpose', '')
        elif artifact.artifact_type == 'class':
            formatted['methods'] = content.get('methods', [])
            formatted['purpose'] = content.get('purpose', '')
        elif artifact.artifact_type == 'api_endpoint':
            formatted['route'] = content.get('route', '')
            formatted['method'] = content.get('method', '')
            formatted['purpose'] = content.get('purpose', '')

        return formatted

    def _format_relationship(self, relationship: Relationship) -> Dict[str, Any]:
        """Format relationship for context"""
        return {
            'source': relationship.source_artifact.name if relationship.source_artifact else 'Unknown',
            'target': relationship.target_artifact.name if relationship.target_artifact else 'Unknown',
            'type': relationship.relationship_type,
            'context': relationship.context or ''
        }

    def _build_function_signature(self, content: Dict) -> str:
        """Build a function signature string"""
        name = content.get('name', 'unknown')
        params = content.get('parameters', [])
        return_type = content.get('return_type', 'void')

        param_str = ', '.join([
            f"{p.get('name', '')}: {p.get('type', 'Any')}"
            for p in params
        ]) if isinstance(params, list) else ''

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
