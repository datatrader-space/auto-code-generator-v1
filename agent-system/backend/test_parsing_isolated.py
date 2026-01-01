
import json
import re
import logging
from typing import List, Dict, Any

# Mock logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class CRSToolsMock:
    def parse_tool_calls(self, llm_response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response using strict JSON protocol OR markdown blocks
        
        Supported formats:
        1. Strict: ===TOOL_CALLS=== [...] ===END_TOOL_CALLS===
        2. Markdown: ```json [...] ``` or ```json {...} ```
        """
        tools = []
        
        # 1. Try strict parsing first
        pattern = r'===TOOL_CALLS===\s*(\[.*?\])\s*===END_TOOL_CALLS==='
        match = re.search(pattern, llm_response, re.DOTALL)

        if match:
            json_str = match.group(1).strip()
            tools = self._parse_json_safe(json_str)
        else:
            # 2. Try markdown code blocks
            # Look for JSON blocks
            md_pattern = r'```json\s*(.*?)\s*```'
            matches = re.findall(md_pattern, llm_response, re.DOTALL)
            
            for m in matches:
                parsed_items = self._parse_json_safe(m)
                if parsed_items:
                    tools.extend(parsed_items)

        if not tools:
            logger.debug("No tool calls found in response")
            return []

        # Validate structure
        validated = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue

            if 'name' not in tool:
                continue

            # Basic heuristic to avoid confusing normal JSON with tool calls
            # Tool calls usually have "name" (req) and "parameters" (opt)
            # If it has unexpected keys like "file_path" or "type" it might just be data
            
            validated.append({
                'name': tool['name'].upper(),
                'parameters': tool.get('parameters', {})
            })

        logger.info(f"Parsed {len(validated)} valid tool calls: {[t['name'] for t in validated]}")
        return validated

    def _parse_json_safe(self, json_str: str) -> List[Dict[str, Any]]:
        """Helper to parse JSON string into a list of dicts"""
        try:
            data = json.loads(json_str)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Handle single object case
                return [data]
            return []
        except json.JSONDecodeError:
            return []

def test_parsing():
    print("Initializing isolated mock tools...")
    tools = CRSToolsMock()
    
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
    print(f"Result: {calls}")
    
    if len(calls) == 1 and calls[0]['name'] == 'LIST_ARTIFACTS':
        print("SUCCESS: Parser found the tool call.")
    else:
        print("FAIL: Parser missed the tool call.")

    # Standard expected output
    standard_output = """
===TOOL_CALLS===
[{"name":"LIST_ARTIFACTS","parameters":{"kind":"django_model"}}]
===END_TOOL_CALLS===
"""
    print("\n--- Testing Standard Output ---")
    calls = tools.parse_tool_calls(standard_output)
    print(f"Result: {calls}")
    if len(calls) == 1 and calls[0]['name'] == 'LIST_ARTIFACTS':
        print("SUCCESS: Standard output parsed correctly.")
    else:
        print("FAIL: Standard output failed.")

if __name__ == "__main__":
    test_parsing()
