# syntax=docker/dockerfile:1.7
#
#   development — Vite dev server with hot reload
#   production  — static bundle served by an unprivileged nginx

# =============================================================================
FROM node:26-alpine AS deps
# =============================================================================

WORKDIR /app
ENV CI=true

# Only the manifests, so the (slow) install layer is reused whenever source
# changes but dependencies do not. `npm ci` requires the lockfile and installs
# exactly what it pins — never resolving fresh versions during a build.
COPY package.json package-lock.json ./
RUN npm ci

# =============================================================================
FROM deps AS development
# =============================================================================

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# =============================================================================
FROM deps AS build
# =============================================================================

COPY . .
# Baked in at build time: Vite inlines VITE_* values into the bundle.
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ARG VITE_WS_URL=ws://localhost:8000/api/v1/ws
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_WS_URL=${VITE_WS_URL}
RUN npm run build

# =============================================================================
FROM nginxinc/nginx-unprivileged:1.27-alpine AS production
# =============================================================================

# This image already runs as uid 101; nothing in the container runs as root.
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
