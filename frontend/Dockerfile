# syntax=docker/dockerfile:1
#
# ResearchConnect AI — web frontend image (Phase 6.1).
#
# Build context: frontend/. Every API call is made from the browser, so the API address is
# compiled into the client bundle at build time: NEXT_PUBLIC_API_URL is a build argument,
# and changing it means rebuilding the image.

ARG NODE_IMAGE=node:24.13.1-bookworm-slim

# ── Dependencies, including the dev tooling the build needs ───────────────────
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ── Build ─────────────────────────────────────────────────────────────────────
FROM ${NODE_IMAGE} AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# The address the *browser* uses to reach the API. NEXT_PUBLIC_* values are shipped to
# every visitor, so this must never carry a secret.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
# NEXT_OUTPUT=standalone makes next.config.ts emit a self-contained server that carries
# only the dependencies it actually uses.
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_OUTPUT=standalone \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Runtime: the standalone server and its traced dependencies only ───────────
FROM ${NODE_IMAGE} AS runtime
WORKDIR /app

# HOSTNAME=0.0.0.0 makes the server listen on the container interface, not just loopback.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

# The base image's unprivileged `node` user.
USER node

EXPOSE 3000

CMD ["node", "server.js"]
