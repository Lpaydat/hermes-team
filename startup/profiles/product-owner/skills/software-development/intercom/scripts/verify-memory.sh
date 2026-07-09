#!/usr/bin/env bash
# Verify intercom agent memory across rounds.
# Usage: verify-memory.sh <target_profile> <topic> <secret_code>
# Sends a secret code via spawn, then resumes the session and asks for it back.
# Exit 0 = agent remembered, Exit 1 = agent forgot or spawn failed.
set -euo pipefail

TARGET="${1:?Usage: verify-memory.sh <target_profile> <topic> <secret_code>}"
TOPIC="${2:?Missing topic}"
SECRET="${3:?Missing secret code}"

INTERCOM_DIR="$HOME/.hermes-teams/_shared/intercom"
SOCK="$INTERCOM_DIR/.intercom.sock"

# Send the secret via spawn (use ops as sender so target is offline)
python3 -c "
import sys, os
sys.path.insert(0, '$INTERCOM_DIR')
from broker import IntercomClient
c = IntercomClient(sock_path='$SOCK')
c.connect()
c.register('t', 'ops')
r = c.send_message({
    'type': 'send', 'from_team': 't', 'from_profile': 'ops',
    'to_team': '', 'to_profile': '$TARGET', 'topic': '$TOPIC',
    'content': {'text': 'Remember this code: $SECRET'}, 'spawn': True,
}, timeout=300)
sid = r.get('hermes_session_id')
if not sid:
    print('SPAWN_FAILED: ' + str(r), file=sys.stderr)
    sys.exit(1)
print(sid)
" 2>/dev/null > /tmp/intercom_sid.txt

SESSION_ID=$(cat /tmp/intercom_sid.txt)
rm -f /tmp/intercom_sid.txt

if [ -z "$SESSION_ID" ]; then
    echo "❌ Spawn failed — no session ID captured"
    exit 1
fi

echo "Spawned session: $SESSION_ID"

# Resume and ask for the secret
RESPONSE=$(hermes -p "$TARGET" chat -q "What secret code was I given? Just the code, nothing else." \
    -Q --pass-session-id --resume "$SESSION_ID" 2>/dev/null)

if echo "$RESPONSE" | grep -qi "$SECRET"; then
    echo "✅ Agent remembered: $SECRET"
    exit 0
else
    echo "❌ Agent forgot. Response: $RESPONSE"
    exit 1
fi
