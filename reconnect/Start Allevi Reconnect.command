#!/bin/bash
# Double-click this file to start Allevi Reconnect.
# It runs allevi_client_shim.py, which is the actual program — this file
# just launches it in a Terminal window you can watch and close.
cd "$(dirname "$0")"

echo "Allevi Reconnect"
echo "-----------------"

# Find a working Python. Prefer python3 (the normal name on macOS); fall
# back to plain python in case someone has an unusual setup.
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo
  echo "Python was not found on this Mac."
  echo "Install it from python.org/downloads, then double-click this file again."
  echo
  echo "Press Return to close this window."
  read -r
  exit 1
fi

# If a copy is already running, there's nothing to do — just say so.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo
  echo "Already running. If bioprint.allevi3d.com still shows the printer as"
  echo "disconnected, try reloading that page."
  echo
  echo "Press Return to close this window."
  read -r
  exit 0
fi

"$PYTHON" allevi_client_shim.py &
SERVER_PID=$!

# Give it a moment, then confirm it actually stayed up before declaring success.
sleep 2
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo
  echo "It stopped right after starting — see the error above."
  echo
  echo "Press Return to close this window."
  read -r
  exit 1
fi

echo
echo "Leave this window open while you use bioprint.allevi3d.com."
echo "Closing it (or pressing Control-C) stops the connection."
wait "$SERVER_PID"

echo
echo "Stopped. Press Return to close this window."
read -r
