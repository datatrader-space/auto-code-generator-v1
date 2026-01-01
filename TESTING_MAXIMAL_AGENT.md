# Maximal Agent Runner - Testing Guide

Comprehensive testing plan for the Maximal Agent Runner implementation.

## Prerequisites

1. **Database Setup**
   ```bash
   cd agent-system/backend
   python manage.py migrate agent
   ```
   Expected: Migration 0007_add_knowledge_fields should apply successfully

2. **Server Running**
   ```bash
   # Terminal 1: Django + Channels
   cd agent-system/backend
   daphne -b 0.0.0.0 -p 8000 config.asgi:application

   # Terminal 2: Frontend (if needed)
   cd agent-system/frontend
   npm run dev
   ```

---

## Test 1: Database Schema

**Verify knowledge fields were added:**

```bash
cd agent-system/backend
python manage.py shell
```

```python
from agent.models import Repository

# Check fields exist
repo = Repository.objects.first()
print(f"knowledge_status: {repo.knowledge_status}")
print(f"knowledge_last_extracted: {repo.knowledge_last_extracted}")
print(f"knowledge_docs_count: {repo.knowledge_docs_count}")

# Verify choices
print(Repository._meta.get_field('knowledge_status').choices)
# Should show: [('pending', 'Pending Extraction'), ('extracting', 'Extracting Knowledge'), ('ready', 'Knowledge Ready'), ('error', 'Extraction Error')]
```

**Expected Result:** ✅ All fields exist with correct defaults

---

## Test 2: Knowledge API Endpoints

### 2.1 Knowledge Summary (GET)

```bash
# Replace {system_id} and {repo_id} with actual IDs
curl http://localhost:8000/api/systems/1/repositories/1/knowledge/summary/
```

**Expected Response:**
```json
{
  "status": "pending",
  "last_extracted": null,
  "docs_count": 0,
  "profile": null,
  "docs_by_kind": {},
  "total_docs": 0
}
```

### 2.2 Extract Knowledge (POST)

**Prerequisites:** Repository must have CRS status = 'ready'

```bash
# First, check CRS status
curl http://localhost:8000/api/systems/1/repositories/1/crs/summary/

# If CRS is ready, extract knowledge
curl -X POST http://localhost:8000/api/systems/1/repositories/1/knowledge/extract/ \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

**Expected Response (if CRS ready):**
```json
{
  "status": "success",
  "knowledge_docs_created": 5,
  "duration_ms": 2340,
  "summary": {
    "architecture_style": "django_rest_framework",
    "domain": "agent_system",
    "entities_count": 12,
    "patterns_found": 0,
    "conventions_found": 1,
    "guides_created": 1
  }
}
```

**Expected Response (if CRS not ready):**
```json
{
  "error": "CRS must be ready before knowledge extraction",
  "crs_status": "not_started",
  "message": "Please run CRS pipeline first"
}
```

### 2.3 List Knowledge Documents (GET)

```bash
# All documents
curl http://localhost:8000/api/systems/1/repositories/1/knowledge/docs/

# Filter by kind
curl "http://localhost:8000/api/systems/1/repositories/1/knowledge/docs/?kind=domain_model"
```

**Expected Response:**
```json
{
  "docs": [
    {
      "kind": "repository_profile",
      "spec_id": "main",
      "description": "Repository profile for agent-system",
      "architecture": {...},
      "created_at": "2026-01-01T12:00:00Z"
    }
  ],
  "count": 5,
  "kind_filter": null
}
```

### 2.4 Get Specific Document (GET)

```bash
curl http://localhost:8000/api/systems/1/repositories/1/knowledge/docs/repository_profile/main/
```

**Expected Response:** Full document JSON with all fields

### 2.5 Update Document (PUT)

```bash
curl -X PUT http://localhost:8000/api/systems/1/repositories/1/knowledge/docs/repository_profile/main/ \
  -H "Content-Type: application/json" \
  -d '{
    "spec_id": "main",
    "description": "Updated description",
    "architecture": {
      "style": "django_rest_framework",
      "custom_note": "Added by user"
    }
  }'
```

**Expected Response:** Updated document with provenance:
```json
{
  "spec_id": "main",
  "description": "Updated description",
  "provenance": {
    "edited_by": "username",
    "edit_source": "user_ui",
    "edited_at": "2026-01-01T12:30:00Z"
  },
  ...
}
```

---

## Test 3: WebSocket Connections

### 3.1 Knowledge WebSocket

**Using wscat (install: `npm install -g wscat`):**

```bash
# Connect to knowledge WebSocket
wscat -c ws://localhost:8000/ws/knowledge/1/

# Send ping
> {"type": "ping"}
< {"type": "pong"}

# Start extraction (if CRS is ready)
> {"type": "start_extraction", "force": false}

# Watch for events:
< {"type": "knowledge_extraction_started", "repository_id": 1, ...}
< {"type": "knowledge_extraction_progress", "stage": "repository_profile", "message": "Analyzing..."}
< {"type": "knowledge_extraction_progress", "stage": "domain_model", "message": "Extracting entities..."}
< {"type": "knowledge_extraction_complete", "docs_created": 5, ...}
```

**Using Browser Console:**

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/knowledge/1/');

ws.onopen = () => {
  console.log('✅ Connected');
  ws.send(JSON.stringify({type: 'ping'}));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('📨 Event:', data);
};

ws.onerror = (error) => {
  console.error('❌ Error:', error);
};

// Start extraction
ws.send(JSON.stringify({type: 'start_extraction', force: true}));
```

### 3.2 Agent Runner WebSocket

```bash
# Connect to agent WebSocket
wscat -c ws://localhost:8000/ws/agent/1/

# Send ping
> {"type": "ping"}
< {"type": "pong"}

# Execute agent (placeholder - will implement later)
> {"type": "execute", "request": "List all Django models"}

# Watch for events:
< {"type": "agent_session_created", "session_id": "session_abc", ...}
< {"type": "agent_planning", "status": "analyzing_request", ...}
< {"type": "agent_step_start", "step_id": "step1", ...}
< {"type": "agent_step_complete", "step_id": "step1", "success": true, ...}
< {"type": "agent_session_complete", "status": "success", ...}
```

---

## Test 4: Knowledge Extraction Flow (End-to-End)

### Step 1: Ensure CRS is Ready

```bash
# Check CRS status
curl http://localhost:8000/api/systems/1/repositories/1/crs/summary/

# If not ready, run CRS pipeline
curl -X POST http://localhost:8000/api/systems/1/repositories/1/crs/run/ \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Step 2: Extract Knowledge

```bash
curl -X POST http://localhost:8000/api/systems/1/repositories/1/knowledge/extract/ \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

### Step 3: Verify Knowledge Created

```bash
# Check summary
curl http://localhost:8000/api/systems/1/repositories/1/knowledge/summary/ | jq

# Expected:
# {
#   "status": "ready",
#   "last_extracted": "2026-01-01T12:00:00Z",
#   "docs_count": 5,
#   "profile": {...},
#   "docs_by_kind": {
#     "repository_profile": 1,
#     "domain_model": 1,
#     "coding_convention": 1,
#     "usage_guide": 1
#   },
#   "total_docs": 5
# }
```

### Step 4: Verify Files Created

```bash
# Check state directory
ls -la agent-system/crs/state/specs/docs/

# Should see directories:
# - repository_profile/
# - domain_model/
# - coding_convention/
# - usage_guide/

# Check specific file
cat agent-system/crs/state/specs/docs/repository_profile/main.json | jq
```

---

## Test 5: Frontend Components (Browser)

### 5.1 Open Browser Console

Navigate to: `http://localhost:3000` (or wherever frontend is running)

### 5.2 Test WebSocket Connection

```javascript
// In browser console
const ws = new WebSocket('ws://localhost:8000/ws/knowledge/1/');

ws.onopen = () => console.log('✅ WebSocket connected');
ws.onmessage = (e) => console.log('📨', JSON.parse(e.data));
ws.onerror = (e) => console.error('❌', e);

// Send ping
ws.send(JSON.stringify({type: 'ping'}));
// Should receive: {"type": "pong"}
```

### 5.3 Test Component Rendering

If RepositoryKnowledge.vue is integrated into a page:

1. Navigate to repository detail page
2. Click "Knowledge" tab
3. Verify:
   - ✅ Status banner shows current status
   - ✅ "Extract Knowledge" button is visible
   - ✅ Empty state shows if no knowledge extracted

4. Click "Extract Knowledge"
5. Verify:
   - ✅ Progress events appear in real-time
   - ✅ Status changes to "Extracting..."
   - ✅ Events show stage-specific icons
   - ✅ Completion message appears
   - ✅ Status changes to "Ready"
   - ✅ Knowledge tabs appear

6. Click through tabs:
   - ✅ Profile tab shows architecture, tech stack
   - ✅ Domain Model tab shows entities
   - ✅ Conventions tab shows rules
   - ✅ Usage Guides tab shows steps

---

## Test 6: Error Handling

### 6.1 Extract Knowledge Without CRS

```bash
# On a repository with CRS status != 'ready'
curl -X POST http://localhost:8000/api/systems/1/repositories/1/knowledge/extract/ \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

**Expected:** HTTP 400 with error message about CRS not ready

### 6.2 Get Non-Existent Document

```bash
curl http://localhost:8000/api/systems/1/repositories/1/knowledge/docs/fake_kind/fake_id/
```

**Expected:** HTTP 404 with "Document not found" error

### 6.3 WebSocket with Invalid Message

```javascript
ws.send(JSON.stringify({type: 'invalid_type'}));
```

**Expected:** `{"type": "error", "error": "Unknown message type: invalid_type"}`

---

## Test 7: Database State Verification

```python
# In Django shell
from agent.models import Repository
from django.utils import timezone

repo = Repository.objects.get(id=1)

# After extraction
print(f"Status: {repo.knowledge_status}")  # Should be 'ready'
print(f"Last extracted: {repo.knowledge_last_extracted}")  # Should be recent timestamp
print(f"Docs count: {repo.knowledge_docs_count}")  # Should be > 0

# Verify status choices work
repo.knowledge_status = 'extracting'
repo.save()

repo.refresh_from_db()
assert repo.knowledge_status == 'extracting'

# Verify timestamp updates
repo.knowledge_last_extracted = timezone.now()
repo.save()

repo.refresh_from_db()
assert repo.knowledge_last_extracted is not None
```

---

## Test 8: Performance

### Measure Extraction Time

```bash
time curl -X POST http://localhost:8000/api/systems/1/repositories/1/knowledge/extract/ \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

**Expected:**
- Small repo (<100 artifacts): < 3 seconds
- Medium repo (100-500 artifacts): < 10 seconds
- Large repo (>500 artifacts): < 30 seconds

---

## Checklist Summary

- [ ] Database migration applied successfully
- [ ] Repository model has knowledge fields
- [ ] GET /knowledge/summary/ returns correct data
- [ ] POST /knowledge/extract/ triggers extraction
- [ ] GET /knowledge/docs/ lists documents
- [ ] GET /knowledge/docs/{kind}/{id}/ returns document
- [ ] PUT /knowledge/docs/{kind}/{id}/ updates document
- [ ] WebSocket connects to ws://localhost:8000/ws/knowledge/{id}/
- [ ] WebSocket ping/pong works
- [ ] WebSocket extraction events stream correctly
- [ ] Knowledge files created in state/specs/docs/
- [ ] Frontend components render without errors
- [ ] Real-time progress updates in UI
- [ ] Error handling works correctly
- [ ] Performance is acceptable

---

## Debugging Tips

### Check Django Logs

```bash
# Watch server logs
tail -f agent-system/backend/logs/django.log
```

### Check WebSocket Connection Issues

```bash
# Verify Django Channels is running
ps aux | grep daphne

# Check if WebSocket route is registered
cd agent-system/backend
python manage.py shell
>>> from agent.routing import websocket_urlpatterns
>>> print(websocket_urlpatterns)
```

### Check CRS State Files

```bash
# Verify CRS workspace exists
ls -la agent-system/crs/state/

# Check artifacts exist
cat agent-system/crs/state/artifacts.json | jq '.artifacts | length'

# Check relationships exist
cat agent-system/crs/state/relationships.json | jq '.relationships | length'
```

### Python Import Errors

```python
# In Django shell
from agent.services.knowledge_agent import RepositoryKnowledgeAgent
from agent.services.agent_runner import AgentRunner
from core.spec_store import SpecStore

# Should import without errors
```

---

## Next Steps After Testing

1. **If all tests pass:** Integration into SystemDetail.vue
2. **If tests fail:** Check error logs and debug
3. **Performance issues:** Optimize knowledge extraction
4. **Missing features:** Implement Agent Runner execution UI

---

## Quick Test Script

Save as `test_knowledge.sh`:

```bash
#!/bin/bash

echo "🧪 Testing Maximal Agent Runner"
echo "================================"

SYSTEM_ID=1
REPO_ID=1
BASE_URL="http://localhost:8000"

echo ""
echo "1️⃣ Testing Knowledge Summary..."
curl -s "${BASE_URL}/api/systems/${SYSTEM_ID}/repositories/${REPO_ID}/knowledge/summary/" | jq -r '.status'

echo ""
echo "2️⃣ Testing Knowledge Extraction..."
curl -s -X POST "${BASE_URL}/api/systems/${SYSTEM_ID}/repositories/${REPO_ID}/knowledge/extract/" \
  -H "Content-Type: application/json" \
  -d '{"force": true}' | jq -r '.status'

echo ""
echo "3️⃣ Testing Knowledge Documents..."
curl -s "${BASE_URL}/api/systems/${SYSTEM_ID}/repositories/${REPO_ID}/knowledge/docs/" | jq -r '.count'

echo ""
echo "✅ Tests complete!"
```

Run with: `bash test_knowledge.sh`
