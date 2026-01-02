import os
import django
from unittest.mock import MagicMock, patch
import sys

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# Add CRS core path
crs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../crs'))
sys.path.append(crs_path)

print(f"DEBUG: sys.path includes: {sys.path}")
print(f"DEBUG: crs_path: {crs_path}")

print("DEBUG: Setting Django Settings...")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
try:
    print("DEBUG: Calling django.setup()...")
    django.setup()
    print("DEBUG: django.setup() success.")
except Exception as e:
    print(f"CRITICAL DJANGO SETUP ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("DEBUG: Attempting to import AgentRunner...")
try:
    from agent.services.agent_runner import AgentRunner
    print("DEBUG: AgentRunner imported successfully.")
    
    print("DEBUG: Attempting to import CRSQueryAPI...")
    from core.query_api import CRSQueryAPI # Import to ensure it exists for patch
    print("DEBUG: CRSQueryAPI imported successfully.")
except ImportError as e:
    with open('error.txt', 'w') as f:
        f.write(f"CRITICAL IMPORT ERROR: {e}\n")
        import traceback
        traceback.print_exc(file=f)
    sys.exit(1)
except Exception as e:
    with open('error.txt', 'w') as f:
        f.write(f"CRITICAL UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc(file=f)
    sys.exit(1)

# Create mock artifacts from user's JSON data
MOCK_ARTIFACTS = [
    {
        'name': 'AccountCreationJob', 
        'type': 'django_model', 
        'file_path': 'creator/models.py', 
        'description': 'class AccountCreationJob(models.Model)...'
    },
    {
        'name': 'AccountCreationJobViewSet', 
        'type': 'drf_viewset', 
        'file_path': 'creator/views.py', 
        'description': 'class AccountCreationJobViewSet(viewsets.ModelViewSet)...'
    },
    {
        'name': 'account-jobs route', 
        'type': 'django_url', 
        'file_path': 'creator/urls.py', 
        'description': "router.register(r'account-jobs', views.AccountCreationJobViewSet, basename='accountjob')"
    },
    # Noise artifacts to test ranking
    {
        'name': 'OtherModel', 
        'type': 'django_model', 
        'file_path': 'creator/models.py', 
        'description': 'class OtherModel...'
    },
    {
        'name': 'SomeUtility', 
        'type': 'function', 
        'file_path': 'utils.py', 
        'description': 'def utility()...'
    }
]

def verify_rag():
    print("Verifying RAG Logic with Mock Artifacts...")
    
    with patch('core.query_api.CRSQueryAPI') as MockCRS:
        instance = MockCRS.return_value
        instance.find_artifacts.return_value = MOCK_ARTIFACTS
        
        # Initialize Runner
        runner = AgentRunner("dummy_root", "dummy_config")
        
        with patch('core.fs.WorkspaceFS'):
            # Patch LLM Router to capture the prompt
            with patch('agent.services.agent_runner.llm.router.get_llm_router') as mock_get_router:
                mock_llm = MagicMock()
                mock_get_router.return_value = mock_llm
                mock_llm.query.return_value = "Mock Answer"
                
                # Execute Query
                query = "Where are the API routes for the AccountCreationJob model?"
                print(f"Query: {query}")
                runner._execute_query(query)
                
                # Analyze calls
                if mock_llm.query.called:
                    args, kwargs = mock_llm.query.call_args
                    prompt = args[0] if args else kwargs.get('prompt', '')
                    
                    print("\n--- LLM PROMPT ANALYSIS ---")
                    
                    # Check for critical keywords in the prompt context
                    has_url = "creator/urls.py" in prompt and "account-jobs" in prompt
                    has_view = "creator/views.py" in prompt and "AccountCreationJobViewSet" in prompt
                    
                    if has_url:
                        print("SUCCESS: Context contains 'creator/urls.py' and 'account-jobs' route!")
                    else:
                        print("FAILURE: Context is MISSING the URL route info.")
                        
                    if has_view:
                        print("SUCCESS: Context contains 'creator/views.py' and ViewSet!")
                    else:
                        print("FAILURE: Context is MISSING the ViewSet info.")
                    
                    print("\n--- CONTEXT SNIPPET SENT TO LLM ---")
                    start_marker = "Context (Codebase Artifacts):"
                    start = prompt.find(start_marker)
                    if start != -1:
                        print(prompt[start:start+1000])
                    else:
                        print("Could not find context marker in prompt.")
                else:
                     print("FAILURE: LLM `query` was not called.")

if __name__ == "__main__":
    verify_rag()
