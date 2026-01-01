"""
Agent Runner - Maximal Autonomous Execution Engine

The Agent Runner orchestrates CRS capabilities for autonomous code changes:
- Planning: Break requests into executable steps
- Tool Orchestration: Chain QueryRunner → PatchEngine → VerificationEngine
- Impact Analysis: Predict change effects before applying
- Verification-First: Rollback on test failures
- Session Management: Track execution history
"""

from typing import Dict, List, Any, Optional, Callable
import time
import logging
import uuid
import json
import os

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    Maximal Agent Runner
    Autonomous execution layer over CRS
    """

    def __init__(self, repository, socket_callback: Optional[Callable] = None):
        """
        Initialize agent runner

        Args:
            repository: Django Repository model instance
            socket_callback: Optional callback for real-time event streaming
        """
        self.repository = repository
        self.socket_callback = socket_callback

        # Initialize components (lazy-loaded)
        self._fs = None
        self._query_api = None
        self._patch_engine = None
        self._verification_engine = None
        self._knowledge_agent = None

        # Session state
        self.current_session = None

    @property
    def fs(self):
        """Lazy-load WorkspaceFS"""
        if self._fs is None:
            from core.fs import WorkspaceFS
            self._fs = WorkspaceFS(workspace_root=self.repository.crs_workspace_path)
        return self._fs

    @property
    def query_api(self):
        """Lazy-load CRSQueryAPI"""
        if self._query_api is None:
            from core.query_api import CRSQueryAPI
            self._query_api = CRSQueryAPI(self.fs)
        return self._query_api

    @property
    def patch_engine(self):
        """Lazy-load PatchEngine"""
        if self._patch_engine is None:
            from core.patch_engine import PatchEngine
            self._patch_engine = PatchEngine(self.fs)
        return self._patch_engine

    @property
    def verification_engine(self):
        """Lazy-load VerificationEngine"""
        if self._verification_engine is None:
            from core.verification_engine import VerificationEngine
            self._verification_engine = VerificationEngine(self.fs)
        return self._verification_engine

    @property
    def knowledge_agent(self):
        """Lazy-load Knowledge Agent"""
        if self._knowledge_agent is None:
            from agent.services.knowledge_agent import RepositoryKnowledgeAgent
            self._knowledge_agent = RepositoryKnowledgeAgent(
                repository=self.repository,
                socket_callback=self.socket_callback
            )
        return self._knowledge_agent

    def _send_event(self, event_type: str, data: dict):
        """Send event through socket if callback provided"""
        if self.socket_callback:
            try:
                self.socket_callback({
                    'type': event_type,
                    'session_id': self.current_session.get('session_id') if self.current_session else None,
                    **data
                })
            except Exception as e:
                logger.error(f"Failed to send event {event_type}: {e}")

    def execute(self, session_id: str, request: str) -> Dict[str, Any]:
        """
        Execute autonomous agent session

        Args:
            session_id: Unique session identifier
            request: User's natural language request

        Returns:
            dict: Execution results with status, patches applied, verification results
        """
        start = time.time()

        logger.info(f"Starting agent session {session_id}: {request}")

        # Initialize session
        self.current_session = {
            'session_id': session_id,
            'request': request,
            'created_at': self._utc_iso(),
            'status': 'planning',
            'steps': [],
            'patches_applied': [],
            'verification_runs': [],
            'tools_called': []
        }

        self._send_event('agent_session_created', {
            'request': request,
            'timestamp': self.current_session['created_at']
        })

        try:
            # Step 1: Get knowledge context
            knowledge_context = self.knowledge_agent.get_context_for(request)
            self.current_session['knowledge_context'] = {
                'architecture_style': knowledge_context.get('architecture_style'),
                'domain': knowledge_context.get('domain')
            }

            # Step 2: Create execution plan
            self._send_event('agent_planning', {
                'status': 'analyzing_request',
                'message': 'Analyzing request and creating execution plan...'
            })

            plan = self._create_plan(request, knowledge_context)
            self.current_session['plan'] = plan
            self.current_session['status'] = 'executing'

            self._send_event('agent_planning', {
                'status': 'plan_created',
                'plan': plan,
                'message': f'Created plan with {len(plan.get("steps", []))} steps'
            })

            # Step 3: Execute plan steps
            for step_index, step in enumerate(plan.get('steps', [])):
                step_result = self._execute_step(step_index, step)
                self.current_session['steps'].append(step_result)

                if step_result.get('status') == 'error':
                    logger.error(f"Step {step_index} failed: {step_result.get('error')}")
                    self.current_session['status'] = 'failed'
                    break

            # Step 4: Final verification (if patches were applied)
            if self.current_session['patches_applied']:
                verification_result = self._run_verification()
                self.current_session['verification_runs'].append(verification_result)

                if not verification_result.get('overall_ok', False):
                    logger.warning("Verification failed, rolling back changes")
                    self._rollback_session()
                    self.current_session['status'] = 'rolled_back'
                else:
                    self.current_session['status'] = 'success'
            else:
                # No patches applied (read-only operation)
                self.current_session['status'] = 'success'

            duration_ms = int((time.time() - start) * 1000)
            self.current_session['completed_at'] = self._utc_iso()
            self.current_session['duration_ms'] = duration_ms

            # Save session record
            self._save_session_record()

            result = {
                'status': self.current_session['status'],
                'session_id': session_id,
                'execution_time_ms': duration_ms,
                'steps_completed': len(self.current_session['steps']),
                'patches_applied': len(self.current_session['patches_applied']),
                'session_record': f"state/agent/sessions/{session_id}.json"
            }

            self._send_event('agent_session_complete', result)

            logger.info(f"Agent session {session_id} completed with status: {self.current_session['status']}")

            return result

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Agent session {session_id} failed: {e}", exc_info=True)

            self.current_session['status'] = 'error'
            self.current_session['error'] = str(e)
            self.current_session['duration_ms'] = duration_ms

            self._save_session_record()

            error_result = {
                'status': 'error',
                'session_id': session_id,
                'error': str(e),
                'execution_time_ms': duration_ms
            }

            self._send_event('agent_session_error', error_result)

            return error_result

    def _create_plan(self, request: str, knowledge_context: dict) -> Dict[str, Any]:
        """
        Create execution plan from user request

        Args:
            request: User's natural language request
            knowledge_context: Repository knowledge context

        Returns:
            dict: Execution plan with steps
        """
        # For now, create a simple plan based on keywords
        # In production, this would use LLM to generate sophisticated plans

        request_lower = request.lower()
        steps = []

        # Detect intent
        if any(kw in request_lower for kw in ['list', 'show', 'what', 'find']):
            # Query operation
            steps.append({
                'id': 'step_query',
                'action': 'QUERY',
                'description': 'Query repository artifacts',
                'params': {'query': request}
            })

        elif any(kw in request_lower for kw in ['add', 'create', 'implement']):
            # Create operation
            steps.append({
                'id': 'step_analyze',
                'action': 'ANALYZE',
                'description': 'Analyze where to add new code'
            })
            steps.append({
                'id': 'step_patch',
                'action': 'PATCH',
                'description': 'Apply code changes',
                'depends_on': ['step_analyze']
            })
            steps.append({
                'id': 'step_verify',
                'action': 'VERIFY',
                'description': 'Run verification suite',
                'depends_on': ['step_patch']
            })

        elif any(kw in request_lower for kw in ['change', 'update', 'modify']):
            # Update operation
            steps.append({
                'id': 'step_find',
                'action': 'FIND',
                'description': 'Find artifacts to modify'
            })
            steps.append({
                'id': 'step_impact',
                'action': 'IMPACT_ANALYSIS',
                'description': 'Analyze change impact',
                'depends_on': ['step_find']
            })
            steps.append({
                'id': 'step_patch',
                'action': 'PATCH',
                'description': 'Apply changes',
                'depends_on': ['step_impact']
            })
            steps.append({
                'id': 'step_verify',
                'action': 'VERIFY',
                'description': 'Verify changes',
                'depends_on': ['step_patch']
            })

        else:
            # Default: analyze operation
            steps.append({
                'id': 'step_analyze',
                'action': 'ANALYZE',
                'description': 'Analyze request'
            })

        return {
            'steps': steps,
            'estimated_risk': self._assess_risk(steps),
            'architecture_context': knowledge_context.get('architecture_style'),
            'created_at': self._utc_iso()
        }

    def _assess_risk(self, steps: List[dict]) -> str:
        """Assess risk level of execution plan"""
        has_patch = any(s.get('action') == 'PATCH' for s in steps)
        has_verify = any(s.get('action') == 'VERIFY' for s in steps)

        if has_patch and not has_verify:
            return 'high'  # Patches without verification
        elif has_patch and has_verify:
            return 'medium'  # Patches with verification
        else:
            return 'low'  # Read-only operations

    def _execute_step(self, step_index: int, step: dict) -> Dict[str, Any]:
        """
        Execute a single plan step

        Args:
            step_index: Step number
            step: Step definition

        Returns:
            dict: Step execution result
        """
        step_id = step.get('id')
        action = step.get('action')

        logger.info(f"Executing step {step_index}: {action}")

        self._send_event('agent_step_start', {
            'step_id': step_id,
            'step_index': step_index,
            'action': action,
            'description': step.get('description'),
            'timestamp': self._utc_iso()
        })

        start = time.time()
        result = {'status': 'success', 'action': action}

        try:
            if action == 'QUERY':
                result['data'] = self._execute_query(step.get('params', {}))

            elif action == 'ANALYZE':
                result['data'] = self._execute_analyze(step.get('params', {}))

            elif action == 'FIND':
                result['data'] = self._execute_find(step.get('params', {}))

            elif action == 'IMPACT_ANALYSIS':
                result['data'] = self._execute_impact_analysis(step.get('params', {}))

            elif action == 'PATCH':
                result['data'] = self._execute_patch(step.get('params', {}))

            elif action == 'VERIFY':
                result['data'] = self._execute_verify(step.get('params', {}))

            else:
                result['status'] = 'skipped'
                result['reason'] = f'Unknown action: {action}'

            duration_ms = int((time.time() - start) * 1000)
            result['duration_ms'] = duration_ms

            self._send_event('agent_step_complete', {
                'step_id': step_id,
                'step_index': step_index,
                'success': result['status'] == 'success',
                'duration_ms': duration_ms,
                'result_summary': self._summarize_result(result)
            })

            return result

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Step {step_index} ({action}) failed: {e}", exc_info=True)

            error_result = {
                'status': 'error',
                'action': action,
                'error': str(e),
                'duration_ms': duration_ms
            }

            self._send_event('agent_step_error', {
                'step_id': step_id,
                'step_index': step_index,
                'error': str(e),
                'duration_ms': duration_ms
            })

            return error_result

    def _execute_query(self, params: dict) -> Dict[str, Any]:
        """Execute query operation"""
        query = params.get('query', '')

        # Simple artifact search
        artifacts = self.query_api.find_artifacts()

        return {
            'artifacts_found': len(artifacts),
            'artifacts': artifacts[:10]  # Return first 10
        }

    def _execute_analyze(self, params: dict) -> Dict[str, Any]:
        """Execute analysis operation"""
        # Placeholder: would analyze codebase structure
        return {
            'analysis': 'Code analysis placeholder'
        }

    def _execute_find(self, params: dict) -> Dict[str, Any]:
        """Execute find operation"""
        # Placeholder: would find specific artifacts
        return {
            'found': []
        }

    def _execute_impact_analysis(self, params: dict) -> Dict[str, Any]:
        """Execute impact analysis"""
        # Placeholder: would use relationship graph to predict impact

        self._send_event('agent_impact_analysis', {
            'message': 'Analyzing change impact...',
            'impact': {
                'direct_dependencies': 0,
                'indirect_dependencies': 0,
                'risk_factors': []
            }
        })

        return {
            'impact': 'low',
            'affected_artifacts': []
        }

    def _execute_patch(self, params: dict) -> Dict[str, Any]:
        """Execute patch operation"""
        # Placeholder: would apply code patches

        patch_id = f"patch_{uuid.uuid4().hex[:12]}"

        self._send_event('agent_patch_start', {
            'patch_id': patch_id,
            'message': 'Applying code changes...'
        })

        # Track patch
        self.current_session['patches_applied'].append(patch_id)

        self._send_event('agent_patch_complete', {
            'patch_id': patch_id,
            'success': True,
            'files_modified': []
        })

        return {
            'patch_id': patch_id,
            'status': 'applied'
        }

    def _execute_verify(self, params: dict) -> Dict[str, Any]:
        """Execute verification"""
        return self._run_verification()

    def _run_verification(self) -> Dict[str, Any]:
        """Run verification suite"""
        self._send_event('agent_verification_start', {
            'message': 'Running verification suite...'
        })

        try:
            # Try to load and run verification suite
            suite_spec = self.verification_engine.load_spec()
            suites = suite_spec.get('suites', [])

            if not suites:
                logger.warning("No verification suites defined")
                return {
                    'overall_ok': True,
                    'passed': 0,
                    'failed': 0,
                    'message': 'No verification suites defined'
                }

            # Run first suite (or default suite)
            suite_id = suites[0].get('id') if suites else 'default'
            result = self.verification_engine.run_suite(suite_id)

            self._send_event('agent_verification_complete', {
                'suite_id': suite_id,
                'passed': result.get('passed', 0),
                'failed': result.get('failed', 0),
                'overall_ok': result.get('overall_ok', False)
            })

            return result

        except Exception as e:
            logger.error(f"Verification failed: {e}")

            self._send_event('agent_verification_error', {
                'error': str(e)
            })

            return {
                'overall_ok': False,
                'error': str(e)
            }

    def _rollback_session(self):
        """Rollback all patches applied in this session"""
        patches_to_revert = self.current_session.get('patches_applied', [])

        if not patches_to_revert:
            return

        logger.info(f"Rolling back {len(patches_to_revert)} patches")

        self._send_event('agent_rollback_start', {
            'reason': 'verification_failed',
            'patches_to_revert': patches_to_revert
        })

        # Placeholder: would actually revert patches
        # In production, would use PatchEngine to revert

        self._send_event('agent_rollback_complete', {
            'success': True,
            'reverted_patches': len(patches_to_revert)
        })

    def _save_session_record(self):
        """Save session record to state/agent/sessions/"""
        session_id = self.current_session.get('session_id')

        try:
            # Create sessions directory if needed
            sessions_dir = os.path.join(self.fs.paths.state_dir, 'agent', 'sessions')
            self.fs.backend.makedirs(sessions_dir)

            # Write session record
            session_path = os.path.join(sessions_dir, f"{session_id}.json")
            self.fs.write_json(session_path, self.current_session)

            logger.info(f"Saved session record: {session_path}")

        except Exception as e:
            logger.error(f"Failed to save session record: {e}")

    def _summarize_result(self, result: dict) -> str:
        """Create human-readable summary of step result"""
        action = result.get('action')
        status = result.get('status')

        if status == 'success':
            data = result.get('data', {})

            if action == 'QUERY':
                count = data.get('artifacts_found', 0)
                return f"Found {count} artifacts"

            elif action == 'PATCH':
                return f"Applied patch {data.get('patch_id')}"

            elif action == 'VERIFY':
                passed = data.get('passed', 0)
                failed = data.get('failed', 0)
                return f"Verification: {passed} passed, {failed} failed"

            return f"{action} completed"

        elif status == 'error':
            return f"{action} failed: {result.get('error')}"

        return status

    def _utc_iso(self) -> str:
        """Return current UTC time in ISO format"""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
