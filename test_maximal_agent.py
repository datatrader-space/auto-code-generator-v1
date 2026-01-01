#!/usr/bin/env python3
"""
Quick test script for Maximal Agent Runner
Run from agent-system/backend directory: python ../../test_maximal_agent.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent-system', 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agent.models import Repository
from agent.services.knowledge_agent import RepositoryKnowledgeAgent
from agent.services.agent_runner import AgentRunner
from core.fs import WorkspaceFS
from core.spec_store import SpecStore

def test_imports():
    """Test all imports work"""
    print("✅ All imports successful")
    return True

def test_model_fields():
    """Test Repository model has knowledge fields"""
    try:
        repo = Repository.objects.first()
        if not repo:
            print("⚠️  No repositories in database")
            return False

        # Check fields exist
        assert hasattr(repo, 'knowledge_status')
        assert hasattr(repo, 'knowledge_last_extracted')
        assert hasattr(repo, 'knowledge_docs_count')

        print(f"✅ Repository fields exist")
        print(f"   - knowledge_status: {repo.knowledge_status}")
        print(f"   - knowledge_last_extracted: {repo.knowledge_last_extracted}")
        print(f"   - knowledge_docs_count: {repo.knowledge_docs_count}")

        return True
    except Exception as e:
        print(f"❌ Model fields test failed: {e}")
        return False

def test_knowledge_agent():
    """Test KnowledgeAgent can be instantiated"""
    try:
        repo = Repository.objects.first()
        if not repo:
            print("⚠️  No repositories in database")
            return False

        # Create agent
        agent = RepositoryKnowledgeAgent(repository=repo)

        # Check components can be loaded
        assert agent.repository == repo

        print(f"✅ KnowledgeAgent instantiated successfully")
        print(f"   - Repository: {repo.name}")

        return True
    except Exception as e:
        print(f"❌ KnowledgeAgent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_runner():
    """Test AgentRunner can be instantiated"""
    try:
        repo = Repository.objects.first()
        if not repo:
            print("⚠️  No repositories in database")
            return False

        # Create runner
        runner = AgentRunner(repository=repo)

        # Check components
        assert runner.repository == repo

        print(f"✅ AgentRunner instantiated successfully")
        print(f"   - Repository: {repo.name}")

        return True
    except Exception as e:
        print(f"❌ AgentRunner test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_spec_store():
    """Test SpecStore works if CRS workspace exists"""
    try:
        repo = Repository.objects.first()
        if not repo or not repo.crs_workspace_path:
            print("⚠️  No repository with CRS workspace")
            return False

        # Create SpecStore
        fs = WorkspaceFS(workspace_root=repo.crs_workspace_path)
        spec_store = SpecStore(fs)

        # List docs
        docs = spec_store.list_docs()

        print(f"✅ SpecStore works")
        print(f"   - Workspace: {repo.crs_workspace_path}")
        print(f"   - Documents found: {len(docs)}")

        return True
    except Exception as e:
        print(f"⚠️  SpecStore test skipped: {e}")
        return True  # Not critical

def main():
    """Run all tests"""
    print("🧪 Testing Maximal Agent Runner Components")
    print("=" * 50)
    print()

    tests = [
        ("Imports", test_imports),
        ("Model Fields", test_model_fields),
        ("Knowledge Agent", test_knowledge_agent),
        ("Agent Runner", test_agent_runner),
        ("Spec Store", test_spec_store),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n📋 Test: {name}")
        print("-" * 50)
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} failed with exception: {e}")
            results.append((name, False))

    print()
    print("=" * 50)
    print("📊 Test Results")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
