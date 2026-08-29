#!/usr/bin/env bash
# Deploy Montra from images already on Docker Hub.
#
# Pulls and runs; never builds. That is the point of pushing images — the
# artifact that was tested is the artifact that runs, and the host does not
# need the source, a toolchain, or the patience for a Next.js build.
#
#   ./scripts/deploy.sh                   # the version in version.py
#   ./scripts/deploy.sh 0.5.0             # an explicit version
#   ./scripts/deploy.sh latest            # the moving tag
#
# Overridable: DOCKERHUB_USER, ENV_FILE, PROJECT.
#
# ENV_FILE defaults to UAT. For production, ENV_FILE=.env.production
# PROJECT=montra ./scripts/deploy.sh — the two stacks run side by side under
# different project names, so getting this wrong deploys into the wrong one.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

DOCKERHUB_USER="${DOCKERHUB_USER:-corecrest}"
ENV_FILE="${ENV_FILE:-.env.uat}"
PROJECT="${PROJECT:-montra-uat}"

VERSION="${1:-$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' backend/app/core/version.py)}"
if [ -z "$VERSION" ]; then
  echo "could not read APP_VERSION from backend/app/core/version.py" >&2
  exit 1
fi

# --env-file is not optional. Without it compose interpolates this file from
# the default .env, which is the development one, and Postgres comes up with a
# different password from the one the API uses.
if [ ! -f "$ENV_FILE" ]; then
  echo "$ENV_FILE not found. Copy .env.uat.example and fill it in." >&2
  exit 1
fi

# Points every service at the registry instead of the locally built tag. The
# compose file defaults these to montra-api:prod / montra-web:prod, so `make
# uat` still builds locally and is unaffected by anything here.
export MONTRA_API_IMAGE="$DOCKERHUB_USER/montra-api:$VERSION"
export MONTRA_WEB_IMAGE="$DOCKERHUB_USER/montra-web:$VERSION"

COMPOSE=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f docker-compose.prod.yml)
PORT="$(sed -n 's/^PROXY_PORT=\(.*\)$/\1/p' "$ENV_FILE" | tail -1)"
PORT="${PORT:-8080}"

echo "==> Deploying $VERSION to $PROJECT (env $ENV_FILE, port $PORT)"
echo "    $MONTRA_API_IMAGE"
echo "    $MONTRA_WEB_IMAGE"

echo ""
echo "--- Pulling ---"
"${COMPOSE[@]}" pull

echo ""
echo "--- Starting ---"
# --no-build so a missing image fails loudly rather than being built here from
# whatever the working tree happens to contain. The migrate job runs first and
# the API waits on it, so the schema is never behind the code.
"${COMPOSE[@]}" up -d --no-build

# nginx resolves its upstreams once at startup. Replaced containers get new
# addresses, so without this the proxy keeps talking to the old ones until it
# gives up.
"${COMPOSE[@]}" restart proxy

echo ""
echo "--- Waiting for the API ---"
for _ in $(seq 60); do
  if curl -sf "localhost:$PORT/api/v1/health/live" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -sf "localhost:$PORT/api/v1/health/live" >/dev/null 2>&1; then
  echo "the API did not come up within 120s" >&2
  "${COMPOSE[@]}" ps
  exit 1
fi

# The version the app reports comes from the API image. Checking it here is
# what catches a half-deploy: the stack is up, but some service is still on
# the previous image and the app misreports what it is running.
served="$(curl -s "localhost:$PORT/api/v1/meta")"
echo "    $served"

if [ "$VERSION" != "latest" ] && ! echo "$served" | grep -q "\"version\":\"$VERSION\""; then
  echo "" >&2
  echo "deployed $VERSION but the API reports something else — a service is" >&2
  echo "probably still on an older image" >&2
  "${COMPOSE[@]}" ps
  exit 1
fi

echo ""
echo "--- Status ---"
"${COMPOSE[@]}" ps

echo ""
echo "Done. Serving on port $PORT."
