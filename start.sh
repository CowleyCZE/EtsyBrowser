#!/usr/bin/env bash
# Spusti GUI jednim prikazem:  bash start.sh
# Pri prvnim spusteni vytvori virtualni prostredi a nainstaluje zavislosti.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Vytvarim virtualni prostredi (.venv)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f .venv/.deps_installed ] || [ requirements.txt -nt .venv/.deps_installed ]; then
  echo "Instaluji zavislosti..."
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  touch .venv/.deps_installed
fi

exec python -m gui
