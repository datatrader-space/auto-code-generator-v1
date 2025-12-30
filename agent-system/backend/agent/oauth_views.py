"""
GitHub OAuth Views for Quick Prototyping
Simple OAuth flow to get repository access tokens
"""
import requests
import os
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import User
from .services.github_client import GitHubClient


@api_view(['GET'])
@permission_classes([AllowAny])
def github_login(request):
    """
    Step 1: Redirect user to GitHub OAuth authorization page

    Usage: Navigate to http://localhost:8000/api/auth/github/login
    """
    client_id = settings.GITHUB_CLIENT_ID
    redirect_uri = settings.GITHUB_OAUTH_CALLBACK_URL
    scope = settings.GITHUB_OAUTH_SCOPE

    if not client_id or client_id == 'your_github_client_id_here':
        return JsonResponse({
            'error': 'GitHub OAuth not configured',
            'instructions': [
                '1. Go to https://github.com/settings/developers',
                '2. Click "New OAuth App"',
                '3. Set Authorization callback URL to: http://localhost:8000/api/auth/github/callback',
                '4. Copy Client ID and Client Secret to .env file',
                '5. Update GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env'
            ]
        }, status=400)

    # Build GitHub OAuth URL
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&state=random_state_string"  # In production, use secure random state
    )

    return redirect(github_auth_url)


@api_view(['GET'])
@permission_classes([AllowAny])
def github_callback(request):
    """
    Step 2: GitHub redirects back here with authorization code
    Exchange code for access token

    This endpoint is called automatically by GitHub after user authorizes
    """
    code = request.GET.get('code')
    state = request.GET.get('state')

    if not code:
        return JsonResponse({
            'error': 'No authorization code received',
            'details': 'User may have cancelled the OAuth flow'
        }, status=400)

    # Exchange code for access token
    token_url = "https://github.com/login/oauth/access_token"
    token_data = {
        'client_id': settings.GITHUB_CLIENT_ID,
        'client_secret': settings.GITHUB_CLIENT_SECRET,
        'code': code,
        'redirect_uri': settings.GITHUB_OAUTH_CALLBACK_URL,
    }

    headers = {'Accept': 'application/json'}

    try:
        response = requests.post(token_url, data=token_data, headers=headers)
        response.raise_for_status()
        token_response = response.json()

        access_token = token_response.get('access_token')

        if not access_token:
            return JsonResponse({
                'error': 'Failed to get access token',
                'response': token_response
            }, status=400)

        # Get user info from GitHub
        user_response = requests.get(
            'https://api.github.com/user',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        user_data = user_response.json()

        github_username = user_data.get('login')
        github_email = user_data.get('email')

        # For quick prototyping, just return the token
        # In production, you'd create/update user and create session
        return JsonResponse({
            'success': True,
            'access_token': access_token,
            'github_username': github_username,
            'github_email': github_email,
            'message': 'OAuth successful! Copy the access_token and add it to your .env file as GITHUB_TOKEN',
            'instructions': [
                f'1. Copy this token: {access_token}',
                '2. Add to .env file: GITHUB_TOKEN={access_token}',
                '3. Now you can use GitHub API with full repo access!',
                '4. Test it by calling /api/repositories/ endpoints'
            ],
            'scopes': token_response.get('scope', '').split(',')
        })

    except requests.RequestException as e:
        return JsonResponse({
            'error': 'Failed to exchange code for token',
            'details': str(e)
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def test_token(request):
    """
    Test endpoint to verify GitHub token works

    Usage: GET /api/auth/github/test?token=YOUR_TOKEN
    """
    token = request.GET.get('token') or settings.GITHUB_TOKEN

    if not token:
        return JsonResponse({
            'error': 'No token provided',
            'usage': 'GET /api/auth/github/test?token=YOUR_TOKEN'
        }, status=400)

    try:
        # Test token by getting user info
        response = requests.get(
            'https://api.github.com/user',
            headers={'Authorization': f'Bearer {token}'}
        )
        response.raise_for_status()
        user_data = response.json()

        # Test repo access
        repos_response = requests.get(
            'https://api.github.com/user/repos',
            headers={'Authorization': f'Bearer {token}'},
            params={'per_page': 5}
        )
        repos = repos_response.json() if repos_response.status_code == 200 else []

        return JsonResponse({
            'success': True,
            'token_valid': True,
            'user': {
                'username': user_data.get('login'),
                'name': user_data.get('name'),
                'email': user_data.get('email'),
                'public_repos': user_data.get('public_repos'),
                'private_repos': user_data.get('total_private_repos', 0),
            },
            'sample_repos': [
                {
                    'name': repo.get('name'),
                    'full_name': repo.get('full_name'),
                    'private': repo.get('private'),
                    'url': repo.get('html_url')
                }
                for repo in repos[:5]
            ] if isinstance(repos, list) else [],
            'rate_limit': {
                'remaining': response.headers.get('X-RateLimit-Remaining'),
                'limit': response.headers.get('X-RateLimit-Limit'),
            }
        })

    except requests.RequestException as e:
        return JsonResponse({
            'success': False,
            'token_valid': False,
            'error': str(e)
        }, status=401)


@api_view(['GET'])
@permission_classes([AllowAny])
def list_github_repos(request):
    """
    List all GitHub repositories for the authenticated user

    Usage: GET /api/auth/github/repos
    """
    token = request.GET.get('token') or os.getenv('GITHUB_TOKEN')

    if not token:
        return JsonResponse({
            'error': 'No GitHub token provided',
            'message': 'Set GITHUB_TOKEN in .env or complete OAuth flow first'
        }, status=401)

    try:
        client = GitHubClient(token=token)
        repos = client.list_user_repos(per_page=100)

        if isinstance(repos, dict) and 'error' in repos:
            return JsonResponse(repos, status=401)

        return JsonResponse({
            'success': True,
            'count': len(repos),
            'repositories': repos
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch repositories',
            'details': str(e)
        }, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def get_repo_info(request):
    """
    Get detailed info about a specific GitHub repository

    Usage: POST /api/auth/github/repo-info
    Body: { "github_url": "https://github.com/owner/repo" }
    """
    github_url = request.data.get('github_url')

    if not github_url:
        return JsonResponse({
            'error': 'github_url is required'
        }, status=400)

    token = request.data.get('token') or os.getenv('GITHUB_TOKEN')

    if not token:
        return JsonResponse({
            'error': 'No GitHub token provided'
        }, status=401)

    try:
        client = GitHubClient(token=token)
        info = client.get_repo_info(github_url)

        if 'error' in info:
            return JsonResponse(info, status=404)

        # Also get branches
        branches = client.get_repo_branches(info['owner'], info['repo'])

        return JsonResponse({
            'success': True,
            'repository': info,
            'branches': branches if not isinstance(branches, dict) else []
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to get repository info',
            'details': str(e)
        }, status=500)
