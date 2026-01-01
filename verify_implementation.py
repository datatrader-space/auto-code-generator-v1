#!/usr/bin/env python3
"""
Verification script for Maximal Agent Runner implementation
Checks that all required files exist and have expected content
Does not require Django or running server
"""

import os
import json
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def check_file_exists(path, description):
    """Check if a file exists"""
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"{Colors.GREEN}✅ {description}{Colors.END}")
        print(f"   Path: {path}")
        print(f"   Size: {size} bytes")
        return True
    else:
        print(f"{Colors.RED}❌ {description}{Colors.END}")
        print(f"   Path: {path} (NOT FOUND)")
        return False

def check_file_contains(path, search_strings, description):
    """Check if file contains expected strings"""
    if not os.path.exists(path):
        print(f"{Colors.RED}❌ {description} - File not found{Colors.END}")
        return False

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    missing = []
    for search_str in search_strings:
        if search_str not in content:
            missing.append(search_str)

    if not missing:
        print(f"{Colors.GREEN}✅ {description}{Colors.END}")
        return True
    else:
        print(f"{Colors.RED}❌ {description}{Colors.END}")
        print(f"   Missing: {', '.join(missing)}")
        return False

def main():
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}Maximal Agent Runner - Implementation Verification{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")

    base_path = Path(__file__).parent
    results = []

    # Phase 1: Core Infrastructure
    print(f"\n{Colors.BLUE}Phase 1: Core Infrastructure{Colors.END}")
    print("-" * 60)

    results.append(check_file_exists(
        base_path / "agent-system/backend/agent/services/knowledge_agent.py",
        "Knowledge Agent service"
    ))

    results.append(check_file_contains(
        base_path / "agent-system/backend/agent/services/knowledge_agent.py",
        ["class RepositoryKnowledgeAgent", "def analyze_repository", "def incremental_update"],
        "Knowledge Agent has required methods"
    ))

    results.append(check_file_exists(
        base_path / "agent-system/backend/agent/services/agent_runner.py",
        "Agent Runner service"
    ))

    results.append(check_file_contains(
        base_path / "agent-system/backend/agent/services/agent_runner.py",
        ["class AgentRunner", "def execute", "def _create_plan"],
        "Agent Runner has required methods"
    ))

    results.append(check_file_exists(
        base_path / "agent-system/backend/agent/migrations/0007_add_knowledge_fields.py",
        "Knowledge fields migration"
    ))

    results.append(check_file_contains(
        base_path / "agent-system/backend/agent/models.py",
        ["knowledge_status", "knowledge_last_extracted", "knowledge_docs_count"],
        "Repository model has knowledge fields"
    ))

    # Phase 2: Knowledge API Endpoints
    print(f"\n{Colors.BLUE}Phase 2: Knowledge API Endpoints{Colors.END}")
    print("-" * 60)

    results.append(check_file_contains(
        base_path / "agent-system/backend/agent/views.py",
        [
            "def extract_knowledge",
            "def knowledge_summary",
            "def knowledge_docs",
            "def knowledge_doc_detail",
            "def update_knowledge_doc"
        ],
        "Views has all 5 knowledge endpoints"
    ))

    # Phase 3: Socket Integration
    print(f"\n{Colors.BLUE}Phase 3: Socket Integration{Colors.END}")
    print("-" * 60)

    results.append(check_file_contains(
        base_path / "agent-system/backend/agent/consumers.py",
        ["class KnowledgeConsumer", "class AgentRunnerConsumer"],
        "Consumers has WebSocket handlers"
    ))

    results.append(check_file_contains(
        base_path / "agent-system/backend/agent/routing.py",
        ["ws/knowledge", "ws/agent"],
        "Routing has WebSocket routes"
    ))

    # Phase 4: Frontend UI
    print(f"\n{Colors.BLUE}Phase 4: Frontend UI{Colors.END}")
    print("-" * 60)

    results.append(check_file_exists(
        base_path / "agent-system/frontend/src/components/RepositoryKnowledge.vue",
        "Main Knowledge component"
    ))

    results.append(check_file_contains(
        base_path / "agent-system/frontend/src/components/RepositoryKnowledge.vue",
        ["connectWebSocket", "extractKnowledge", "loadKnowledgeSummary"],
        "Knowledge component has required methods"
    ))

    results.append(check_file_exists(
        base_path / "agent-system/frontend/src/components/knowledge/RepositoryProfileViewer.vue",
        "Repository Profile viewer"
    ))

    results.append(check_file_exists(
        base_path / "agent-system/frontend/src/components/knowledge/DomainModelViewer.vue",
        "Domain Model viewer"
    ))

    results.append(check_file_exists(
        base_path / "agent-system/frontend/src/components/knowledge/ConventionsList.vue",
        "Conventions List viewer"
    ))

    results.append(check_file_exists(
        base_path / "agent-system/frontend/src/components/knowledge/UsageGuidesList.vue",
        "Usage Guides viewer"
    ))

    # Phase 5: Testing
    print(f"\n{Colors.BLUE}Phase 5: Testing Infrastructure{Colors.END}")
    print("-" * 60)

    results.append(check_file_exists(
        base_path / "TESTING_MAXIMAL_AGENT.md",
        "Testing documentation"
    ))

    results.append(check_file_exists(
        base_path / "test_maximal_agent.py",
        "Automated test script"
    ))

    # Summary
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}Summary{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")

    passed = sum(1 for r in results if r)
    total = len(results)
    percentage = (passed / total * 100) if total > 0 else 0

    print(f"\nTests passed: {passed}/{total} ({percentage:.1f}%)")

    if passed == total:
        print(f"\n{Colors.GREEN}🎉 All verification checks passed!{Colors.END}")
        print(f"\n{Colors.BLUE}Next Steps:{Colors.END}")
        print("1. Start Django server: cd agent-system/backend && daphne -b 0.0.0.0 -p 8000 config.asgi:application")
        print("2. Run API tests from TESTING_MAXIMAL_AGENT.md")
        print("3. Test WebSocket connections")
        print("4. Integrate RepositoryKnowledge.vue into SystemDetail.vue")
        return 0
    else:
        print(f"\n{Colors.RED}⚠️  Some checks failed{Colors.END}")
        return 1

if __name__ == '__main__':
    exit(main())
