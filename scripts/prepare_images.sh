#!/usr/bin/env bash
# Build the two Montra images and tag them for Docker Hub.
#
# Montra ships two images, not three: montra-api runs the API, the migrate
# job, the Celery worker and the scheduler — same image, four commands — and
# montra-web runs Next.js. Everything else in the stack (Postgres, Redis,
# MinIO, nginx) is an unmodified upstream image and is pulled, never built.
#
# The build goes through compose rather than `docker build` so there is one
# definition of how an image is made. The frontend in particular takes a build
# arg (NEXT_PUBLIC_API_BASE_URL, inlined into the bundle) and both images build
# a specific stage; duplicating that here would drift the moment the compose
# file changed.
#
#   ./scripts/prepare_images.sh            # tag with the version in version.py
#   ./scripts/prepare_images.sh 0.5.0      # tag with an explicit version
#
# Overridable: DOCKERHUB_USER, ENV_FILE, PROJECT.
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

if [ ! -f "$ENV_FILE" ]; then
  echo "$ENV_FILE not found. Copy .env.uat.example and fill it in." >&2
  exit 1
fi

API_IMAGE="$DOCKERHUB_USER/montra-api"
WEB_IMAGE="$DOCKERHUB_USER/montra-web"

echo "==> Building montra-api and montra-web at $VERSION"
# Only api and web: migrate, worker and scheduler share the API image, so
# building them again would build the same thing three more times.
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f docker-compose.prod.yml \
  build api web

echo ""
echo "==> Tagging for Docker Hub"
for pair in "montra-api:prod $API_IMAGE" "montra-web:prod $WEB_IMAGE"; do
  set -- $pair
  docker tag "$1" "$2:$VERSION"
  docker tag "$1" "$2:latest"
  echo "    $2:$VERSION"
  echo "    $2:latest"
done

echo ""
echo "==> Built"
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}' \
  | grep -E "^($API_IMAGE|$WEB_IMAGE|montra-(api|web)):" || true

echo ""
echo "Next: ./scripts/push_images.sh $VERSION"
