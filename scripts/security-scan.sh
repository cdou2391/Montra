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

for image in montra-api montra-web; do
  echo "-- $image"
  docker save "$image:latest" -o "$TMP/image.tar" 2>/dev/null || {
    echo "   image not built; run: docker compose build"
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
echo "Note: montra-web is a development image and ships a package manager, so"
echo "findings inside pnpm/npm are expected there. The production image built"
echo "in Phase 31 should be multi-stage and carry neither."
