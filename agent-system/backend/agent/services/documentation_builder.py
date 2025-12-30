from typing import Dict, Any, List

from agent.models import System, SystemDocumentation, SystemKnowledge


class DocumentationBuilder:
    """
    Builds system documentation payloads from knowledge items and CRS outputs.
    """

    def build_overview(self, system: System) -> Dict[str, Any]:
        knowledge_items = list(SystemKnowledge.objects.filter(system=system))
        return {
            "system": {
                "id": system.id,
                "name": system.name,
                "description": system.description,
                "status": system.status,
            },
            "knowledge": [
                {
                    "type": item.knowledge_type,
                    "spec_id": item.spec_id,
                    "content": item.content,
                    "confidence": item.confidence,
                    "source": item.source,
                }
                for item in knowledge_items
            ],
        }

    def upsert_overview(self, system: System) -> SystemDocumentation:
        payload = self.build_overview(system)
        documentation, _ = SystemDocumentation.objects.update_or_create(
            system=system,
            doc_type="overview",
            defaults={"content": payload},
        )
        return documentation
