# GitHub OAuth Setup Guide

Quick setup guide for GitHub OAuth integration (prototyping mode).

## Quick Start (2 Options)

### Option 1: Personal Access Token (Fastest - 2 minutes) ⚡

**For quick prototyping, skip OAuth and just use a personal token:**

1. Go to: https://github.com/settings/tokens/new
2. Generate token with scopes: `repo`, `user`
3. Copy the token
4. Add to `.env`:
   ```
   GITHUB_TOKEN=ghp_your_token_here
   ```
5. Done! Start using the API

**Test it:**
```bash
curl http://localhost:8000/api/auth/github/test?token=YOUR_TOKEN
```

---

### Option 2: Full OAuth Flow (5-10 minutes) 🔄

**For a more realistic OAuth implementation:**

#### Step 1: Create GitHub OAuth App

1. Go to: https://github.com/settings/developers
2. Click **"New OAuth App"**
3. Fill in:
   - **Application name:** `Auto Code Generator (Dev)`
   - **Homepage URL:** `http://localhost:8000`
   - **Authorization callback URL:** `http://localhost:8000/api/auth/github/callback`
4. Click **"Register application"**
5. Copy the **Client ID**
6. Click **"Generate a new client secret"**
7. Copy the **Client Secret**

#### Step 2: Update `.env` File

Edit `/agent-system/backend/.env`:

```env
# GitHub OAuth Configuration
GITHUB_CLIENT_ID=your_actual_client_id_here
GITHUB_CLIENT_SECRET=your_actual_client_secret_here
GITHUB_OAUTH_CALLBACK_URL=http://localhost:8000/api/auth/github/callback
GITHUB_OAUTH_SCOPE=repo,user
```

#### Step 3: Start the Backend Server

```bash
cd agent-system/backend
python manage.py runserver
```

#### Step 4: Initiate OAuth Flow

1. Open browser: http://localhost:8000/api/auth/github/login
2. You'll be redirected to GitHub
3. Click **"Authorize"**
4. GitHub redirects back with your token
5. **Copy the `access_token` from the response**
6. Add it to `.env`:
   ```
   GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
   ```

---

## Available Endpoints

### OAuth Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/github/login` | GET | Redirects to GitHub OAuth |
| `/api/auth/github/callback` | GET | Receives OAuth callback |
| `/api/auth/github/test` | GET | Test token validity |

### Example Usage

**1. Test your token:**
```bash
curl "http://localhost:8000/api/auth/github/test?token=YOUR_TOKEN"
```

**2. Get user info:**
```python
from agent.services.github_client import GitHubClient

client = GitHubClient(token="YOUR_TOKEN")
user_info = client.get_authenticated_user()
print(user_info)
```

**3. List repositories:**
```python
repos = client.list_user_repos(per_page=10)
for repo in repos:
    print(f"{repo['full_name']} - {repo['description']}")
```

**4. Get repo info:**
```python
info = client.get_repo_info("https://github.com/owner/repo")
print(f"Stars: {info['stars']}, Language: {info['language']}")
```

**5. Get file contents:**
```python
file_content = client.get_file_content("owner", "repo", "README.md")
print(file_content['content'])
```

**6. Clone repository:**
```python
result = client.clone_repository(
    "https://github.com/owner/repo",
    "/path/to/clone",
    branch="main"
)
print(result)
```

---

## GitHub API Features Available

### User Operations
- ✅ Get authenticated user info
- ✅ List user repositories (public + private)

### Repository Operations
- ✅ Get repository metadata (stars, language, etc.)
- ✅ List branches
- ✅ Get directory contents
- ✅ Get file contents
- ✅ Clone repositories (via git)

### Coming Soon
- Create pull requests
- Create issues
- Add comments
- Webhooks
- Repository creation

---

## Troubleshooting

### "GitHub OAuth not configured"
- Make sure you've updated `.env` with actual Client ID and Secret
- Restart Django server after updating `.env`

### "Failed to get access token"
- Check Client Secret is correct
- Verify callback URL matches exactly: `http://localhost:8000/api/auth/github/callback`

### "token_valid": false
- Token may have expired
- Re-run OAuth flow to get new token
- Or generate new Personal Access Token

### "Private repos won't work"
- Make sure token has `repo` scope
- For OAuth: verify scope includes `repo`
- For PAT: check boxes for `repo` permission

---

## Security Notes (For Production)

🚨 **Current setup is for PROTOTYPING only!**

For production, add:
- Secure state parameter (CSRF protection)
- Token encryption in database
- Session management
- Token refresh mechanism
- HTTPS only
- Environment-specific callback URLs
- Secret management (not in .env file)

---

## Next Steps

1. ✅ Get a token (Option 1 or 2)
2. ✅ Test it with `/api/auth/github/test`
3. ✅ Use `GitHubClient` to access repos
4. ✅ Build features using the GitHub API methods

Happy coding! 🚀
