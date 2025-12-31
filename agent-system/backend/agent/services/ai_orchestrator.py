from typing import Dict, Any, List

from agent.models import Repository, RepositoryReasoningTrace


class AIOrchestrator:
    """
    Coordinates AI analysis and captures reasoning traces.
    """

    def record_trace(self, repository: Repository, stage: str, payload: Dict[str, Any]) -> None:
        RepositoryReasoningTrace.objects.create(
            repository=repository,
            stage=stage,
            payload=payload
        )

    def capture_analysis(self, repository: Repository, analysis: Dict[str, Any]) -> None:
        self.record_trace(repository, "analysis", {
            "analysis": analysis
        })

    def capture_questions(self, repository: Repository, questions: List[Any]) -> None:
        self.record_trace(repository, "questions_generated", {
            "questions": [q.to_dict() if hasattr(q, "to_dict") else q for q in questions]
        })
