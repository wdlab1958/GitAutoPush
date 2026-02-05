#!/bin/bash
# ============================================
# GitAutoPush - Quick Setup & Launch Script
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "🚀 GitAutoPush Setup"
echo "===================="

# 1. Python 확인
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Python $PYTHON_VERSION found"

# 2. venv 생성
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 3. 의존성 설치
echo "📦 Installing dependencies..."
pip install -q -r "$SCRIPT_DIR/requirements.txt"

# 4. Ollama 확인
echo ""
if command -v ollama &> /dev/null; then
    echo "✅ Ollama is installed"
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✅ Ollama server is running"
        MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = [m['name'] for m in data.get('models', [])]
print(', '.join(models) if models else 'No models installed')
")
        echo "📋 Available models: $MODELS"
    else
        echo "⚠️  Ollama is installed but not running. Start with: ollama serve"
    fi
else
    echo "⚠️  Ollama not found. Install: curl -fsSL https://ollama.ai/install.sh | sh"
    echo "   Then: ollama pull llama3.1:8b"
fi

# 5. Git 확인
echo ""
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version)
    echo "✅ $GIT_VERSION"
else
    echo "❌ Git is not installed"
    exit 1
fi

# 6. 앱 실행
echo ""
echo "🚀 Launching GitAutoPush..."
echo "===================="
cd "$SCRIPT_DIR"
python3 main.py
