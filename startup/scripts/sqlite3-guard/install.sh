#!/usr/bin/env bash
# sqlite3 guard installer — blocks direct writes to kanban/workflow databases.
# Forces use of hermes kanban / kanban_* tools which run recompute_ready properly.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing sqlite3 guard..."

# 1. CLI guard — replace /usr/bin/sqlite3 with wrapper, keep real binary
if [ ! -f /usr/bin/sqlite3-real ]; then
    echo "Backing up real sqlite3 to /usr/bin/sqlite3-real..."
    sudo -S -p '' cp /usr/bin/sqlite3 /usr/bin/sqlite3-real
fi

echo "Installing CLI guard to /usr/bin/sqlite3..."
sudo -S -p '' cp "$SCRIPT_DIR/sqlite3-guard.sh" /usr/bin/sqlite3
sudo -S -p '' chmod +x /usr/bin/sqlite3

# 2. Python guard — install sitecustomize.py
PYTHON_SITE="$(python3 -c "import site; print(site.getusersitepackages())")"
echo "Installing Python guard to $PYTHON_SITE/sitecustomize.py..."
mkdir -p "$PYTHON_SITE"
cp "$SCRIPT_DIR/sitecustomize.py" "$PYTHON_SITE/sitecustomize.py"

# 3. Verify
echo ""
echo "=== Verification ==="
echo "CLI: $(sqlite3 --version)"
echo "CLI guard active: $(head -1 /usr/bin/sqlite3)"

# Test read
echo ""
echo "Testing read access (should work)..."
sqlite3 ~/.hermes-teams/startup/kanban/boards/ngin/kanban.db "SELECT count(*) FROM tasks" 2>&1 || echo "(board not found — ok)"

# Test write block
echo ""
echo "Testing write block (should fail)..."
sqlite3 ~/.hermes-teams/startup/kanban/boards/ngin/kanban.db "UPDATE tasks SET status='test'" 2>&1 || true

# Test Python write block
echo ""
echo "Testing Python write block (should fail)..."
python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/.hermes-teams/startup/kanban/boards/ngin/kanban.db')
try:
    conn.execute(\"UPDATE tasks SET status='test'\")
    print('BYPASSED — guard failed!')
except sqlite3.OperationalError as e:
    print(f'Blocked: {str(e)[:60]}')
" 2>&1

echo ""
echo "Done."
