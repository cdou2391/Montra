# syntax=docker/dockerfile:1

# --------------------------------------------------------------------- deps
FROM node:22-slim AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
# Pinned, and kept current: the package manager ships its own dependencies into
# the image, and 10.33 carried a critical in its bundled tar that no
# project-level audit would ever see.
RUN corepack prepare pnpm@10.34.5 --activate && pnpm install --frozen-lockfile

# ---------------------------------------------------------------------- dev
# The source is bind-mounted over /app, so this needs the dependency tree and
# the dev server and nothing else.
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

# ------------------------------------------------------------------ builder
FROM deps AS builder
# Inlined into the bundle at build time rather than read at runtime, so it has
# to be present here. Relative on purpose: the client then calls whatever
# origin served it, and one image works behind any hostname.
ARG NEXT_PUBLIC_API_BASE_URL=/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
COPY . .
RUN pnpm build

# ------------------------------------------------------------------- runner
# Next's standalone output carries the server and only the modules it actually
# reached, so the runtime has no package manager and no node_modules tree —
# which is what the container scan kept finding.
FROM node:22-slim AS runner
# npm comes with the base image and is never used here — the server starts with
# plain node. Every advisory the scan reported against this image was inside
# npm's own bundled dependencies, so it goes. The upgrade picks up Debian
# security updates published since the base was last rebuilt.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
