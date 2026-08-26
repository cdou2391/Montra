#!/usr/bin/env bash
# Dependency and container scanning (Implementation Plan Phase 29).
#
# Run before a release and after any dependency bump. Both scanners are
# advisory: they report, they do not gate. Wiring them into CI so a new
# advisory fails the build belongs with the rest of Phase 34.
set -uo pipefail

echo "== Python dependencies (pip-audit) =="
docker compose exec -T api pip-audit --progress-spinner off
python_status=$?

echo
echo "== Node dependencies (pnpm audit) =="
docker compose run --rm -T --no-deps web pnpm audit --audit-level moderate
node_status=$?

echo
echo "== Container images (trivy) =="
if command -v trivy >/dev/null 2>&1; then
  for image in montra-api montra-web; do
    echo "-- $image"
    trivy image --severity HIGH,CRITICAL --ignore-unfixed "$image"
  done
else
  echo "trivy is not installed; skipping."
  echo "Install: https://aquasecurity.github.io/trivy/"
fi

echo
echo "python=$python_status node=$node_status"
