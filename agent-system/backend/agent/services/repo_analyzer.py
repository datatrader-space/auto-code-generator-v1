# agent/services/repo_analyzer.py
"""
Repository Analyzer - Uses LLM to understand repository structure

This is the CORE of Phase 1: LLM analyzes repos WITHOUT CRS,
then generates questions for the user to answer.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from llm.router import get_llm_router

logger = logging.getLogger(__name__)


@dataclass
class FileTreeNode:
    """Represents a file/directory in the tree"""
    name: str
    type: str  # 'file' or 'dir'
    path: str
    children: List['FileTreeNode'] = None
    size: Optional[int] = None


class RepositoryAnalyzer:
    """
    Analyzes repository structure using LLM
    
    Flow:
    1. Build file tree
    2. Sample key files
    3. Ask LLM to analyze structure
    4. Return analysis + confidence
    """
    
    def __init__(self):
        self.llm = get_llm_router()
        
        # Files to always include in analysis
        self.KEY_FILES = [
            'requirements.txt',
            'pyproject.toml', 
            'setup.py',
            'Dockerfile',
            'docker-compose.yml',
            'README.md',
            'manage.py',  # Django
            'settings.py',  # Django
            'wsgi.py',  # Django
            'celery.py',  # Celery
            'app.py',  # Flask
            'main.py',  # FastAPI/general
            'config.py',
            '__init__.py'
        ]
        
        # Directories to scan
        self.SCAN_DIRS = [
            'src',
            'app',
            'services',
            'handlers',
            'models',
            'views',
            'api',
            'tasks',
            'workers',
            'core',
            'lib',
            'utils'
        ]
        
        # Max files to sample (to stay within token limits)
        self.MAX_SAMPLE_FILES = 15
        self.MAX_FILE_SIZE = 10000  # chars
    
    def analyze(self, repo_path: str, repo_name: str) -> Dict[str, Any]:
        """
        Analyze repository structure
        
        Args:
            repo_path: Path to cloned repository
            repo_name: Repository name (for context)
            
        Returns:
            {
                "paradigm": "django|services|fastapi|celery|other",
                "patterns": ["class-based", "function-based"],
                "key_concepts": ["model", "service", "handler"],
                "dependencies": ["django", "celery", "requests"],
                "file_tree": {...},
                "sample_files": {...},
                "can_use_standard_crs": true|false,
                "confidence": 0.95,
                "uncertainty": ["questions for user"],
                "llm_reasoning": "..."
            }
        """
        
        logger.info(f"Analyzing repository: {repo_name} at {repo_path}")
        
        # 1. Build file tree
        file_tree = self._build_file_tree(repo_path)
        
        # 2. Sample key files
        sample_files = self._sample_files(repo_path)
        
        # 3. Analyze dependencies
        dependencies = self._extract_dependencies(repo_path)
        
        # 4. Ask LLM to analyze
        analysis = self._llm_analyze(
            repo_name=repo_name,
            file_tree=file_tree,
            sample_files=sample_files,
            dependencies=dependencies
        )
        
        # 5. Add metadata
        analysis['file_tree'] = file_tree
        analysis['sample_files'] = sample_files
        analysis['dependencies'] = dependencies
        
        return analysis
    
    def _build_file_tree(self, repo_path: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Build simplified file tree
        
        Returns:
            {
                "root": "/path/to/repo",
                "structure": {
                    "services/": ["order_service.py", "payment_service.py"],
                    "models/": ["order.py", "customer.py"],
                    ...
                }
            }
        """
        
        structure = {}
        repo_root = Path(repo_path)
        
        def scan_dir(dir_path: Path, depth: int = 0):
            if depth > max_depth:
                return
            
            try:
                for item in dir_path.iterdir():
                    # Skip hidden, venv, node_modules, etc
                    if item.name.startswith('.') or item.name in ['venv', 'node_modules', '__pycache__', 'dist', 'build']:
                        continue
                    
                    rel_path = str(item.relative_to(repo_root))
                    
                    if item.is_dir():
                        # Scan if it's an interesting directory
                        if depth == 0 or item.name in self.SCAN_DIRS:
                            structure[rel_path + '/'] = []
                            scan_dir(item, depth + 1)
                    else:
                        # Add file to parent dir
                        parent = str(item.parent.relative_to(repo_root))
                        if parent == '.':
                            parent = ''
                        else:
                            parent += '/'
                        
                        if parent not in structure:
                            structure[parent] = []
                        structure[parent].append(item.name)
            
            except PermissionError:
                pass
        
        scan_dir(repo_root)
        
        return {
            "root": str(repo_root),
            "structure": structure
        }
    
    def _sample_files(self, repo_path: str) -> Dict[str, str]:
        """
        Sample key files for analysis
        
        Returns:
            {
                "requirements.txt": "django==4.2\ncelery==5.3\n...",
                "services/order_service.py": "class OrderService:\n    ...",
                ...
            }
        """
        
        samples = {}
        repo_root = Path(repo_path)
        
        # 1. Always include key files
        for key_file in self.KEY_FILES:
            file_path = repo_root / key_file
            if file_path.exists() and file_path.is_file():
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    if len(content) <= self.MAX_FILE_SIZE:
                        samples[key_file] = content
                    else:
                        samples[key_file] = content[:self.MAX_FILE_SIZE] + "\n... (truncated)"
                except Exception as e:
                    logger.warning(f"Failed to read {key_file}: {e}")
        
        # 2. Sample files from interesting directories
        sampled_count = len(samples)
        
        for scan_dir in self.SCAN_DIRS:
            if sampled_count >= self.MAX_SAMPLE_FILES:
                break
            
            dir_path = repo_root / scan_dir
            if not dir_path.exists():
                continue
            
            # Sample up to 2 Python files from each directory
            try:
                py_files = list(dir_path.glob('*.py'))[:2]
                for py_file in py_files:
                    if sampled_count >= self.MAX_SAMPLE_FILES:
                        break
                    
                    try:
                        content = py_file.read_text(encoding='utf-8', errors='ignore')
                        rel_path = str(py_file.relative_to(repo_root))
                        
                        if len(content) <= self.MAX_FILE_SIZE:
                            samples[rel_path] = content
                        else:
                            samples[rel_path] = content[:self.MAX_FILE_SIZE] + "\n... (truncated)"
                        
                        sampled_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to read {py_file}: {e}")
            except Exception as e:
                logger.warning(f"Failed to scan {scan_dir}: {e}")
        
        return samples
    
    def _extract_dependencies(self, repo_path: str) -> List[str]:
        """
        Extract Python dependencies
        
        Returns:
            ["django", "celery", "requests", ...]
        """
        
        dependencies = []
        repo_root = Path(repo_path)
        
        # Check requirements.txt
        req_file = repo_root / 'requirements.txt'
        if req_file.exists():
            try:
                content = req_file.read_text()
                for line in content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Extract package name (before ==, >=, etc)
                        pkg = line.split('==')[0].split('>=')[0].split('<=')[0].strip()
                        if pkg:
                            dependencies.append(pkg)
            except Exception as e:
                logger.warning(f"Failed to parse requirements.txt: {e}")
        
        # Check pyproject.toml
        pyproject = repo_root / 'pyproject.toml'
        if pyproject.exists():
            try:
                import toml
                data = toml.load(pyproject)
                deps = data.get('project', {}).get('dependencies', [])
                for dep in deps:
                    pkg = dep.split('==')[0].split('>=')[0].strip()
                    if pkg not in dependencies:
                        dependencies.append(pkg)
            except Exception as e:
                logger.warning(f"Failed to parse pyproject.toml: {e}")
        
        return dependencies
    
    def _llm_analyze(
        self,
        repo_name: str,
        file_tree: Dict,
        sample_files: Dict[str, str],
        dependencies: List[str]
    ) -> Dict[str, Any]:
        """
        Use LLM to analyze repository structure
        
        This is where the magic happens!
        """
        
        # Build prompt
        prompt = self._build_analysis_prompt(
            repo_name=repo_name,
            file_tree=file_tree,
            sample_files=sample_files,
            dependencies=dependencies
        )
        
        # Query LLM (try local first, fallback to cloud)
        try:
            response = self.llm.query(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing Python codebases. "
                                   "You understand Django, FastAPI, Celery, service architectures, and more. "
                                   "Return ONLY valid JSON, no markdown formatting."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                json_mode=True,
                provider=None  # Auto-routing
            )
            
            # Parse JSON response
            analysis = self.llm.parse_json_response(response)
            
            # Add metadata
            analysis['llm_provider'] = response.get('provider')
            analysis['llm_model'] = response.get('model')
            
            return analysis
            
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            
            # Return minimal fallback analysis
            return {
                "paradigm": "unknown",
                "patterns": [],
                "key_concepts": [],
                "can_use_standard_crs": False,
                "confidence": 0.0,
                "uncertainty": [
                    "LLM analysis failed",
                    "Manual configuration required"
                ],
                "error": str(e)
            }
    
    def _build_analysis_prompt(
        self,
        repo_name: str,
        file_tree: Dict,
        sample_files: Dict[str, str],
        dependencies: List[str]
    ) -> str:
        """Build the LLM analysis prompt"""
        
        # Simplify file tree for prompt
        structure_str = json.dumps(file_tree['structure'], indent=2)
        
        # Limit sample files in prompt
        samples_str = ""
        for path, content in list(sample_files.items())[:10]:
            samples_str += f"\n### {path}\n```python\n{content[:500]}\n```\n"
        
        prompt = f"""
Analyze this Python repository: {repo_name}

**File Structure:**
```
{structure_str}
```

**Dependencies:**
{', '.join(dependencies[:20])}

**Sample Files:**
{samples_str}

**Your Task:**
Determine the repository's architecture paradigm and structure.

Return JSON with this EXACT structure:
{{
  "paradigm": "django|fastapi|celery_tasks|service_classes|microservice|cli|library|other",
  "patterns": ["class-based", "function-based", "async", ...],
  "key_concepts": ["model", "view", "service", "handler", "task", ...],
  "framework_detected": "Django|FastAPI|Flask|None",
  "can_use_standard_crs": true|false,
  "confidence": 0.0-1.0,
  "uncertainty": ["question1", "question2", ...],
  "reasoning": "Brief explanation of your analysis"
}}

**Guidelines:**
- paradigm: Primary architecture pattern
- patterns: Code organization patterns found
- key_concepts: Main abstractions (models, services, handlers, etc)
- can_use_standard_crs: true if this is standard Django, false otherwise
- confidence: How certain you are (0.0-1.0)
- uncertainty: What questions should we ask the user to clarify?
- reasoning: 2-3 sentences explaining your analysis

Return ONLY the JSON, no other text.
"""
        
        return prompt