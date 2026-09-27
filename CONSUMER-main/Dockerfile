# Single-container build for platforms that only run one container per app
# (e.g. Hugging Face Spaces' Docker SDK). Runs the Next.js frontend on the
# externally exposed port and FastAPI internally on 127.0.0.1:$INTERNAL_API_PORT;
# next.config.js rewrites /api/v1/* from the frontend to the internal
# backend, so the browser only ever talks to one origin.
#
# For a real multi-container deployment (separate scaling, real Qdrant/
# Neo4j/Redis), use docker-compose.yml + backend/Dockerfile +
# frontend/Dockerfile instead -- this file is specifically for the
# one-container-one-port constraint.

# ---- backend deps ----
FROM python:3.12-slim AS backend-deps
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# ---- frontend deps ----
FROM node:20-slim AS frontend-deps
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# ---- frontend build ----
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
# Relative, not a full URL: the browser calls the same origin the page was
# served from, and next.config.js's rewrites() forwards /api/v1/* to the
# internal FastAPI process. NEXT_PUBLIC_* vars are inlined at build time.
ENV NEXT_PUBLIC_API_BASE_URL=/api/v1
COPY --from=frontend-deps /app/frontend/node_modules ./node_modules
COPY frontend ./
RUN npm run build

# ---- final runtime image ----
FROM python:3.12-slim AS runtime

# Node is needed to run the Next.js standalone server alongside the Python backend.
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ENVIRONMENT is deliberately left at its default ("development"), NOT set
# to "production" -- production mode hard-requires VECTOR_STORE_BACKEND=qdrant,
# GRAPH_STORE_BACKEND=neo4j, and a configured Supabase JWT secret for auth
# (app/core/startup.py, app/rag/retrieval/factory.py,
# app/knowledge_graph/factory.py all raise RuntimeError at boot otherwise).
# This deployment intentionally uses the JSONL fallback stores with no
# external Qdrant/Neo4j, and auth's "development" mode is what lets the
# app's existing device-id bearer tokens work without a real Supabase
# project configured -- setting ENVIRONMENT=production here would crash the
# app at startup and then break every request even if it somehow booted.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    VECTOR_STORE_BACKEND=jsonl \
    GRAPH_STORE_BACKEND=jsonl \
    INTERNAL_API_PORT=8000 \
    LLM_PROVIDER=nvidia

WORKDIR /app

# Backend: installed deps + source + the real data it reads at runtime.
COPY --from=backend-deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-deps /usr/local/bin /usr/local/bin
COPY backend /app/backend
COPY knowledge /app/knowledge

# Frontend: standalone server output only (already minimal/self-contained).
# .next/standalone's own contents already nest under a frontend/ folder
# (next.config.js sets outputFileTracingRoot to the monorepo root), so
# copying its CONTENTS into /app lands at /app/frontend/server.js -- copying
# it to /app/frontend instead would double-nest to /app/frontend/frontend/.
COPY --from=frontend-builder /app/frontend/.next/standalone /app
COPY --from=frontend-builder /app/frontend/.next/static /app/frontend/.next/static
COPY --from=frontend-builder /app/frontend/public /app/frontend/public

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Hugging Face Spaces (Docker SDK) expects the app to listen on 7860 by
# default. Overridable via the PORT env var for other one-container hosts.
ENV PORT=7860
EXPOSE 7860

CMD ["/app/start.sh"]
