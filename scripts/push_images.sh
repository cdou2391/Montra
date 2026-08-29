#!/usr/bin/env bash
# Push the two Montra images to Docker Hub.
#
# Pushes only — prepare_images.sh does the building, so there is one place
# where an image is made and one place where it is published.
#
#   ./scripts/push_images.sh              # the version in version.py
#   ./scripts/push_images.sh 0.5.0        # an explicit version
#
# Overridable: DOCKERHUB_USER.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

DOCKERHUB_USER="${DOCKERHUB_USER:-corecrest}"

VERSION="${1:-$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' backend/app/core/version.py)}"
if [ -z "$VERSION" ]; then
  echo "could not read APP_VERSION from backend/app/core/version.py" >&2
  exit 1
fi

API_IMAGE="$DOCKERHUB_USER/montra-api"
WEB_IMAGE="$DOCKERHUB_USER/montra-web"

# A published image serves its own version at /api/v1/meta and shows it in App
# settings. Pushing while version.py, the changelog and package.json disagree
# ships an image that misreports itself, and it cannot be corrected in place —
# the tag is already out there. Cheaper to stop here.
echo "==> Checking the version is consistent"
./scripts/check-version.sh

# The images must already exist. Building here as a fallback would mean two
# code paths that can produce a differently-built image under the same tag.
echo ""
echo "==> Checking the images are built"
missing=0
for tag in "$API_IMAGE:$VERSION" "$WEB_IMAGE:$VERSION"; do
  if ! docker image inspect "$tag" >/dev/null 2>&1; then
    echo "    missing: $tag" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "" >&2
  echo "Run: ./scripts/prepare_images.sh $VERSION" >&2
  exit 1
fi

# `docker login` with credentials already stored authenticates without
# prompting, so calling it is close to free. Without a terminal it cannot
# prompt at all, so skip it there and let the push report the auth failure.
if [ -t 0 ]; then
  echo ""
  echo "==> Docker Hub login"
  docker login
fi

echo ""
echo "==> Pushing as :$VERSION and :latest"
for image in "$API_IMAGE" "$WEB_IMAGE"; do
  docker push "$image:$VERSION"
  docker push "$image:latest"
done

echo ""
echo "Pushed:"
for image in "$API_IMAGE" "$WEB_IMAGE"; do
  echo "  $image:$VERSION"
  echo "  $image:latest"
done
echo ""
echo "Next: ./scripts/deploy.sh $VERSION"
