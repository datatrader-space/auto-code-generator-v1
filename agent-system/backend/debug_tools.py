import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from agent.tools.registry import get_tool_registry

registry = get_tool_registry()
tools = registry.get_all_tools()

print("--- Registered Tools ---")
for name, meta in tools.items():
    print(f"{name} ({meta.category}) - Enabled: {meta.enabled}")

if "LIST_ARTIFACTS" in tools and "GET_ARTIFACT" in tools:
    print("\nSUCCESS: CRS Tools are registered!")
else:
    print("\nFAILURE: CRS Tools missing.")
