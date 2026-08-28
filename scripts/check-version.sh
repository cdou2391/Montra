#!/usr/bin/env bash
# The version and the changelog must agree.
#
# Runs on the host rather than as a pytest: only backend/ is mounted into the
# API container, so a test in there cannot see CHANGELOG.md and would pass
# without checking anything.
#
# It cannot know whether a feature shipped without a bump — nothing can — but
# it does stop the two from drifting once either one moves.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
version=$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' "$root/backend/app/core/version.py")

if [ -z "$version" ]; then
  echo "could not read APP_VERSION from backend/app/core/version.py" >&2
  exit 1
fi

fail=0

if ! grep -q "^## ${version}\$" "$root/CHANGELOG.md"; then
  echo "CHANGELOG.md has no '## ${version}' entry" >&2
  fail=1
fi

pkg=$(sed -n 's/^  "version": "\(.*\)",$/\1/p' "$root/frontend/package.json")
if [ "$pkg" != "$version" ]; then
  echo "frontend/package.json is $pkg, version.py is $version" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "version $version: changelog and package.json agree"
fi
exit "$fail"
