#!/usr/bin/env bash
# Builds release artifacts:
#   - per-skill zips  -> for claude.ai / Claude Desktop (chat) skill upload
#   - per-plugin zips -> for Cowork / Claude Desktop "Personal plugins" upload
# Usage: scripts/build-zips.sh <version>
set -euo pipefail
VERSION="${1:?usage: build-zips.sh <version>}"
ROOT="$(pwd)"; DIST="$ROOT/dist"
rm -rf "$DIST" && mkdir -p "$DIST"
shopt -s nullglob

for d in plugins/*/skills/*/; do
  name=$(basename "$d"); parent=$(dirname "$d")
  ( cd "$parent" && zip -rq "$DIST/${name}-v${VERSION}.zip" "$name" )
  echo "built ${name}-v${VERSION}.zip"
done

for p in plugins/*/; do
  name=$(basename "$p")
  ( cd plugins && zip -rq "$DIST/${name}-plugin-v${VERSION}.zip" "$name" )
  echo "built ${name}-plugin-v${VERSION}.zip"
done
