#!/usr/bin/env python
"""
Complete Prototype Test Script

This tests the entire flow end-to-end:
1. Create user and system
2. Add repository
3. Clone repo (mocked for now)
4. Analyze with LLM
5. Generate questions
6. Submit answers
7. Build knowledge
8. Show results

Run:
    python manage.py shell < prototype_test.py
    
Or:
    python prototype_test.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agent.models import User, System, Repository, RepositoryQuestion, SystemKnowledge
from agent.services.repo_analyzer import RepositoryAnalyzer
from agent.services.question_generator import QuestionGenerator
from agent.services.knowledge_builder import KnowledgeBuilder
from agent.services.github_client import GitHubClient


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def run_prototype_test():
    """Run complete prototype test"""
    
    print_section("🚀 CRS Agent Prototype Test")
    
    # =========================================
    # Step 1: Create User and System
    # =========================================
    print_section("Step 1: Create User and System")
    
    # Create or get user
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={'email': 'test@example.com'}
    )
    if created:
        user.set_password('test123')
        user.save()
        print("✅ Created user: testuser")
    else:
        print("✅ Using existing user: testuser")
    
    # Create system
    system, created = System.objects.get_or_create(
        user=user,
        name='Test E-commerce Platform',
        defaults={
            'slug': 'test-ecommerce',
            'description': '4-house architecture test',
            'status': 'initializing'
        }
    )
    
    if created:
        print(f"✅ Created system: {system.name}")
    else:
        print(f"✅ Using existing system: {system.name}")
        # Clean up old data
        system.repositories.all().delete()
        system.knowledge.all().delete()
    
    # =========================================
    # Step 2: Add Repository (Mocked)
    # =========================================
    print_section("Step 2: Add Repository")
    
    # For prototype, we'll mock a repository structure
    # In real usage, this would clone from GitHub
    
    repo = Repository.objects.create(
        system=system,
        name='worker',
        github_url='https://github.com/example/worker',
        github_branch='main',
        status='pending'
    )
    
    print(f"✅ Added repository: {repo.name}")
    print(f"   GitHub: {repo.github_url}")
    
    # =========================================
    # Step 3: Mock Repository Structure
    # =========================================
    print_section("Step 3: Mock Repository Structure")
    
    # For prototype, we'll use a mocked analysis
    # In production, this comes from actual cloned code
    
    mock_clone_path = '/tmp/mock_worker_repo'
    repo.clone_path = mock_clone_path
    repo.status = 'cloning'
    repo.save()
    
    print(f"✅ Mock clone path: {mock_clone_path}")
    print("   (In production, GitHubClient would clone actual repo)")
    
    # =========================================
    # Step 4: Analyze with LLM
    # =========================================
    print_section("Step 4: Analyze Repository with LLM")
    
    # For prototype, use mock analysis if LLM not available
    analyzer = RepositoryAnalyzer()
    
    # Check LLM health
    from llm.router import get_llm_router
    llm = get_llm_router()
    health = llm.health_check()
    
    print(f"LLM Health: {health}")
    
    if health['local']['available'] or health['cloud']['available']:
        print("✅ LLM available, running real analysis...")
        
        # Create minimal mock repo structure for analysis
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal structure
            (Path(tmpdir) / 'services').mkdir()
            (Path(tmpdir) / 'services' / 'order_service.py').write_text("""
class OrderProcessingService:
    def process_order(self, order_id):
        # Call DataHouse API
        response = requests.get(f'http://datahouse/api/orders/{order_id}')
        order = response.json()
        status = order['status']
        
        if status == 'pending':
            # Process order
            pass
""")
            
            (Path(tmpdir) / 'requirements.txt').write_text("requests==2.31.0\ncelery==5.3.0")
            
            try:
                analysis = analyzer.analyze(tmpdir, repo.name)
                print(f"✅ LLM Analysis complete:")
                print(f"   Paradigm: {analysis.get('paradigm')}")
                print(f"   Confidence: {analysis.get('confidence', 0):.0%}")
                print(f"   Can use standard CRS: {analysis.get('can_use_standard_crs')}")
            except Exception as e:
                print(f"⚠️  LLM analysis failed: {e}")
                print("   Using mock analysis instead...")
                analysis = None
    else:
        print("⚠️  No LLM available, using mock analysis...")
        analysis = None
    
    # Use mock analysis if LLM failed
    if not analysis:
        analysis = {
            "paradigm": "service_classes",
            "patterns": ["class-based", "api-calls"],
            "key_concepts": ["service", "api_client", "handler"],
            "framework_detected": "None",
            "can_use_standard_crs": False,
            "confidence": 0.85,
            "uncertainty": [
                "Does this call DataHouse APIs?",
                "Which fields from Order model are used?"
            ],
            "reasoning": "Detected service-based architecture with API calls to external services.",
            "dependencies": ["requests", "celery"]
        }
        print(f"✅ Using mock analysis:")
        print(f"   Paradigm: {analysis['paradigm']}")
        print(f"   Confidence: {analysis['confidence']:.0%}")
    
    # Save analysis
    repo.analysis = analysis
    repo.status = 'questions_generated'
    repo.save()
    
    # =========================================
    # Step 5: Generate Questions
    # =========================================
    print_section("Step 5: Generate Questions")
    
    generator = QuestionGenerator()
    
    # Get other repos in system (for cross-repo questions)
    other_repos = [
        {'name': 'datahouse', 'paradigm': 'django'},
        {'name': 'central', 'paradigm': 'django'},
        {'name': 'storagehouse', 'paradigm': 'fastapi'}
    ]
    
    questions = generator.generate_questions(
        repo_name=repo.name,
        analysis=analysis,
        other_repos=other_repos
    )
    
    print(f"✅ Generated {len(questions)} questions:\n")
    
    for idx, q in enumerate(questions, 1):
        print(f"{idx}. [{q.category}] {q.text}")
        if q.options:
            for opt in q.options:
                print(f"   - {opt}")
        print()
        
        # Save to database
        RepositoryQuestion.objects.create(
            repository=repo,
            question_key=q.key,
            question_text=q.text,
            question_type=q.type,
            options=q.options,
            required=q.required,
            category=q.category,
            order=idx
        )
    
    # =========================================
    # Step 6: Simulate User Answers
    # =========================================
    print_section("Step 6: User Answers Questions")
    
    # Mock answers (in production, from UI/Slack)
    answers = {
        "paradigm_confirm": "Yes, it's service_classes",
        "service_pattern": "Class-based services (e.g., OrderService)",
        "calls_other_repos": "yes",
        "calls_which_repos": "datahouse",
        "communication_method": "REST API calls",
        "uses_models": "yes",
        "model_fields_used": "Order.status, Order.items",
        "naming_conventions": "Services end with 'Service', all lowercase with underscores"
    }
    
    print("✅ Mock answers provided:")
    for key, val in answers.items():
        print(f"   {key}: {val}")
    
    # Save answers
    for question in RepositoryQuestion.objects.filter(repository=repo):
        if question.question_key in answers:
            question.answer = answers[question.question_key]
            question.save()
    
    # =========================================
    # Step 7: Build Knowledge
    # =========================================
    print_section("Step 7: Build System Knowledge")
    
    builder = KnowledgeBuilder()
    
    # Build repo config
    config = builder.build_repo_knowledge(repo, answers)
    
    print(f"✅ Repository configuration:")
    print(f"   Paradigm: {config['paradigm']}")
    print(f"   Artifact types: {', '.join(config['artifact_types'])}")
    print(f"   Fields used: {', '.join(config['fields_used'])}")
    print(f"   Can use standard CRS: {config['can_use_standard_crs']}")
    
    # Build system knowledge
    all_repos = [repo]  # In real system, would have all 4 repos
    knowledge_items = builder.build_system_knowledge(system, all_repos)
    
    print(f"\n✅ Created {len(knowledge_items)} system knowledge items:")
    for item in knowledge_items:
        print(f"   - {item.knowledge_type}: {item.spec_id}")
    
    # Update system status
    system.status = 'ready'
    system.save()
    
    # =========================================
    # Step 8: Display Results
    # =========================================
    print_section("Step 8: Final Results")
    
    print(f"System: {system.name}")
    print(f"Status: {system.status}")
    print(f"Repositories: {system.repositories.count()}")
    print(f"Knowledge Items: {system.knowledge.count()}")
    
    print(f"\nRepository: {repo.name}")
    print(f"Status: {repo.status}")
    print(f"Paradigm: {repo.config.get('paradigm')}")
    print(f"Questions answered: {repo.questions.filter(answer__isnull=False).count()}/{repo.questions.count()}")
    
    print("\n" + "=" * 60)
    print("  ✅ PROTOTYPE TEST COMPLETE!")
    print("=" * 60)
    
    print("\n📊 Summary:")
    print(f"   User: {user.username}")
    print(f"   System: {system.name} ({system.status})")
    print(f"   Repository: {repo.name} ({repo.status})")

    confidence = repo.analysis.get('confidence', 0) or 0
    print(f"   Analysis: {repo.analysis.get('paradigm')} (confidence: {confidence:.0%})")
    print(f"   Knowledge: {len(knowledge_items)} items")
    
    print("\n🎯 Next Steps:")
    print("   1. Build Vue frontend for this flow")
    print("   2. Add real GitHub cloning")
    print("   3. Generate custom extractors")
    print("   4. Run CRS on analyzed repos")
    print("   5. Build task execution engine")
    
    return {
        "success": True,
        "user": user,
        "system": system,
        "repository": repo,
        "knowledge_items": knowledge_items
    }


if __name__ == '__main__':
    try:
        from pathlib import Path
        result = run_prototype_test()
        
        if result['success']:
            print("\n✅ Test passed!")
            sys.exit(0)
        else:
            print("\n❌ Test failed!")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)