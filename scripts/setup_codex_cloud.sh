#!/usr/bin/env bash
set -euo pipefail
python --version
python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
python scripts/check_release.py
