#!/bin/bash
# Setup script for Phase 2 development environment

set -e  # Exit on error

echo "=================================================="
echo "Phase 2 Development Environment Setup"
echo "=================================================="
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed"
    echo "Please install uv: https://github.com/astral-sh/uv"
    exit 1
fi

echo "✓ uv is installed"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
uv sync --extra dev
echo "✓ Dependencies installed"
echo ""

# Install pre-commit hooks
echo "🔧 Installing pre-commit hooks..."
uv run pre-commit install
echo "✓ Pre-commit hooks installed"
echo ""

# Run formatting
echo "🎨 Formatting code..."
uv run ruff format .
echo "✓ Code formatted"
echo ""

# Fix linting issues
echo "🔍 Fixing linting issues..."
uv run ruff check --fix .
echo "✓ Linting issues fixed"
echo ""

# Run tests
echo "🧪 Running tests..."
uv run pytest -v
echo "✓ Tests passed"
echo ""

# Apply database migrations
echo "🗄️  Applying database migrations..."
uv run alembic upgrade head
echo "✓ Database migrated"
echo ""

echo "=================================================="
echo "✨ Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env: cp .env.example .env"
echo "  2. Fill in your API credentials in .env"
echo "  3. Run the application: python main.py"
echo ""
echo "Development commands:"
echo "  Run tests:        pytest"
echo "  Format code:      ruff format ."
echo "  Check linting:    ruff check ."
echo "  Type checking:    mypy src/"
echo "  Security scan:    bandit -r src/"
echo ""
echo "See DEVELOPMENT.md for detailed documentation"
echo ""
