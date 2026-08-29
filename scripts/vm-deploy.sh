#!/usr/bin/env bash
# Pull Montra from Docker Hub and run it. For a VM or any host that has no
# copy of the source.
#
# Put this file next to docker-compose.prod.yml in the deploy directory and
# run it from anywhere; it works on its own directory, not on the shell's.
#
#   ./vm-deploy.sh              # :latest
#   ./vm-deploy.sh 0.4.14       # a pinned version — prefer this
#
# The deploy directory needs exactly four things:
#
#   vm-deploy.sh
#   docker-compose.prod.yml
#   infra/nginx/montra.conf
#   .env.production             (or .env.uat — see ENV_FILE)
#
# No source, no toolchain, no repository. Everything else is an image.
#
# Overridable: DOCKERHUB_USER, ENV_FILE, PROJECT.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

DOCKERHUB_USER="${DOCKERHUB_USER:-corecrest}"
ENV_FILE="${ENV_FILE:-.env.production}"
PROJECT="${PROJECT:-montra}"
VERSION="${1:-latest}"

fail() { echo "$*" >&2; exit 1; }

echo "==> Preflight"

command -v docker >/dev/null 2>&1 || fail "docker is not installed."
docker compose version >/dev/null 2>&1 \
  || fail "the docker compose plugin is missing (docker-compose v1 will not do)."
docker info >/dev/null 2>&1 \
  || fail "cannot talk to the docker daemon — is it running, and is this user in the docker group?"

[ -f docker-compose.prod.yml ] || fail "docker-compose.prod.yml is not in $here"
[ -f infra/nginx/montra.conf ] \
  || fail "infra/nginx/montra.conf is not in $here — the proxy bind-mounts it and will not start without it."
[ -f "$ENV_FILE" ] || fail "$ENV_FILE is not in $here. Copy .env.uat.example from the repo and fill it in."

# Compose reads env_file: ${MONTRA_ENV_FILE} to pass settings *into* the
# containers, separately from --env-file which fills in ${...} in the compose
# file itself. They must name the same file; when they disagree the stack comes
# up with half its configuration missing.
#
# Unset is fine — the compose file defaults to .env.production — so this only
# has something to say when the two actually contradict each other.
declared="$(sed -n 's/^MONTRA_ENV_FILE=\(.*\)$/\1/p' "$ENV_FILE" | tail -1)"
if [ -n "$declared" ]; then
  [ "$declared" = "$ENV_FILE" ] \
    || fail "$ENV_FILE sets MONTRA_ENV_FILE=$declared. It must name itself: MONTRA_ENV_FILE=$ENV_FILE"
elif [ "$ENV_FILE" != ".env.production" ]; then
  fail "$ENV_FILE does not set MONTRA_ENV_FILE, and the compose default is .env.production.
Add this line to $ENV_FILE:  MONTRA_ENV_FILE=$ENV_FILE"
fi

for key in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL REDIS_URL \
           SECRET_KEY S3_ACCESS_KEY S3_SECRET_KEY S3_PUBLIC_ENDPOINT_URL \
           CORS_ORIGINS SAME_ORIGINS MONTRA_ENV; do
  grep -qE "^$key=.+" "$ENV_FILE" || fail "$ENV_FILE is missing $key (or leaves it empty)."
done

# The public hostname has to be the one the browser actually uses. Attachments
# are signed for it, and an S3 signature covers the host — point this at
# localhost and uploads fail for everyone who is not sitting at the VM.
if grep -qE "^S3_PUBLIC_ENDPOINT_URL=https?://(localhost|127\.0\.0\.1)" "$ENV_FILE"; then
  echo "    warning: S3_PUBLIC_ENDPOINT_URL points at localhost. Attachments will"
  echo "             only work from the VM itself. Set it to the public URL."
fi

PORT="$(sed -n 's/^PROXY_PORT=\(.*\)$/\1/p' "$ENV_FILE" | tail -1)"
PORT="${PORT:-8080}"
MONTRA_ENV="$(sed -n 's/^MONTRA_ENV=\(.*\)$/\1/p' "$ENV_FILE" | tail -1)"

echo "    ok — $ENV_FILE, MONTRA_ENV=$MONTRA_ENV, port $PORT, project $PROJECT"

export MONTRA_API_IMAGE="$DOCKERHUB_USER/montra-api:$VERSION"
export MONTRA_WEB_IMAGE="$DOCKERHUB_USER/montra-web:$VERSION"

COMPOSE=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f docker-compose.prod.yml)

echo ""
echo "==> Pulling $VERSION"
echo "    $MONTRA_API_IMAGE"
echo "    $MONTRA_WEB_IMAGE"
"${COMPOSE[@]}" pull

echo ""
echo "==> Starting"
# --no-build: there is no source here to build from, so a missing image must
# fail rather than send compose looking for a build context.
"${COMPOSE[@]}" up -d --no-build

# nginx resolves its upstreams once, at startup. Replaced containers get new
# addresses, so without this the proxy keeps talking to the old ones.
"${COMPOSE[@]}" restart proxy

echo ""
echo "==> Waiting for the API"
for _ in $(seq 60); do
  curl -sf "localhost:$PORT/api/v1/health/live" >/dev/null 2>&1 && break
  sleep 2
done
curl -sf "localhost:$PORT/api/v1/health/live" >/dev/null 2>&1 || {
  echo "the API did not come up within 120s" >&2
  "${COMPOSE[@]}" ps
  "${COMPOSE[@]}" logs --tail 40 api migrate
  exit 1
}

# The version comes from the API image. Checking it catches a half-deploy: the
# stack is up, but something is still on the previous image.
served="$(curl -s "localhost:$PORT/api/v1/meta")"
echo "    $served"
if [ "$VERSION" != "latest" ] && ! echo "$served" | grep -q "\"version\":\"$VERSION\""; then
  echo "" >&2
  echo "asked for $VERSION but the API reports something else — a service is" >&2
  echo "probably still running an older image." >&2
  "${COMPOSE[@]}" ps
  exit 1
fi

echo ""
"${COMPOSE[@]}" ps

echo ""
echo "Serving on port $PORT."
if [ "$MONTRA_ENV" = "production" ]; then
  echo "MONTRA_ENV=production: cookies are Secure and HSTS is on, so this must be"
  echo "reached over HTTPS. Terminate TLS in front of it — a tunnel, or a proxy"
  echo "with a certificate. Plain http://<vm-ip>:$PORT will not let you sign in."
fi
