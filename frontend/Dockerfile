# ---- Stage 1: build the React app with Node ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ---- Stage 2: serve the static files with an unprivileged Nginx ----
FROM nginxinc/nginx-unprivileged:1.29-alpine
# Patch the base image's Alpine packages: without this Trivy reports HIGH CVEs (curl, c-ares, ...).
USER root
RUN apk upgrade --no-cache
ENV BACKEND_URL=http://backend:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
# The base image already runs as the non-root "nginx" user (uid 101) on port 8080.
USER 101
EXPOSE 8080
