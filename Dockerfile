# ---------------------------------------------------------------------------
# Excel InsightForge Agent — production Dockerfile
# Build:  docker build -t appars/excel-insightforge-agent:latest .
# Run:    docker run -p 8501:8501 appars/excel-insightforge-agent:latest
# AI:     docker run -p 8501:8501 -e GROQ_API_KEY=gsk_xxx appars/excel-insightforge-agent:latest
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS base

# Security: run as non-root
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY config.py app.py ./
COPY services/ ./services/

RUN chown -R app:app /app
USER app

EXPOSE 8501

# Streamlit's built-in health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
  "--server.port=8501", \
  "--server.address=0.0.0.0", \
  "--server.headless=true", \
  "--browser.gatherUsageStats=false"]
