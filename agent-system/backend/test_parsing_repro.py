
import os
import sys
import django

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import json
from agent.crs_tools import CRSTools
class MockRepo:
    pass

def test_parsing():
    try:
        tools = CRSTools(repository=MockRepo())
    except Exception as e:
        print(f"Error initializing CRSTools: {e}")
        return

    # User's reported failing output (approximate)
    failing_output = """
Alright, let's break down how to determine the relevant API routes for the AccountCreationJob model.

...

1. First, list all models:
```json
{ "name": "LIST_ARTIFACTS", "parameters": { "kind": "django_model" } }
```

Once you have this information...
"""

    print("--- Testing Failing Output ---")
    calls = tools.parse_tool_calls(failing_output)
    print(f"Found {len(calls)} calls. Result: {calls}")
    
    if not calls:
        print("FAIL: Parser missed the tool call.")
    else:
        print("SUCCESS: Parser found the tool call.")

    # Standard expected output
    standard_output = """
===TOOL_CALLS===
[{"name":"LIST_ARTIFACTS","parameters":{"kind":"django_model"}}]
===END_TOOL_CALLS===
"""
    print("\n--- Testing Standard Output ---")
    calls = tools.parse_tool_calls(standard_output)
    print(f"Found {len(calls)} calls.")

if __name__ == "__main__":
    test_parsing()
