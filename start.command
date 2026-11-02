#!/bin/bash
# Double-click this file on a Mac to start Sayable.
# The first run sets everything up, which takes a few minutes.
set -e
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Sayable needs Python 3.10 or newer."
  echo "Install it from https://www.python.org/downloads/ and double-click this file again."
  read -r -p "Press Return to close this window." _
  exit 1
fi

if [ ! -d .venv ]; then
  echo "First run: creating a private Python environment in .venv"
  "$PYTHON" -m venv .venv
fi
source .venv/bin/activate

# Install packages on the first run, and again whenever requirements.txt changes
if [ ! -f .venv/.installed ] || ! cmp -s requirements.txt .venv/.installed; then
  echo "Installing packages…"
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  python manage.py migrate --noinput --verbosity 0
  python manage.py prepare_speech ||
    echo "The speech model could not be downloaded now. It will be tried again at your first recording."
  cp requirements.txt .venv/.installed
fi
python manage.py migrate --noinput --verbosity 0

PORT="${SAYABLE_PORT:-8000}"
echo
echo "Sayable is running at http://127.0.0.1:$PORT"
echo "Keep this window open while you use it. Close it to stop Sayable."
echo
( sleep 2 && open "http://127.0.0.1:$PORT" ) &
python manage.py runserver "127.0.0.1:$PORT" --noreload
