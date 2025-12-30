# agent/services/question_generator.py
"""
Question Generator - Creates questions for user based on LLM analysis

Takes the uncertainty from LLM analysis and generates structured questions
that the user can answer to complete the repository understanding.
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass

from llm.router import get_llm_router

logger = logging.getLogger(__name__)


@dataclass
class Question:
    """Structured question for user"""
    key: str
    text: str
    type: str  # yes_no, multiple_choice, text, list
    options: List[str] = None
    required: bool = True
    category: str = "general"
    help_text: str = ""


class QuestionGenerator:
    """
    Generates questions based on repository analysis
    
    Questions help fill gaps in LLM's understanding and guide
    custom extractor generation.
    """
    
    def __init__(self):
        self.llm = get_llm_router()
    
    def generate_questions(
        self,
        repo_name: str,
        analysis: Dict[str, Any],
        other_repos: List[Dict[str, Any]] = None
    ) -> List[Question]:
        """
        Generate questions based on analysis
        
        Args:
            repo_name: Repository name
            analysis: LLM analysis result
            other_repos: Other repositories in the system (for cross-repo questions)
            
        Returns:
            List of structured questions
        """
        
        questions = []
        
        paradigm = analysis.get('paradigm', 'unknown')
        confidence = analysis.get('confidence', 0.0)
        uncertainty = analysis.get('uncertainty', [])
        can_use_standard_crs = analysis.get('can_use_standard_crs', False)
        
        # 1. Paradigm confirmation (if low confidence)
        if confidence < 0.8 or paradigm == 'unknown':
            questions.append(Question(
                key="paradigm_confirm",
                text=f"LLM detected '{paradigm}' with {confidence:.0%} confidence. Is this correct?",
                type="multiple_choice",
                options=[
                    "Yes, it's " + paradigm,
                    "No, it's Django",
                    "No, it's FastAPI",
                    "No, it's Celery tasks",
                    "No, it's service classes",
                    "No, it's something else"
                ],
                required=True,
                category="structure",
                help_text="This helps us understand how to analyze your code."
            ))
        
        # 2. Django-specific questions
        if paradigm == 'django' or can_use_standard_crs:
            questions.append(Question(
                key="django_apps",
                text="Which Django apps contain business logic? (comma-separated)",
                type="list",
                required=False,
                category="structure",
                help_text="e.g., orders, customers, payments"
            ))
        
        # 3. Service/class-based questions
        if paradigm in ['service_classes', 'microservice'] or 'service' in str(analysis):
            questions.append(Question(
                key="service_pattern",
                text="How are services organized?",
                type="multiple_choice",
                options=[
                    "Class-based services (e.g., OrderService)",
                    "Function-based handlers",
                    "Mix of both",
                    "Other pattern"
                ],
                required=True,
                category="patterns"
            ))
            
            questions.append(Question(
                key="service_methods",
                text="What do service methods typically do?",
                type="multiple_choice",
                options=[
                    "Call external APIs",
                    "Process business logic",
                    "Handle database operations",
                    "All of the above"
                ],
                required=False,
                category="patterns"
            ))
        
        # 4. Cross-repo dependency questions
        if other_repos:
            other_names = [r['name'] for r in other_repos]
            
            questions.append(Question(
                key="calls_other_repos",
                text=f"Does {repo_name} communicate with other repos?",
                type="yes_no",
                required=True,
                category="dependencies"
            ))
            
            questions.append(Question(
                key="calls_which_repos",
                text=f"Which repos does {repo_name} communicate with?",
                type="multiple_choice",
                options=other_names,
                required=False,
                category="dependencies",
                help_text="Select all that apply"
            ))
            
            questions.append(Question(
                key="communication_method",
                text="How does it communicate?",
                type="multiple_choice",
                options=[
                    "REST API calls",
                    "Message queue (RabbitMQ, Redis)",
                    "Direct database access",
                    "Shared Python imports",
                    "gRPC",
                    "Other"
                ],
                required=False,
                category="dependencies"
            ))
        
        # 5. Model/field usage questions
        questions.append(Question(
            key="uses_models",
            text=f"Does {repo_name} reference models from other repos?",
            type="yes_no",
            required=True,
            category="dependencies"
        ))
        
        questions.append(Question(
            key="model_fields_used",
            text="Which model fields does it use? (e.g., Order.status, Customer.email)",
            type="text",
            required=False,
            category="dependencies",
            help_text="List key fields, comma-separated"
        ))
        
        # 6. LLM-generated questions from uncertainty
        if uncertainty:
            for idx, uncertain_item in enumerate(uncertainty[:3]):  # Max 3
                questions.append(Question(
                    key=f"llm_uncertainty_{idx}",
                    text=uncertain_item,
                    type="text",
                    required=False,
                    category="clarification",
                    help_text="LLM needs clarification on this point"
                ))
        
        # 7. Coding conventions
        questions.append(Question(
            key="naming_conventions",
            text="Any specific naming conventions? (e.g., all services end with 'Service')",
            type="text",
            required=False,
            category="conventions"
        ))
        
        return questions
    
    def generate_questions_with_llm(
        self,
        repo_name: str,
        analysis: Dict[str, Any],
        other_repos: List[Dict[str, Any]] = None
    ) -> List[Question]:
        """
        Use LLM to generate more intelligent questions
        
        This asks the LLM to create contextual questions based on
        what it found confusing in the analysis.
        """
        
        prompt = f"""
Based on this repository analysis, generate 3-5 clarifying questions for the user.

Repository: {repo_name}
Analysis:
{analysis}

Other repositories in system: {[r['name'] for r in (other_repos or [])]}

Generate questions that will help us:
1. Understand the code architecture better
2. Detect cross-repository dependencies
3. Identify which fields/models are used
4. Understand communication patterns

Return JSON array of questions:
[
  {{
    "key": "unique_key",
    "text": "Question text?",
    "type": "yes_no|multiple_choice|text|list",
    "options": ["opt1", "opt2"],  // only for multiple_choice
    "category": "structure|dependencies|patterns|conventions"
  }}
]

Return ONLY the JSON array, no other text.
"""
        
        try:
            response = self.llm.query(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at asking clarifying questions about codebases."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                json_mode=True,
                provider=None
            )
            
            questions_data = self.llm.parse_json_response(response)
            
            # Convert to Question objects
            questions = []
            for q_data in questions_data:
                questions.append(Question(
                    key=q_data['key'],
                    text=q_data['text'],
                    type=q_data['type'],
                    options=q_data.get('options'),
                    required=False,
                    category=q_data.get('category', 'general')
                ))
            
            return questions
            
        except Exception as e:
            logger.error(f"LLM question generation failed: {e}")
            # Fallback to rule-based questions
            return self.generate_questions(repo_name, analysis, other_repos)
    
    def validate_answers(
        self,
        questions: List[Question],
        answers: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate user answers
        
        Returns:
            {
                "valid": bool,
                "errors": [{"key": "...", "error": "..."}],
                "warnings": [...]
            }
        """
        
        errors = []
        warnings = []
        
        for question in questions:
            answer = answers.get(question.key)
            
            # Check required
            if question.required and not answer:
                errors.append({
                    "key": question.key,
                    "error": "This question is required"
                })
                continue
            
            # Type validation
            if answer:
                if question.type == 'yes_no':
                    if answer not in ['yes', 'no', True, False]:
                        errors.append({
                            "key": question.key,
                            "error": "Answer must be yes/no"
                        })
                
                elif question.type == 'multiple_choice':
                    if question.options and answer not in question.options:
                        errors.append({
                            "key": question.key,
                            "error": f"Answer must be one of: {question.options}"
                        })
                
                elif question.type == 'list':
                    if not isinstance(answer, list):
                        # Try to parse comma-separated string
                        if isinstance(answer, str):
                            answers[question.key] = [x.strip() for x in answer.split(',')]
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }