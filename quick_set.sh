#!/bin/bash
#
# Quick Setup Script for CRS Agent Prototype
#
# This gets you from zero to running prototype in minutes
#
# Usage:
#   chmod +x quick_setup.sh
#   ./quick_setup.sh
#

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════╗
║   CRS Agent Prototype Setup           ║
║   Phase 1: LLM-Guided Discovery       ║
╚═══════════════════════════════════════╝
EOF
echo -e "${NC}"

# ==========================================
# Step 1: Check Prerequisites
# ==========================================

log_info "Checking prerequisites..."

# Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found. Please install Python 3.10+"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
log_success "Python: $PYTHON_VERSION"

# Git
if ! command -v git &> /dev/null; then
    log_error "Git not found. Please install git"
    exit 1
fi
log_success "Git: $(git --version | cut -d' ' -f3)"

# Ollama (optional)
if command -v ollama &> /dev/null; then
    log_success "Ollama: Found"
    OLLAMA_AVAILABLE=true
else
    log_warning "Ollama not found (optional - will use cloud LLM)"
    OLLAMA_AVAILABLE=false
fi

# ==========================================
# Step 2: Create Project Structure
# ==========================================

log_info "Creating project structure..."

mkdir -p agent-system/backend
mkdir -p agent-system/frontend
mkdir -p agent-system/workspaces
mkdir -p agent-system/crs_workspaces

cd agent-system/backend

log_success "Project structure created"

# ==========================================
# Step 3: Setup Python Environment
# ==========================================

log_info "Setting up Python environment..."

python3 -m venv venv
source venv/bin/activate

log_success "Virtual environment created"

# ==========================================
# Step 4: Install Dependencies
# ==========================================

log_info "Installing Python dependencies..."

cat > requirements.txt << 'EOF'
django==4.2
djangorestframework==3.14
django-cors-headers==4.3
psycopg2-binary==2.9
python-dotenv==1.0
requests==2.31
anthropic==0.18
toml==0.10
EOF

pip install --quiet -r requirements.txt

log_success "Dependencies installed"

# ==========================================
# Step 5: Create Django Project
# ==========================================

log_info "Creating Django project..."

if [ ! -f "manage.py" ]; then
    django-admin startproject config .
    python manage.py startapp agent
    mkdir -p llm agent/services
    touch llm/__init__.py agent/services/__init__.py
    log_success "Django project created"
else
    log_warning "Django project already exists"
fi

# ==========================================
# Step 6: Setup Environment Variables
# ==========================================

log_info "Creating environment file..."

cat > .env << 'EOF'
# Django
SECRET_KEY=dev-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (SQLite for prototype)
DATABASE_URL=sqlite:///db.sqlite3

# LLM Configuration
LOCAL_LLM_MODEL=deepseek-coder:6.7b
OLLAMA_BASE_URL=http://localhost:11434

# Cloud LLM (optional - set one)
CLOUD_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=
# Or OpenAI:
# CLOUD_LLM_PROVIDER=openai  
# OPENAI_API_KEY=

# GitHub (optional)
GITHUB_TOKEN=

# Paths
WORKSPACES_ROOT=../workspaces
CRS_WORKSPACES_ROOT=../crs_workspaces
EOF

log_success "Environment file created (.env)"

# ==========================================
# Step 7: Configure Django Settings
# ==========================================

log_info "Configuring Django settings..."

cat > config/settings.py << 'EOFPYTHON'
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'agent',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'agent.User'

CORS_ALLOWED_ORIGINS = ["http://localhost:8080", "http://localhost:3000"]

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
EOFPYTHON

log_success "Django settings configured"

# ==========================================
# Step 8: Run Migrations
# ==========================================

log_info "Running database migrations..."

python manage.py makemigrations agent || log_warning "Migrations already exist"
python manage.py migrate

log_success "Database initialized"

# ==========================================
# Step 9: Test LLM Connection
# ==========================================

log_info "Testing LLM connection..."

python << 'EOFTEST'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from llm.router import get_llm_router

try:
    router = get_llm_router()
    health = router.health_check()
    
    print("\nLLM Health Check:")
    print(f"  Local:  {'✅ Available' if health['local']['available'] else '❌ Not available'}")
    print(f"  Cloud:  {'✅ Available' if health['cloud']['available'] else '❌ Not available'}")
    
    if health['local']['available'] or health['cloud']['available']:
        print("\n✅ LLM connection successful!")
    else:
        print("\n⚠️  No LLM available. Set ANTHROPIC_API_KEY in .env file.")
        
except Exception as e:
    print(f"\n⚠️  LLM test failed: {e}")
    print("   Check your .env configuration")
EOFTEST

# ==========================================
# Step 10: Create Superuser (Optional)
# ==========================================

log_info "Creating Django superuser..."

echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'admin123') if not User.objects.filter(username='admin').exists() else None" | python manage.py shell

log_success "Superuser created (admin/admin123)"

# ==========================================
# Done!
# ==========================================

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ SETUP COMPLETE!                  ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""

log_info "Next steps:"
echo ""
echo "1. Start Django server:"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   python manage.py runserver"
echo ""
echo "2. Test the prototype:"
echo "   python prototype_test.py"
echo ""
echo "3. Access admin panel:"
echo "   http://localhost:8000/admin"
echo "   Username: admin"
echo "   Password: admin123"
echo ""
echo "4. Configure LLM (if not done):"
echo "   - For Ollama: ollama pull deepseek-coder:6.7b"
echo "   - For Anthropic: Set ANTHROPIC_API_KEY in .env"
echo ""

if [ "$OLLAMA_AVAILABLE" = false ]; then
    log_warning "Ollama not installed. Install from: https://ollama.ai"
    echo "   Then run: ollama pull deepseek-coder:6.7b"
    echo ""
fi

log_success "Ready to build! 🚀"

freeze