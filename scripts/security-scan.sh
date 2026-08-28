#!/usr/bin/env bash
# Dependency and container scanning (Implementation Plan Phase 29).
#
# Run before a release and after any dependency bump. Advisory, not a gate:
# wiring it into CI so a new advisory fails the build belongs with Phase 34.
#
# Trivy runs as a container against a saved image tarball rather than being
# installed on the host and handed the Docker socket. It needs no host package,
# behaves the same in CI, and a scanner does not need the ability to control
# every container on the machine.
set -uo pipefail

CACHE="${TRIVY_CACHE:-/tmp/trivy-cache}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$CACHE"

echo "== Version =="
"$(dirname "$0")/check-version.sh"

echo
echo "== Python dependencies (pip-audit) =="
docker compose exec -T api pip-audit --progress-spinner off

echo
echo "== Node dependencies (pnpm audit) =="
docker compose run --rm -T --no-deps web pnpm audit --audit-level moderate

echo
echo "== Container images (trivy) =="
# A stale base is the usual reason an image scan lights up: the OS packages
# baked in months ago have moved on. Refresh before scanning so the report is
# about the images rather than about how long since they were rebuilt.
echo "-- refreshing base images"
docker pull -q python:3.12-slim >/dev/null
docker pull -q node:22-slim >/dev/null

# The production images are what ships, so they are what a scan is about. The
# development ones are listed too because they are what runs on this machine.
for image in montra-api:prod montra-web:prod montra-api:latest montra-web:latest; do
  echo "-- $image"
  docker save "$image" -o "$TMP/image.tar" 2>/dev/null || {
    echo "   not built; run: docker compose build   (or, for :prod)"
    echo "   docker compose --env-file .env.production -f docker-compose.prod.yml build"
    continue
  }
  docker run --rm \
    -v "$TMP/image.tar:/image.tar:ro" \
    -v "$CACHE:/root/.cache" \
    aquasec/trivy:latest image \
      --input /image.tar \
      --severity HIGH,CRITICAL \
      --ignore-unfixed \
      --scanners vuln \
      --quiet
  rm -f "$TMP/image.tar"
done

echo
echo "The :prod images should report nothing. They are multi-stage: the runtime"
echo "carries the built virtualenv or the Next standalone server and no package"
echo "manager, which is where every finding used to live. They also apply the"
echo "Debian security updates published since their base was last rebuilt."
echo
echo "The :latest images are the development ones. They ship pip, pnpm and the"
echo "test tooling on purpose, so findings inside those are expected there."
