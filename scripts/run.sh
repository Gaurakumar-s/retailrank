#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
exec python -m uvicorn retailrank.api:app --host 127.0.0.1 --port "${PORT:-8002}"
