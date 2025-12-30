import sys
from pathlib import Path

CRS_ROOT = Path(__file__).resolve().parent / "agent-system" / "crs"
if str(CRS_ROOT) not in sys.path:
    sys.path.insert(0, str(CRS_ROOT))

from core.fs import WorkspaceFS
from core.query_api import CRSQueryAPI

fs = WorkspaceFS()
q = CRSQueryAPI(fs)

# Find all serializers
serializers = q.find_artifacts(type="drf_serializer", limit=200)
print(serializers)
# Trace a route

trace = q.trace_route_to_model("/api/v1/customer/")
print(trace)
models = q.find_artifacts(type="django_model", contains_name="customer", limit=20)
for m in models:
    print(m["name"], "->", m["file_path"])
from core.fs import WorkspaceFS
from core.query_runner import CRSQueryRunner

fs = WorkspaceFS()
qr = CRSQueryRunner(fs)

print(qr.load())
print(qr.find_models(contains="user"))
print(qr.find_endpoint_for_route("/api/users/"))
print(qr.find_routes_for_model("User"))
print(qr.search("customer"))
