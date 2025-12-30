# agent/services/github_client.py
"""
GitHub Client - Clone and sync repositories
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class GitHubClient:
    """
    Simple GitHub operations
    
    For prototype: Just clone repos
    Later: OAuth, PR creation, webhooks
    """
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv('GITHUB_TOKEN')
        
        if not self.token:
            logger.warning("GITHUB_TOKEN not set. Private repos won't work.")
    
    def clone_repository(
        self,
        github_url: str,
        target_path: str,
        branch: str = 'main'
    ) -> Dict[str, Any]:
        """
        Clone a repository
        
        Args:
            github_url: https://github.com/user/repo
            target_path: Where to clone
            branch: Branch name
            
        Returns:
            {
                "success": bool,
                "path": str,
                "commit_sha": str,
                "error": str
            }
        """
        
        try:
            logger.info(f"Cloning {github_url} to {target_path}")
            
            # Create parent directory
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Build clone URL with token if available
            if self.token:
                # Convert https://github.com/user/repo to https://token@github.com/user/repo
                if github_url.startswith('https://github.com/'):
                    auth_url = github_url.replace(
                        'https://github.com/',
                        f'https://{self.token}@github.com/'
                    )
                else:
                    auth_url = github_url
            else:
                auth_url = github_url
            
            # Clone
            result = subprocess.run(
                ['git', 'clone', '--branch', branch, '--depth', '1', auth_url, target_path],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"Clone failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            
            # Get commit SHA
            commit_sha = self._get_commit_sha(target_path)
            
            logger.info(f"Clone successful: {commit_sha}")
            
            return {
                "success": True,
                "path": target_path,
                "commit_sha": commit_sha,
                "branch": branch
            }
        
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Clone timed out (>5 minutes)"
            }
        except Exception as e:
            logger.error(f"Clone error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_commit_sha(self, repo_path: str) -> str:
        """Get current commit SHA"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip()
        except Exception:
            return ""
    
    def pull_updates(self, repo_path: str) -> Dict[str, Any]:
        """
        Pull latest changes
        
        Args:
            repo_path: Path to cloned repo
            
        Returns:
            {
                "success": bool,
                "commit_sha": str,
                "changes": bool,
                "error": str
            }
        """
        
        try:
            old_sha = self._get_commit_sha(repo_path)
            
            result = subprocess.run(
                ['git', 'pull'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": result.stderr or result.stdout
                }
            
            new_sha = self._get_commit_sha(repo_path)
            
            return {
                "success": True,
                "commit_sha": new_sha,
                "changes": old_sha != new_sha,
                "old_sha": old_sha,
                "new_sha": new_sha
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_repo_info(self, github_url: str) -> Dict[str, Any]:
        """
        Get repository info from GitHub API
        
        Args:
            github_url: https://github.com/user/repo
            
        Returns:
            {
                "owner": str,
                "repo": str,
                "default_branch": str,
                "private": bool
            }
        """
        
        # Parse URL
        parts = github_url.rstrip('/').split('/')
        if len(parts) < 2:
            return {"error": "Invalid GitHub URL"}
        
        owner = parts[-2]
        repo = parts[-1].replace('.git', '')
        
        # For prototype, just return basic info
        # Later: Use GitHub API to get full details
        
        return {
            "owner": owner,
            "repo": repo,
            "default_branch": "main",  # Assume main
            "private": False  # Assume public for now
        }
    
    def check_git_installed(self) -> bool:
        """Check if git is installed"""
        try:
            subprocess.run(
                ['git', '--version'],
                capture_output=True,
                timeout=5
            )
            return True
        except Exception:
            return False