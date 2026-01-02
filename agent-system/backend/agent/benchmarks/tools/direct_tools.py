import os
import re
from typing import List, Dict, Any
from pathlib import Path
from .base import AbstractToolSet

class DirectToolSet(AbstractToolSet):
    """
    Standard File System Tools. 
    Simulates a developer without CRS/Semantic capabilities.
    """
    
    def __init__(self, repository):
        self.repository = repository
        self.root = Path(repository.clone_path) if repository.clone_path else None

    def get_system_prompt(self) -> str:
        return """
# Available Standard Tools

You are a Standard Coding Agent. You perform tasks by manually exploring the file system.
You DO NOT have access to a Knowledge Graph or Semantic Search.

## Tool Call Format
```json
===TOOL_CALLS===
[{"name": "TOOL_NAME", "parameters": {"param": "value"}}]
===END_TOOL_CALLS===
```

## Tools

### 1. LIST_FILES
- **Purpose**: List files in a directory (recursive up to depth).
- **Parameters**: 
  - `path` (optional): relative path to list (default root).
  - `depth` (optional): max depth (default 2).
- **Returns**: List of file paths.

### 2. READ_FILE
- **Purpose**: Read file content.
- **Parameters**:
  - `path` (required): relative path.
- **Returns**: File content.

### 3. FIND_TEXT
- **Purpose**: Grep for text in files.
- **Parameters**:
  - `pattern` (required): text/regex to find.
  - `path` (optional): path to search in (default root).
- **Returns**: Matching lines with line numbers.

## Strategy
1. Use `LIST_FILES` to explore the structure.
2. Use `FIND_TEXT` to locate relevant code.
3. Use `READ_FILE` to understand logic.
"""

    def parse_tool_calls(self, llm_response: str) -> List[Dict[str, Any]]:
        # Reuse the logic from CRSTools or implement simple JSON extraction
        # For simplicity, implementing a basic extractor here
        import json
        pattern = r'===TOOL_CALLS===\s*(\[.*?\])\s*===END_TOOL_CALLS==='
        match = re.search(pattern, llm_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        
        # Fallback markdown
        md_pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(md_pattern, llm_response, re.DOTALL)
        tools = []
        for m in matches:
            try:
                data = json.loads(m)
                if isinstance(data, list): tools.extend(data)
                elif isinstance(data, dict): tools.append(data)
            except: pass
        return tools

    def execute_tool(self, name: str, params: Dict[str, Any]) -> str:
        if not self.root or not self.root.exists():
            return "❌ Repository not available (not cloned?)"
            
        name = name.upper()
        
        try:
            if name == 'LIST_FILES':
                return self._list_files(params.get('path', '.'), int(params.get('depth', 2)))
            elif name == 'READ_FILE':
                return self._read_file(params.get('path', ''))
            elif name == 'FIND_TEXT':
                return self._find_text(params.get('pattern', ''), params.get('path', '.'))
            else:
                return f"❌ Unknown tool: {name}"
        except Exception as e:
            return f"❌ Error executing {name}: {str(e)}"

    def _list_files(self, rel_path: str, depth: int) -> str:
        target = (self.root / rel_path).resolve()
        if not str(target).startswith(str(self.root)):
            return "❌ Access Denied: Path outside repo"
            
        if not target.exists():
            return f"❌ Path not found: {rel_path}"
            
        files = []
        for root, dirs, filenames in os.walk(target):
            current_depth = root[len(str(target)):].count(os.sep)
            if current_depth >= depth:
                dirs[:] = [] # Stop recursion
                continue
                
            for f in filenames:
                full = Path(root) / f
                rel = full.relative_to(self.root)
                files.append(str(rel))
                
        return f"📂 Files in {rel_path}:\n" + "\n".join(files[:100]) + ("\n... (truncated)" if len(files) > 100 else "")

    def _read_file(self, rel_path: str) -> str:
        target = (self.root / rel_path).resolve()
        if not str(target).startswith(str(self.root)) or not target.exists():
            return f"❌ File not found: {rel_path}"
            
        try:
            content = target.read_text(encoding='utf-8', errors='ignore')
            lines = content.splitlines()
            numbered = [f"{i+1:4d} | {l}" for i, l in enumerate(lines)]
            return f"📄 **{rel_path}**\n```\n" + "\n".join(numbered) + "\n```"
        except Exception as e:
            return f"❌ Error reading: {e}"

    def _find_text(self, pattern: str, rel_path: str) -> str:
        target = (self.root / rel_path).resolve()
        results = []
        try:
            # Simple grep simulation
            import fnmatch
            for root, _, files in os.walk(target):
                for fname in files:
                    if fname.endswith(('.py', '.js', '.ts', '.vue', '.html', '.css', '.md', '.json')):
                        fpath = Path(root) / fname
                        try:
                            lines = fpath.read_text(encoding='utf-8', errors='ignore').splitlines()
                            for i, line in enumerate(lines):
                                if pattern in line:
                                    rel = fpath.relative_to(self.root)
                                    results.append(f"{rel}:{i+1}: {line.strip()}")
                        except: pass
                        if len(results) > 50: break
                if len(results) > 50: break
                
            if not results: return f"🔍 No matches for '{pattern}'"
            return f"🔍 Matches for '{pattern}':\n" + "\n".join(results[:50])
        except Exception as e:
            return f"❌ Search error: {e}"
