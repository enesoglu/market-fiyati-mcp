#!/bin/sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_COMMAND=${PYTHON:-python3}
"$PYTHON_COMMAND" -c "import sys; sys.exit(0 if sys.version_info >= (3,13) else 'Python 3.13+ is required')"
"$PYTHON_COMMAND" -m venv "$PROJECT_ROOT/.venv"
ENVIRONMENT_PYTHON="$PROJECT_ROOT/.venv/bin/python"
"$ENVIRONMENT_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.lock"
"$ENVIRONMENT_PYTHON" -m pip install --no-deps "$PROJECT_ROOT"
printf 'Installed. Generate your MCP client configuration with:\n'
printf '"%s" -m market_fiyati_mcp --client-config\n' "$ENVIRONMENT_PYTHON"
