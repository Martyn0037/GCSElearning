# frontend/Dockerfile
# Builds the React app, then serves it from Caddy, which also reverse-proxies
# /api to the backend and terminates TLS. The Caddyfile comes from the
# "caddyfile" build context (infra/caddy), set in docker-compose.yml.

FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2-alpine AS runtime
COPY --from=build /web/dist /srv
COPY --from=caddyfile Caddyfile /etc/caddy/Caddyfile
