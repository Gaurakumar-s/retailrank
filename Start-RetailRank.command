#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  retailrank_python="$PWD/.venv/bin/python"
elif [ -x ../../work/retailrank-venv/bin/python ]; then
  retailrank_python="$PWD/../../work/retailrank-venv/bin/python"
else
  echo "Please complete the Python environment setup in README.md first."
  exit 1
fi
export RETAILRANK_HOME="$PWD" OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2
echo "RetailRank: http://127.0.0.1:8002 — press Control-C to stop."
exec "$retailrank_python" -m uvicorn retailrank.api:app --host 127.0.0.1 --port "${PORT:-8002}"
