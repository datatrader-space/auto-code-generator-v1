# agent/services/github_client.py
"""
GitHub Client - Clone repos and access GitHub API via OAuth
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from github import Github, GithubException

logger = logging.getLogger(__name__)


class GitHubClient:
    """
    GitHub operations with OAuth support

    Features:
    - Clone repositories via git
    - Access GitHub API via PyGithub
    - List repositories, branches, commits
    - Get file contents
    - Repository metadata
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv('GITHUB_TOKEN')

        if not self.token:
            logger.warning("GITHUB_TOKEN not set. Private repos and API access won't work.")
            self.gh = None
        else:
            # Initialize PyGithub client
            try:
                self.gh = Github(self.token)
                # Test authentication
                user = self.gh.get_user()
                logger.info(f"GitHub API authenticated as: {user.login}")
            except GithubException as e:
                logger.error(f"GitHub authentication failed: {e}")
                self.gh = None
    
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
                "private": bool,
                "description": str,
                "stars": int,
                "language": str
            }
        """

        # Parse URL
        parts = github_url.rstrip('/').split('/')
        if len(parts) < 2:
            return {"error": "Invalid GitHub URL"}

        owner = parts[-2]
        repo_name = parts[-1].replace('.git', '')

        # If PyGithub is available, use API
        if self.gh:
            try:
                repo = self.gh.get_repo(f"{owner}/{repo_name}")
                return {
                    "owner": owner,
                    "repo": repo_name,
                    "full_name": repo.full_name,
                    "default_branch": repo.default_branch,
                    "private": repo.private,
                    "description": repo.description or "",
                    "stars": repo.stargazers_count,
                    "language": repo.language or "Unknown",
                    "forks": repo.forks_count,
                    "open_issues": repo.open_issues_count,
                    "created_at": repo.created_at.isoformat() if repo.created_at else None,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                }
            except GithubException as e:
                logger.error(f"Failed to get repo info: {e}")
                return {"error": str(e)}

        # Fallback: basic parsing
        return {
            "owner": owner,
            "repo": repo_name,
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

    # === NEW: GitHub API Methods (OAuth-powered) ===

    def list_user_repos(self, per_page: int = 30) -> List[Dict[str, Any]]:
        """
        List all repositories accessible to the authenticated user

        Returns:
            List of repository info dicts
        """
        if not self.gh:
            return {"error": "GitHub API not authenticated. Set GITHUB_TOKEN."}

        try:
            user = self.gh.get_user()
            repos = user.get_repos()

            return [
                {
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "private": repo.private,
                    "url": repo.html_url,
                    "clone_url": repo.clone_url,
                    "description": repo.description or "",
                    "language": repo.language or "Unknown",
                    "stars": repo.stargazers_count,
                    "default_branch": repo.default_branch,
                }
                for repo in list(repos[:per_page])
            ]
        except GithubException as e:
            logger.error(f"Failed to list repos: {e}")
            return {"error": str(e)}

    def get_repo_branches(self, owner: str, repo_name: str) -> List[Dict[str, Any]]:
        """
        Get all branches for a repository

        Args:
            owner: Repository owner
            repo_name: Repository name

        Returns:
            List of branch info
        """
        if not self.gh:
            return {"error": "GitHub API not authenticated"}

        try:
            repo = self.gh.get_repo(f"{owner}/{repo_name}")
            branches = repo.get_branches()

            return [
                {
                    "name": branch.name,
                    "commit_sha": branch.commit.sha,
                    "protected": branch.protected,
                }
                for branch in branches
            ]
        except GithubException as e:
            logger.error(f"Failed to get branches: {e}")
            return {"error": str(e)}

    def get_repo_contents(
        self,
        owner: str,
        repo_name: str,
        path: str = "",
        ref: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get contents of a directory in a repository

        Args:
            owner: Repository owner
            repo_name: Repository name
            path: Path to directory (empty for root)
            ref: Branch/tag/commit (default: default branch)

        Returns:
            List of files/directories
        """
        if not self.gh:
            return {"error": "GitHub API not authenticated"}

        try:
            repo = self.gh.get_repo(f"{owner}/{repo_name}")
            contents = repo.get_contents(path, ref=ref)

            # Handle single file vs directory
            if not isinstance(contents, list):
                contents = [contents]

            return [
                {
                    "name": content.name,
                    "path": content.path,
                    "type": content.type,  # "file" or "dir"
                    "size": content.size,
                    "sha": content.sha,
                    "download_url": content.download_url if content.type == "file" else None,
                }
                for content in contents
            ]
        except GithubException as e:
            logger.error(f"Failed to get contents: {e}")
            return {"error": str(e)}

    def get_file_content(
        self,
        owner: str,
        repo_name: str,
        file_path: str,
        ref: str = None
    ) -> Dict[str, Any]:
        """
        Get content of a specific file

        Args:
            owner: Repository owner
            repo_name: Repository name
            file_path: Path to file
            ref: Branch/tag/commit

        Returns:
            {
                "content": str (decoded),
                "encoding": str,
                "size": int,
                "sha": str
            }
        """
        if not self.gh:
            return {"error": "GitHub API not authenticated"}

        try:
            repo = self.gh.get_repo(f"{owner}/{repo_name}")
            file_content = repo.get_contents(file_path, ref=ref)

            return {
                "content": file_content.decoded_content.decode('utf-8'),
                "encoding": file_content.encoding,
                "size": file_content.size,
                "sha": file_content.sha,
                "path": file_content.path,
            }
        except UnicodeDecodeError:
            # Binary file
            return {
                "error": "Binary file - cannot decode as text",
                "size": file_content.size,
                "download_url": file_content.download_url
            }
        except GithubException as e:
            logger.error(f"Failed to get file: {e}")
            return {"error": str(e)}

    def get_authenticated_user(self) -> Dict[str, Any]:
        """
        Get info about the authenticated user

        Returns:
            User info dict
        """
        if not self.gh:
            return {"error": "GitHub API not authenticated"}

        try:
            user = self.gh.get_user()
            return {
                "username": user.login,
                "name": user.name or "",
                "email": user.email or "",
                "bio": user.bio or "",
                "public_repos": user.public_repos,
                "private_repos": user.total_private_repos,
                "followers": user.followers,
                "following": user.following,
                "avatar_url": user.avatar_url,
                "html_url": user.html_url,
            }
        except GithubException as e:
            logger.error(f"Failed to get user: {e}")
            return {"error": str(e)}