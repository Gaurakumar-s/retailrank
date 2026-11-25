FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml .
COPY src ./src
COPY web ./web
COPY artifacts ./artifacts
RUN pip install --no-deps -e . && useradd --create-home appuser && mkdir -p /app/runtime && chown appuser /app/runtime
USER appuser
ENV PORT=8000 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 RETAILRANK_HOME=/app
CMD ["sh", "-c", "uvicorn retailrank.api:app --host 0.0.0.0 --port ${PORT}"]
