#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r services/decision_api/requirements.txt
pip install -r services/rag_service/requirements.txt
pip install -r ml/training/requirements.txt
pip install pytest ruff

echo "Bootstrap complete. Activate with: source .venv/bin/activate"
