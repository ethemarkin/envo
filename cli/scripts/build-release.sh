#!/bin/sh
# Builds envo for the common platforms into cli/dist with SHA256SUMS.
#
#   VERSION=0.5.0 sh cli/scripts/build-release.sh
#
# Without a local Go toolchain:
#   docker run --rm -v "$PWD/cli:/src" -w /src -e VERSION=0.5.0 golang:1.26 sh scripts/build-release.sh
#
# Publish the files from cli/dist somewhere your CI can download them and set
# ENVO_CLI_URL to that location (see examples/ci).
set -eu

cd "$(dirname "$0")/.."
VERSION="${VERSION:-dev}"
OUT=dist
rm -rf "$OUT"
mkdir -p "$OUT"

for target in linux/amd64 linux/arm64 darwin/amd64 darwin/arm64 windows/amd64; do
  os="${target%/*}"
  arch="${target#*/}"
  name="envo-$os-$arch"
  [ "$os" = windows ] && name="$name.exe"
  echo "building $name"
  CGO_ENABLED=0 GOOS="$os" GOARCH="$arch" go build -trimpath \
    -ldflags "-s -w -X envo/cli/internal/commands.Version=$VERSION" \
    -o "$OUT/$name" ./cmd/envo
done

(cd "$OUT" && sha256sum envo-* > SHA256SUMS)
echo "done: $(ls "$OUT" | wc -l) files in cli/$OUT"
