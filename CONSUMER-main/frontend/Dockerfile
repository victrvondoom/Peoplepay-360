# Build context is the repo root (see docker-compose.yml) so the layout
# mirrors local dev, since next.config.js's outputFileTracingRoot points at
# the monorepo root and nests the standalone build under frontend/.

FROM node:20-slim AS deps
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app/frontend
# NEXT_PUBLIC_* vars are inlined into the client bundle at build time, not
# read at container runtime -- must be passed as a build arg, not just a
# docker-compose `environment:` entry, or overriding it later has no effect.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
COPY --from=deps /app/frontend/node_modules ./node_modules
COPY frontend ./
RUN npm run build

FROM node:20-slim AS runner
# HOSTNAME=0.0.0.0 is required, not optional: Next.js's standalone server.js
# reads process.env.HOSTNAME to decide its bind address, and platforms like
# Render inject their own HOSTNAME env var (the container's internal DNS
# name) into every container. Without this override, the server binds to
# that internal hostname instead of all interfaces, and the platform's own
# external routing/load balancer can't reach it at all -- every request
# 502s even though the app is running and logs "Ready" with no errors.
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=builder /app/frontend/.next/standalone ./
COPY --from=builder /app/frontend/.next/static ./frontend/.next/static
COPY --from=builder /app/frontend/public ./frontend/public
EXPOSE 3000
CMD ["node", "frontend/server.js"]
