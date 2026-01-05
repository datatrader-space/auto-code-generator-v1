"""
Agent Runner - Maximal Autonomous Execution Engine
"""

from typing import Dict, List, Any, Optional, Callable
import time
import logging
import uuid
import json
import os
from pathlib import Path

# Core Imports
from core.pipeline_state import PipelineState
from agent.benchmarks.tools.registry import ToolRegistry
from agent.benchmarks.tracing.observer import BenchmarkObserver

# Lazy imports for core engines are handled in properties

logger = logging.getLogger(__name__)

class AgentRunner:
    """
    Maximal Agent Runner with Mode Support (CRS vs Direct)
    """

    def __init__(self, repository, socket_callback: Optional[Callable] = None):
        self.repository = repository
        self.socket_callback = socket_callback
        
        # Components
        self._fs = None
        self._patch_engine = None
        self._verification_engine = None
        
        # State
        self.current_session = None

    @property
    def fs(self):
        if self._fs is None:
            if not self.repository:
                return None
                
            from core.fs import WorkspaceFS
            from django.conf import settings
            repo_root = Path(settings.BASE_DIR).parents[1]
            # Use standard CRS workspace path construction
            crs_workspace_path = (
                repo_root / "crs_workspaces"
                / str(self.repository.system.user_id)
                / str(self.repository.system_id)
                / f"{self.repository.name}_crs"
            )
            config_path = crs_workspace_path / 'config.json'
            self._fs = WorkspaceFS(config_path=str(config_path))
        return self._fs

    @property
    def patch_engine(self):
        if self._patch_engine is None:
            from core.patch_engine import PatchEngine
            self._patch_engine = PatchEngine(self.fs)
        return self._patch_engine

    @property
    def verification_engine(self):
        if self._verification_engine is None:
            from core.verification_engine import VerificationEngine
            self._verification_engine = VerificationEngine(self.fs)
        return self._verification_engine

    def _send_event(self, event_type: str, data: dict):
        """Send event through socket if callback provided"""
        if self.socket_callback and self.current_session:
            try:
                self.socket_callback({
                    'type': event_type,
                    'session_id': self.current_session.get('session_id'),
                    **data
                })
            except Exception as e:
                logger.error(f"Failed to send event {event_type}: {e}")

    def execute(self, session_id: str, request: str, mode: str = "crs", model_config: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute autonomous session with specific mode
        """
        start_time = time.time()
        logger.info(f"Starting agent session {session_id} [{mode}]: {request}")
        
        # 1. Initialize Observer
        observer = BenchmarkObserver(
            scenario_id="manual", 
            strategy=mode,
            trace_id=session_id
        )
        
        # 2. Get ToolSet
        try:
            if self.repository:
                 toolset = ToolRegistry.get(mode, self.repository)
            else:
                 # For repository-less agents, use built-in tool registry
                 from agent.tools.registry import get_tool_registry
                 self.tool_registry = get_tool_registry()
                 toolset = None  # We'll use tool_registry directly instead of toolset
        except Exception as e:
            logger.error(f"Failed to load tools: {e}")
            return {'status': 'error', 'error': f"Failed to load tools: {e}"}

        # 3. Session State (Backward Compatibility Fields)
        self.current_session = {
            'session_id': session_id,
            'mode': mode,
            'status': 'running',
            'request': request,
            'created_at': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            'plan': {'steps': [{'id': 'react_loop', 'description': 'Autonomous Reasoning Loop'}]}, # Dummy plan
            'steps': [],
            'patches_applied': [],
            'verification_runs': [],
            'tools_called': []
        }
        
        self._send_event('agent_session_created', {
            'request': request,
            'timestamp': self.current_session['created_at']
        })

        # 4. Planning / Execution Loop (ReAct)
        final_status = "success"
        
        try:
            # Initial Prompt
            if toolset:
                system_prompt = toolset.get_system_prompt()
            elif hasattr(self, 'tool_registry'):
                system_prompt = self.tool_registry.generate_prompt_documentation()
            else:
                system_prompt = "You are a helpful AI assistant."
            # Removed hardcoded PATCH/VERIFY actions - those are code-specific
            
            logger.info(f"[AGENT INIT] System Prompt:\n{system_prompt}\n--- END SYSTEM PROMPT ---")
            
            history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request}
            ]
            
            self._send_event('agent_planning', {
                'status': 'analyzing_request',
                'message': 'Thinking...'
            })
            
            steps_limit = 20
            
            for step_i in range(steps_limit):
                # Ask LLM
                observer.log("THOUGHT", {"step": step_i, "history_len": len(history)})
                
                # Notify UI we are thinking
                self._send_event('agent_planning', {'status': 'thinking', 'step': step_i})
                
                response = self._ask_llm(history, model_config)
                logger.info(f"[AGENT STEP {step_i}] LLM Full Response:\n{response}\n--- END RESPONSE ---")
                history.append({"role": "assistant", "content": response})
                
                # Parse Tools
                if toolset:
                    tool_calls = toolset.parse_tool_calls(response)
                    logger.info(f"[AGENT STEP {step_i}] Parsed {len(tool_calls)} tool calls (using toolset)")
                else:
                    # Simple parsing for repository-less agents - support both JSON and function-call formats
                    import json, re
                    tool_calls = []
                    
                    # 1. Try to find JSON blocks using brace counting (handles nested dicts)
                    cursor = 0
                    while True:
                        start_brace = response.find('{', cursor)
                        if start_brace == -1:
                            break
                        
                        depth = 0
                        end_brace = -1
                        for i in range(start_brace, len(response)):
                            if response[i] == '{':
                                depth += 1
                            elif response[i] == '}':
                                depth -= 1
                                if depth == 0:
                                    end_brace = i
                                    break
                        
                        if end_brace != -1:
                            json_str = response[start_brace:end_brace+1]
                            try:
                                call = json.loads(json_str)
                                # Normalize keys
                                tool_name = call.get('tool') or call.get('name') or call.get('action') or call.get('function')
                                params = call.get('parameters') or call.get('arguments') or call.get('params') or call.get('args') or {}
                                
                                if tool_name and isinstance(tool_name, str):
                                    normalized_call = {'name': tool_name, 'parameters': params}
                                    tool_calls.append(normalized_call)
                                    logger.info(f"[AGENT STEP {step_i}] Parsed JSON tool call: {normalized_call}")
                            except Exception as e:
                                logger.warning(f"[AGENT STEP {step_i}] Failed to parse JSON: {json_str[:100]}..., error: {e}")
                            cursor = end_brace + 1
                        else:
                            cursor = start_brace + 1
                    
                    # 2. Key-value function search Fallback: TOOL_NAME(key="val") OR TOOL_NAME("val", "val")
                    if not tool_calls:
                        func_pattern = r'([A-Z_]+)\((.*?)\)'
                        func_matches = re.findall(func_pattern, response, re.DOTALL)
                        logger.info(f"[AGENT STEP {step_i}] Found {len(func_matches)} function-call matches")
                        for tool_name, params_str in func_matches:
                            if tool_name in ["JSON", "TOOL", "CALL"]: continue # Skip false positives
                            
                            try:
                                param_dict = {}
                                # Try key="value"
                                kv_pairs = list(re.finditer(r'(\w+)=["\'](.*?)["\']', params_str))
                                if kv_pairs:
                                    for param_match in kv_pairs:
                                        param_dict[param_match.group(1)] = param_match.group(2)
                                
                                # Fallback: Positional args "val1", "val2"
                                elif params_str.strip():
                                     parts = [p.strip().strip('"').strip("'") for p in params_str.split(',')]
                                     if tool_name in ['WRITE_FILE', 'CREATE_FILE'] and len(parts) >= 1:
                                          param_dict = {'path': parts[0], 'content': parts[1] if len(parts) > 1 else ''}
                                     elif tool_name == 'READ_FILE' and len(parts) >= 1:
                                          param_dict = {'path': parts[0]}
                                
                                if param_dict or (not params_str.strip()):
                                    tool_call = {'name': tool_name, 'parameters': param_dict}
                                    tool_calls.append(tool_call)
                                    logger.info(f"[AGENT STEP {step_i}] Parsed function-call: {tool_call}")
                            except Exception as e:
                                logger.warning(f"[AGENT STEP {step_i}] Failed to parse function call: {tool_name}({params_str}), error: {e}")
                    
                    logger.info(f"[AGENT STEP {step_i}] Final parsed {len(tool_calls)} tool calls: {tool_calls}")
                observer.log("TOOL_CALLS", tool_calls)
                
                if not tool_calls:
                    if "DONE" in response or "I have completed" in response:
                        logger.info("Agent signaled completion")
                        break
                    if step_i > 0 and len(response) > 50:
                        # Assume conversational answer if no tools
                        break
                    continue
                    
                # Execute Tools
                for tool in tool_calls:
                    name = tool['name'].upper()
                    params = tool['parameters']
                    result_str = ""
                    action_type = name 
                    
                    # Notify UI step start
                    step_id = f"step_{step_i}_{uuid.uuid4().hex[:4]}"
                    self._send_event('agent_step_start', {
                        'step_id': step_id,
                        'step_index': step_i,
                        'action': name,
                        'description': f"Running {name}",
                        'timestamp': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                    
                    step_record = {
                        'id': step_id,
                        'action': name,
                        'params': params,
                        'status': 'success'
                    }

                    try:
                        if name == 'PATCH':
                            # Core Action: Patch
                            res = self._execute_patch(params)
                            result_str = json.dumps(res)
                            if res.get('status') == 'applied':
                                self.current_session['patches_applied'].append(res.get('patch_id'))
                                observer.log("PATCH_APPLIED", res)
                                self._send_event('agent_patch_complete', {'patch_id': res.get('patch_id'), 'success': True})
                            
                            step_record['data'] = res
                                
                        elif name == 'VERIFY':
                            # Core Action: Verify
                            res = self._run_verification()
                            result_str = json.dumps(res)
                            self.current_session['verification_runs'].append(res)
                            observer.log("VERIFICATION", res)
                            
                            step_record['data'] = res
                                
                        else:
                            # ToolSet Action
                            logger.info(f"[TOOL EXEC] Executing {name} with params: {params}")
                            if toolset:
                                result_str = toolset.execute_tool(name, params)
                                logger.info(f"[TOOL EXEC] {name} result: {result_str[:200]}...")
                            else:
                                # Use tool_registry for repository-less agents
                                logger.info(f"[TOOL EXEC] Using tool_registry for {name}")
                                from agent.tools.base import ToolExecutionContext, ToolPermission
                                
                                # Determine workspace path
                                workspace_path = "/tmp"
                                if self.repository and hasattr(self.repository, 'get_workspace_path'):
                                    workspace_path = self.repository.get_workspace_path()
                                elif self.repository and hasattr(self.repository, 'workspace'):
                                    workspace_path = self.repository.workspace.root_path
                                elif self.current_session and 'workspace_path' in self.current_session:
                                    workspace_path = self.current_session['workspace_path']

                                context = ToolExecutionContext(
                                    repository=self.repository if self.repository else None,
                                    user=None, # user not easily available in this context yet
                                    session_id=session_id if session_id else "unknown_session",
                                    workspace_path=workspace_path,
                                    permissions=[ToolPermission.READ, ToolPermission.WRITE, ToolPermission.EXECUTE],
                                    trace=[]
                                )
                                result = self.tool_registry.execute(name, params, context)
                                result_str = result.output if result.success else f"Error: {result.error}"
                                logger.info(f"[TOOL EXEC] {name} result success={result.success}: {result_str[:200]}...")
                            step_record['data'] = {'output': result_str[:200] + '...'} # Summary for UI
                            
                    except Exception as e:
                        logger.error(f"Tool {name} failed: {e}", exc_info=True)
                        result_str = f"Error: {e}"
                        step_record['status'] = 'error'
                        step_record['error'] = str(e)
                        self._send_event('agent_step_error', {'step_id': step_id, 'error': str(e)})

                    # Add result to history
                    history.append({
                        "role": "user", 
                        "content": f"Tool '{name}' Result: {result_str}"
                    })
                    observer.log("TOOL_RESULT", {"name": name, "result": result_str[:1000]}) # truncate log
                    
                    # Notify UI step complete
                    self._send_event('agent_step_complete', {
                        'step_id': step_id, 
                        'success': step_record['status'] == 'success',
                        'result_summary': result_str[:100]
                    })
                    
                    # Update Session State
                    self.current_session['steps'].append(step_record)
            
            # Finalize
            self.current_session['status'] = 'success'
            observer.finish({"status": "complete"})
            
        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            observer.log("ERROR", str(e))
            final_status = "error"
            self.current_session['status'] = 'error'
            self.current_session['error'] = str(e)
            self._send_event('agent_session_error', {'error': str(e)})
            
        # Save Trace
        try:
            if self.fs:
                state_dir = self.fs.paths.state_dir
                trace_path = observer.save(os.path.join(state_dir, 'traces'))
            else:
                trace_path = "" # No persistence for free agents yet
        except Exception as e:
            logger.error(f"Failed to save trace: {e}")
            trace_path = ""
        
        # Send Completion Event
        self._send_event('agent_session_complete', {
             'status': self.current_session['status'],
             'session_id': session_id,
             'execution_time_ms': int((time.time() - start_time) * 1000)
        })

        return {
            'status': final_status,
            'session_id': session_id,
            'trace_path': trace_path,
            'patches_applied': self.current_session['patches_applied'],
            'verification_runs': self.current_session['verification_runs']
        }

    def _execute_patch(self, params: dict) -> Dict[str, Any]:
        """Apply patch using PatchEngine"""
        try:
            payload = params
            # Ensure 'changes' key exists or try to wrap
            if 'changes' not in payload:
                 return {'status': 'error', 'error': "Invalid patch: missing 'changes' list."}

            state = PipelineState(self.fs)
            record = self.patch_engine.apply_patch(self.fs, state, payload)
            
            return {'status': 'applied', 'patch_id': record['patch_id']}
            
        except Exception as e:
            logger.error(f"Patch failed: {e}")
            return {'status': 'error', 'error': str(e)}

    def _run_verification(self) -> Dict[str, Any]:
        """Run verification using VerificationEngine"""
        try:
            spec = self.verification_engine.load_spec()
            suites = spec.get('suites', [])
            
            if not suites:
                return {'ok': True, 'message': 'No suites defined (skipped)'}
                
            # Run the first suite found
            suite_id = suites[0].get('id')
            res = self.verification_engine.run_suite(suite_id)
            return res
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return {'ok': False, 'error': str(e)}

    def _ask_llm(self, messages: List[Dict], model_config: Optional[Dict] = None) -> str:
        try:
            from llm.router import get_llm_router, LLMConfig
            router = get_llm_router()
            
            client = None
            if model_config:
                # Assuming model_config matches LLMConfig definition
                config = LLMConfig(**model_config)
                client = router.client_for_config(config)
            
            if client:
                response = client.query(messages)
            else:
                response = router.query(messages=messages)
                
            return response.get('content', '')
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return f"Error: {e}"
