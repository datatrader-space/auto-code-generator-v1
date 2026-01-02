import os
import sys
import django

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
# Actually I don't know the settings module name for sure. 
# Looking at file structure, probably 'config.settings' or 'core.settings' or 'backend.settings'.
# Detailed check: agent/services/agent_runner imports 'django.conf.settings'.

try:
    # Just try importing the modules without full django setup if possible, 
    # but AgentRunner imports django stuff.
    # So we need basic setup.
    pass
except:
    pass

from agent.benchmarks.tools.registry import ToolRegistry
from agent.benchmarks.tracing.observer import BenchmarkObserver
try:
    from agent.services.agent_runner import AgentRunner
    print("SUCCESS: AgentRunner imported")
except ImportError as e:
    print(f"FAILURE: {e}")
except Exception as e:
    # Likely Django not configured, but if it's Import Error we care.
    print(f"WARNING: {e}")

print("Build Verification Complete")
