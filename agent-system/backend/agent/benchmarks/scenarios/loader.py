from typing import List, Dict
from .definitions import BenchmarkScenario

class ScenarioLoader:
    """
    Registry/Loader for Benchmark Scenarios.
    """
    
    _REGISTRY: Dict[str, BenchmarkScenario] = {}
    
    @classmethod
    def register(cls, scenario: BenchmarkScenario):
        cls._REGISTRY[scenario.id] = scenario
        
    @classmethod
    def get(cls, scenario_id: str) -> BenchmarkScenario:
        if scenario_id not in cls._REGISTRY:
            raise KeyError(f"Scenario {scenario_id} not found")
        return cls._REGISTRY[scenario_id]

    @classmethod
    def list_all(cls) -> List[BenchmarkScenario]:
        return list(cls._REGISTRY.values())

# --- Define Built-in Scenarios Here or Import ---
# Example:
# ScenarioLoader.register(BenchmarkScenario(
#     id="basic_add_field",
#     title="Add Field to Model",
#     description="Add a new field to a Django model",
#     repository="auto-code-generator-v1",
#     instruction="Add a 'phone_number' field to the User model in user/models.py",
#     verification_suite={
#         "suites": [{
#             "id": "verify_phone_field",
#             "cases": [{"type": "file_exists", "file": "user/models.py", "grep": "phone_number"}]
#         }]
#     }
# ))
