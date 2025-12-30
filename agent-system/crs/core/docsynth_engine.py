# core/docsynth_engine.py
import os
import time
import json
from typing import Any, Dict, Optional

from core.fs import WorkspaceFS
from core.llm_client import LocalLLMClient
from core.agent_memory import AgentMemoryStore


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class DocSynthEngine:
    """
    Builds AI-first conceptual documentation for the whole CRS codebase.
    Output is machine-operational concepts, not human prose.
    """

    VERSION = "crs-docsynth-v1"

    def __init__(self, fs: WorkspaceFS, llm: LocalLLMClient, agent_id: str = "default"):
        self.fs = fs
        self.llm = llm
        self.mem = AgentMemoryStore(fs, agent_id=agent_id)

    def run(self, *, run_id: Optional[str] = None, reason: str = "init") -> Dict[str, Any]:
        artifacts = self.fs.read_json(self.fs.paths.artifacts_json)
        rels = self.fs.read_json(self.fs.paths.relationships_json)

        # keep prompt small: agent can iterate later
        msg = [
            {
                "role": "system",
                "content": (
                    "You are a CRS documentation synthesizer. "
                    "Return STRICT JSON only. No prose. "
                    "Goal: produce machine-operational conceptual docs."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "synthesize_concepts",
                        "version": self.VERSION,
                        "inputs": {
                            "artifacts_summary_only": True,
                            "artifact_count": len(artifacts.get("artifacts", [])) if isinstance(artifacts, dict) else None,
                            "relationship_count": len(rels.get("relationships", [])) if isinstance(rels, dict) else None,
                            "artifact_types": list({a.get("type") for a in (artifacts.get("artifacts") or []) if isinstance(a, dict)}),
                            "relationship_types": list({r.get("type") for r in (rels.get("relationships") or []) if isinstance(r, dict)}),
                        },
                        "output_schema": {
                            "concepts": "list[{id,name,purpose,inputs,outputs,links}]",
                            "flows": "list[{id,name,steps,preconditions,postconditions}]",
                            "invariants": "list[{id,statement,why_it_matters,how_to_verify,linked_types}]",
                            "interfaces": "list[{id,name,call_signature,input_types,output_types,examples}]",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        text = self.llm.chat(msg)
        payload = json.loads(text) if isinstance(text, str) else {"raw": str(text)}

        out_dir = os.path.join(self.fs.paths.state_dir, "knowledge")
        self.fs.backend.makedirs(out_dir)

        snap_id = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        out_path = os.path.join(out_dir, f"docsynth_{snap_id}.json")
        self.fs.write_json(out_path, payload)

        self.mem.append_event(
            {
                "type": "docsynth_completed",
                "reason": reason,
                "snapshot_path": out_path,
                "run_id": run_id,
            }
        )

        if run_id:
            self.fs.write_run_json(run_id, "docsynth.json", {"snapshot_path": out_path})

        return {"ok": True, "snapshot_path": out_path, "payload_keys": list(payload.keys()) if isinstance(payload, dict) else []}
