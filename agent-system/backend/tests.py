#!/usr/bin/env python
"""
API Test Script - Pure Python
Tests all API endpoints without curl/Postman

Run:
    python test_api.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from agent.models import System, Repository, RepositoryQuestion
from rest_framework.test import APIClient
import json

User = get_user_model()


class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'


def print_section(title):
    print(f"\n{Colors.BLUE}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{Colors.END}\n")


def print_success(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")


def print_error(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.END}")


def print_info(msg):
    print(f"{Colors.YELLOW}ℹ️  {msg}{Colors.END}")


def test_api():
    """Test all API endpoints"""
    
    print_section("🧪 CRS Agent API Test Suite")
    
    # Create test user
    print_info("Setting up test user...")
    user, created = User.objects.get_or_create(
        username='apitest',
        defaults={'email': 'test@example.com'}
    )
    if created:
        user.set_password('test123')
        user.save()
        print_success("Created test user: apitest")
    else:
        print_success("Using existing user: apitest")
    
    # Create API client
    client = APIClient()
    client.force_authenticate(user=user)
    
    # Test results
    results = {
        'passed': 0,
        'failed': 0,
        'errors': []
    }
    
    # ==========================================
    # Test 1: API Root
    # ==========================================
    print_section("Test 1: API Root")
    try:
        response = client.get('/api/')
        assert response.status_code == 200
        data = response.json()
        print_success("API Root accessible")
        print(f"   Version: {data.get('version')}")
        print(f"   Endpoints: {list(data.get('endpoints', {}).keys())}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('API Root', str(e)))
    
    # ==========================================
    # Test 2: LLM Health
    # ==========================================
    print_section("Test 2: LLM Health Check")
    try:
        response = client.get('/api/llm/health/')
        assert response.status_code == 200
        data = response.json()
        print_success("LLM Health check working")
        print(f"   Local: {data.get('local', {}).get('available', False)}")
        print(f"   Cloud: {data.get('cloud', {}).get('available', False)}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('LLM Health', str(e)))
    
    # ==========================================
    # Test 3: Create System
    # ==========================================
    print_section("Test 3: Create System")
    try:
        response = client.post('/api/systems/', {
            'name': 'API Test System',
            'description': 'Testing the REST API'
        }, format='json')
        assert response.status_code == 201
        system_data = response.json()
        system_id = system_data['id']
        print_success("System created")
        print(f"   ID: {system_id}")
        print(f"   Name: {system_data['name']}")
        print(f"   Status: {system_data['status']}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('Create System', str(e)))
        return results
    
    # ==========================================
    # Test 4: List Systems
    # ==========================================
    print_section("Test 4: List Systems")
    try:
        response = client.get('/api/systems/')
        assert response.status_code == 200
        data = response.json()
        print_success(f"Found {data['count']} systems")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('List Systems', str(e)))
    
    # ==========================================
    # Test 5: Get System Detail
    # ==========================================
    print_section("Test 5: Get System Detail")
    try:
        response = client.get(f'/api/systems/{system_id}/')
        assert response.status_code == 200
        data = response.json()
        print_success("System detail retrieved")
        print(f"   Repositories: {len(data['repositories'])}")
        print(f"   Knowledge: {data['knowledge_count']}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('System Detail', str(e)))
    
    # ==========================================
    # Test 6: Add Repository
    # ==========================================
    print_section("Test 6: Add Repository")
    try:
        response = client.post(f'/api/systems/{system_id}/repositories/', {
            'name': 'test-worker',
            'github_url': 'https://github.com/test/worker',
            'github_branch': 'main'
        }, format='json')
        assert response.status_code == 201
        repo_data = response.json()
        repo_id = repo_data['id']
        print_success("Repository added")
        print(f"   ID: {repo_id}")
        print(f"   Name: {repo_data['name']}")
        print(f"   Status: {repo_data['status']}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('Add Repository', str(e)))
        return results
    
    # ==========================================
    # Test 7: Analyze Repository
    # ==========================================
    print_section("Test 7: Analyze Repository")
    try:
        response = client.post(
            f'/api/systems/{system_id}/repositories/{repo_id}/analyze/',
            {'force': False},
            format='json'
        )
        assert response.status_code == 200
        data = response.json()
        print_success("Analysis completed")
        print(f"   Message: {data.get('message')}")
        print(f"   Questions: {data.get('questions_count', 0)}")
        if 'analysis' in data and data['analysis']:
            print(f"   Paradigm: {data['analysis'].get('paradigm', 'unknown')}")
            print(f"   Confidence: {data['analysis'].get('confidence', 0):.0%}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('Analyze Repository', str(e)))
    
    # ==========================================
    # Test 8: Get Questions
    # ==========================================
    print_section("Test 8: Get Questions")
    try:
        response = client.get(
            f'/api/systems/{system_id}/repositories/{repo_id}/questions/'
        )
        assert response.status_code == 200
        data = response.json()
        print_success(f"Retrieved {data['count']} questions")
        print(f"   Answered: {data['answered']}")
        if data['questions']:
            first_q = data['questions'][0]
            print(f"   First question: {first_q['question_text'][:50]}...")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('Get Questions', str(e)))
    
    # ==========================================
    # Test 9: Submit Answers
    # ==========================================
    print_section("Test 9: Submit Answers")
    try:
        # Get questions first
        repo = Repository.objects.get(id=repo_id)
        questions = repo.questions.all()
        
        # Build mock answers
        answers = {}
        for q in questions[:5]:  # Answer first 5 questions
            if q.question_type == 'yes_no':
                answers[q.question_key] = 'yes'
            elif q.question_type == 'multiple_choice' and q.options:
                answers[q.question_key] = q.options[0]
            elif q.question_type == 'text':
                answers[q.question_key] = 'test answer'
        
        response = client.post(
            f'/api/systems/{system_id}/repositories/{repo_id}/submit_answers/',
            {'answers': answers},
            format='json'
        )
        assert response.status_code == 200
        data = response.json()
        print_success("Answers submitted")
        print(f"   Message: {data.get('message')}")
        print(f"   Config: {data.get('config', {}).get('paradigm', 'N/A')}")
        print(f"   Knowledge items: {data.get('knowledge_items', 0)}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('Submit Answers', str(e)))
    
    # ==========================================
    # Test 10: Get Knowledge
    # ==========================================
    print_section("Test 10: Get System Knowledge")
    try:
        response = client.get(f'/api/systems/{system_id}/knowledge/')
        assert response.status_code == 200
        data = response.json()
        print_success(f"Retrieved {data['count']} knowledge items")
        if data['results']:
            for item in data['results'][:3]:
                print(f"   - {item['knowledge_type']}: {item['spec_id']}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('Get Knowledge', str(e)))
    
    # ==========================================
    # Test 11: Create Task
    # ==========================================
    print_section("Test 11: Create Task")
    try:
        response = client.post(f'/api/systems/{system_id}/tasks/', {
            'description': 'Test task: Rename a field',
            'requires_approval': True
        }, format='json')
        assert response.status_code == 201
        task_data = response.json()
        print_success("Task created")
        print(f"   ID: {task_data['id']}")
        print(f"   Status: {task_data['status']}")
        print(f"   Requires approval: {task_data['requires_approval']}")
        results['passed'] += 1
    except Exception as e:
        print_error(f"Failed: {e}")
        results['failed'] += 1
        results['errors'].append(('Create Task', str(e)))
    
    # ==========================================
    # Summary
    # ==========================================
    print_section("📊 Test Results")
    
    total = results['passed'] + results['failed']
    print(f"Total tests: {total}")
    print_success(f"Passed: {results['passed']}")
    
    if results['failed'] > 0:
        print_error(f"Failed: {results['failed']}")
        print("\nFailed tests:")
        for test_name, error in results['errors']:
            print(f"  ❌ {test_name}: {error}")
    
    print_section("✅ API Test Complete!")
    
    if results['failed'] == 0:
        print_success("All tests passed! API is ready for frontend development!")
        return True
    else:
        print_error("Some tests failed. Check errors above.")
        return False


if __name__ == '__main__':
    try:
        success = test_api()
        sys.exit(0 if success else 1)
    except Exception as e:
        print_error(f"Test suite error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)