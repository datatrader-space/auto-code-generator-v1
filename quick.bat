@echo off
REM Quick Setup Script for CRS Agent Prototype (Windows)
REM
REM Usage: Just double-click this file
REM

echo.
echo ╔═══════════════════════════════════════╗
echo ║   CRS Agent Prototype Setup           ║
echo ║   Phase 1: LLM-Guided Discovery       ║
echo ╚═══════════════════════════════════════╝
echo.

REM ==========================================
REM Step 1: Check Prerequisites
REM ==========================================

echo [INFO] Checking prerequisites...
echo.

REM Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] Python: %PYTHON_VERSION%

REM Git
git --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Git not found. You'll need it for GitHub integration
) else (
    echo [OK] Git: Found
)

REM Ollama (optional)
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama not found (optional - will use cloud LLM)
    set OLLAMA_AVAILABLE=false
) else (
    echo [OK] Ollama: Found
    set OLLAMA_AVAILABLE=true
)

echo.
pause

REM ==========================================
REM Step 2: Create Project Structure
REM ==========================================

echo.
echo [INFO] Creating project structure...

if not exist "agent-system" mkdir agent-system
cd agent-system

if not exist "backend" mkdir backend
if not exist "frontend" mkdir frontend
if not exist "workspaces" mkdir workspaces
if not exist "crs_workspaces" mkdir crs_workspaces

cd backend

echo [OK] Project structure created
echo.
pause

REM ==========================================
REM Step 3: Setup Python Environment
REM ==========================================

echo.
echo [INFO] Setting up Python environment...

if not exist "venv" (
    python -m venv venv
    echo [OK] Virtual environment created
) else (
    echo [WARNING] Virtual environment already exists
)

echo.
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
pause

REM ==========================================
REM Step 4: Install Dependencies
REM ==========================================

echo.
echo [INFO] Installing Python dependencies...
echo This may take a few minutes...
echo.

echo django==4.2 > requirements.txt
echo djangorestframework==3.14 >> requirements.txt
echo django-cors-headers==4.3 >> requirements.txt
echo python-dotenv==1.0 >> requirements.txt
echo requests==2.31 >> requirements.txt
echo anthropic==0.18 >> requirements.txt
echo toml==0.10 >> requirements.txt

pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

echo [OK] Dependencies installed
echo.
pause

REM ==========================================
REM Step 5: Create Django Project
REM ==========================================

echo.
echo [INFO] Creating Django project...

if not exist "manage.py" (
    django-admin startproject config .
    python manage.py startapp agent
    
    if not exist "llm" mkdir llm
    if not exist "agent\services" mkdir agent\services
    
    type nul > llm\__init__.py
    type nul > agent\services\__init__.py
    
    echo [OK] Django project created
) else (
    echo [WARNING] Django project already exists
)

echo.
pause

REM ==========================================
REM Step 6: Setup Environment Variables
REM ==========================================

echo.
echo [INFO] Creating environment file...

(
echo # Django
echo SECRET_KEY=dev-secret-key-change-in-production
echo DEBUG=True
echo ALLOWED_HOSTS=localhost,127.0.0.1
echo.
echo # Database (SQLite for prototype^)
echo DATABASE_URL=sqlite:///db.sqlite3
echo.
echo # LLM Configuration
echo LOCAL_LLM_MODEL=deepseek-coder:6.7b
echo OLLAMA_BASE_URL=http://localhost:11434
echo.
echo # Cloud LLM (optional - set one^)
echo CLOUD_LLM_PROVIDER=anthropic
echo ANTHROPIC_API_KEY=
echo # Or OpenAI:
echo # CLOUD_LLM_PROVIDER=openai
echo # OPENAI_API_KEY=
echo.
echo # GitHub (optional^)
echo GITHUB_TOKEN=
echo.
echo # Paths
echo WORKSPACES_ROOT=../workspaces
echo CRS_WORKSPACES_ROOT=../crs_workspaces
) > .env

echo [OK] Environment file created (.env^)
echo.
pause

REM ==========================================
REM Step 7: Instructions for Manual File Copy
REM ==========================================

echo.
echo ╔═══════════════════════════════════════╗
echo ║   IMPORTANT: Manual Steps Required    ║
echo ╚═══════════════════════════════════════╝
echo.
echo Now you need to copy the Python files from the artifacts:
echo.
echo 1. Create these files in backend\:
echo    - agent\models.py (from 'django_models' artifact)
echo    - llm\router.py (from 'llm_router' artifact)
echo    - llm\ollama.py (from 'ollama_client' artifact)
echo    - llm\anthropic_client.py (from 'anthropic_client_minimal' artifact)
echo.
echo 2. Create these in backend\agent\services\:
echo    - repo_analyzer.py (from 'repo_analyzer' artifact)
echo    - question_generator.py (from 'question_generator' artifact)
echo    - knowledge_builder.py (from 'knowledge_builder' artifact)
echo    - github_client.py (from 'github_client_minimal' artifact)
echo.
echo 3. Copy prototype_test.py to backend\
echo.
echo 4. Update config\settings.py with the configuration
echo.
echo Press any key when you've copied all files...
pause

REM ==========================================
REM Step 8: Run Migrations
REM ==========================================

echo.
echo [INFO] Running database migrations...

python manage.py makemigrations agent
python manage.py migrate

echo [OK] Database initialized
echo.
pause

REM ==========================================
REM Step 9: Create Superuser
REM ==========================================

echo.
echo [INFO] Creating Django superuser...
echo Username: admin
echo Password: admin123
echo.

echo from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'admin123') if not User.objects.filter(username='admin').exists() else None | python manage.py shell

echo [OK] Superuser created (admin/admin123)
echo.

REM ==========================================
REM Done!
REM ==========================================

echo.
echo ╔═══════════════════════════════════════╗
echo ║   ✅ SETUP COMPLETE!                  ║
echo ╚═══════════════════════════════════════╝
echo.
echo [INFO] Next steps:
echo.
echo 1. Configure LLM in .env file:
echo    - For Ollama: ollama pull deepseek-coder:6.7b
echo    - For Anthropic: Set ANTHROPIC_API_KEY in .env
echo.
echo 2. Start Django server:
echo    python manage.py runserver
echo.
echo 3. Test the prototype:
echo    python prototype_test.py
echo.
echo 4. Access admin panel:
echo    http://localhost:8000/admin
echo    Username: admin
echo    Password: admin123
echo.

if "%OLLAMA_AVAILABLE%"=="false" (
    echo [WARNING] Ollama not installed. Install from: https://ollama.ai
    echo Then run: ollama pull deepseek-coder:6.7b
    echo.
)

echo Press any key to exit...
pause >nul