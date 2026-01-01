"""
CRS Context Service - Retrieves relevant context from CRS artifacts for LLM chat
"""
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from agent.models import Repository
from agent.services.crs_runner import load_crs_payload

logger = logging.getLogger(__name__)


class CRSContext:
    """
    Provides context from CRS artifacts for LLM queries

    Retrieves and formats:
    - Blueprints (file structure, function/class definitions)
    - Artifacts (extracted code elements)
    - Relationships (dependencies, imports, calls)
    """

    def __init__(self, repository: Repository):
        self.repository = repository
        self._blueprints = None
        self._artifacts = None
        self._relationships = None

    def load_all(self):
        """Load all CRS payloads"""
        try:
            self._blueprints = load_crs_payload(self.repository, "blueprints")
        except Exception as e:
            logger.warning(f"Failed to load blueprints: {e}")
            self._blueprints = {}

        try:
            self._artifacts = load_crs_payload(self.repository, "artifacts")
        except Exception as e:
            logger.warning(f"Failed to load artifacts: {e}")
            self._artifacts = {}

        try:
            self._relationships = load_crs_payload(self.repository, "relationships")
        except Exception as e:
            logger.warning(f"Failed to load relationships: {e}")
            self._relationships = {}

    def has_payloads(self) -> bool:
        """Check if any CRS payloads have usable data."""
        if self._blueprints is None or self._artifacts is None or self._relationships is None:
            self.load_all()

        return any([
            bool(self._blueprints and self._blueprints.get("files")),
            bool(self._artifacts and self._artifacts.get("artifacts")),
            bool(self._relationships and self._relationships.get("relationships")),
        ])

    def get_file_list(self) -> List[str]:
        """Get list of all files in blueprints"""
        if not self._blueprints:
            self.load_all()

        files = self._blueprints.get("files", [])
        return [f.get("path", "") for f in files if f.get("path")]

    def get_file_blueprint(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get blueprint for specific file"""
        if not self._blueprints:
            self.load_all()

        files = self._blueprints.get("files", [])
        for f in files:
            if f.get("path") == file_path:
                return f
        return None

    def search_artifacts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search artifacts by name/type

        Returns list of matching artifacts with their details
        """
        if not self._artifacts:
            self.load_all()

        query_lower = query.lower()
        artifacts = self._artifacts.get("artifacts", [])
        if "admin" not in query_lower:
            artifacts = [
                a for a in artifacts
                if "admin.py" not in (a.get("file_path") or a.get("file") or "").lower()
            ]

        matches = []
        for artifact in artifacts:
            name = artifact.get("name", "").lower()
            artifact_type = artifact.get("type", "").lower()

            if query_lower in name or query_lower in artifact_type:
                matches.append(artifact)
                if len(matches) >= limit:
                    break

        return matches

    def get_artifact_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get specific artifact by exact name"""
        if not self._artifacts:
            self.load_all()

        artifacts = self._artifacts.get("artifacts", [])
        for artifact in artifacts:
            if artifact.get("name") == name:
                return artifact
        return None

    def get_artifact_relationships(self, artifact_name: str) -> Dict[str, List[str]]:
        """
        Get relationships for an artifact

        Returns:
            {
                "imports": [...],
                "calls": [...],
                "used_by": [...]
            }
        """
        if not self._relationships:
            self.load_all()

        relationships = self._relationships.get("relationships", [])

        result = {
            "imports": [],
            "calls": [],
            "used_by": []
        }

        for rel in relationships:
            rel_type = rel.get("type", "")
            source = rel.get("source", "")
            target = rel.get("target", "")

            # Check if this artifact is involved
            if source == artifact_name:
                if rel_type == "imports":
                    result["imports"].append(target)
                elif rel_type == "calls":
                    result["calls"].append(target)

            if target == artifact_name:
                result["used_by"].append(source)

        return result

    def get_artifact_type_counts(self) -> Dict[str, int]:
        """Get counts of artifacts by type."""
        if not self._artifacts:
            self.load_all()

        artifacts = self._artifacts.get("artifacts", []) if self._artifacts else []
        artifacts = [
            a for a in artifacts
            if "admin.py" not in (a.get("file_path") or a.get("file") or "").lower()
        ]
        artifact_types: Dict[str, int] = {}
        for artifact in artifacts:
            art_type = artifact.get("type", "unknown")
            artifact_types[art_type] = artifact_types.get(art_type, 0) + 1

        return artifact_types

    def build_artifact_type_summary(self) -> str:
        """Build a short summary of available artifact types and counts."""
        artifact_types = self.get_artifact_type_counts()
        if not artifact_types:
            return "Available artifact types: none (0 artifacts)."

        summary_parts = [
            f"{art_type}: {count}"
            for art_type, count in sorted(artifact_types.items())
        ]
        return "Available artifact types: " + ", ".join(summary_parts)

    def build_context_summary(self) -> str:
        """
        Build a summary of the repository for LLM context

        Returns formatted text summary
        """
        if not self._blueprints:
            self.load_all()

        parts = []

        # Repository info
        parts.append(f"Repository: {self.repository.name}")
        parts.append(f"GitHub: {self.repository.github_url}")
        parts.append("")

        # File structure
        files = self.get_file_list()
        parts.append(f"Files ({len(files)}):")
        for file_path in files[:20]:  # First 20 files
            parts.append(f"  - {file_path}")
        if len(files) > 20:
            parts.append(f"  ... and {len(files) - 20} more")
        parts.append("")

        # Artifacts summary
        if self._artifacts:
            artifacts = self._artifacts.get("artifacts", [])
            artifact_types = {}
            for artifact in artifacts:
                art_type = artifact.get("type", "unknown")
                artifact_types[art_type] = artifact_types.get(art_type, 0) + 1

            parts.append(f"Artifacts ({len(artifacts)}):")
            for art_type, count in sorted(artifact_types.items()):
                parts.append(f"  - {art_type}: {count}")
            parts.append("")

        # Relationships summary
        if self._relationships:
            relationships = self._relationships.get("relationships", [])
            parts.append(f"Relationships: {len(relationships)}")
            parts.append("")

        return "\n".join(parts)

    def build_artifact_context(self, artifact_names: List[str]) -> str:
        """
        Build detailed context for specific artifacts

        Args:
            artifact_names: List of artifact names to include

        Returns:
            Formatted text with artifact details and relationships
        """
        if not self._artifacts:
            self.load_all()

        parts = []

        for name in artifact_names:
            artifact = self.get_artifact_by_name(name)
            if not artifact:
                continue

            parts.append(f"=== {name} ===")
            parts.append(f"Type: {artifact.get('type', 'unknown')}")
            parts.append(f"File: {artifact.get('file', 'unknown')}")

            # Add source code if available
            if artifact.get("source"):
                parts.append("Source:")
                parts.append(artifact["source"])

            # Add relationships
            rels = self.get_artifact_relationships(name)
            if rels["imports"]:
                parts.append(f"Imports: {', '.join(rels['imports'])}")
            if rels["calls"]:
                parts.append(f"Calls: {', '.join(rels['calls'])}")
            if rels["used_by"]:
                parts.append(f"Used by: {', '.join(rels['used_by'])}")

            parts.append("")

        return "\n".join(parts)

    def search_context(self, query: str, limit: int = 5) -> str:
        """
        Search CRS data and build context string

        This is the main method for chat - searches artifacts and builds
        relevant context based on user query
        """
        # Search for matching artifacts
        matches = self.search_artifacts(query, limit=limit)
        match_names = [m.get("name", "") for m in matches]
        logger.info(
            "CRS retrieval matched %d artifacts: %s",
            len(matches),
            ", ".join(match_names[:5]) if match_names else "none",
        )

        if not matches:
            summary = self.build_artifact_type_summary()
            return (
                f"No artifacts found matching '{query}'.\n"
                f"{summary}\n"
                "Available files:\n"
                + "\n".join(f"  - {f}" for f in self.get_file_list()[:10])
            )

        # Build context from matches
        artifact_names = [m["name"] for m in matches]
        return self.build_artifact_context(artifact_names)
