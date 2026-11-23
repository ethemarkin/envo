#!/bin/sh
# Builds envo for the common platforms into cli/dist. Each platform gets a zip
# named after it (envo-linux-amd64.zip, envo-windows-amd64.zip, ...) holding a
# single binary called envo (envo.exe on Windows), plus SHA256SUMS of the zips.
#
#   VERSION=0.5.0 sh cli/scripts/build-release.sh
#
# Limit the platforms with TARGETS, e.g. TARGETS="darwin/arm64 darwin/amd64".
#
# Without a local Go toolchain:
#   docker run --rm -v "$PWD/cli:/src" -w /src -e VERSION=0.5.0 golang:1.26 sh scripts/build-release.sh
#
# Publish the files from cli/dist somewhere your CI can download them and set
# ENVO_CLI_URL to that location (see examples/ci).
set -eu

cd "$(dirname "$0")/.."
VERSION="${VERSION:-dev}"
TARGETS="${TARGETS:-linux/amd64 linux/arm64 darwin/amd64 darwin/arm64 windows/amd64}"
OUT=dist
WORK="$OUT/.work"
rm -rf "$OUT"
mkdir -p "$WORK"

go build -o "$WORK/zipdist" ./scripts/zipdist

for target in $TARGETS; do
  os="${target%/*}"
  arch="${target#*/}"
  bin=envo
  [ "$os" = windows ] && bin=envo.exe
  echo "building envo-$os-$arch.zip"
  mkdir -p "$WORK/$os-$arch"
  CGO_ENABLED=0 GOOS="$os" GOARCH="$arch" go build -trimpath \
    -ldflags "-s -w -X envo/cli/internal/commands.Version=$VERSION" \
    -o "$WORK/$os-$arch/$bin" ./cmd/envo
  "$WORK/zipdist" "$OUT/envo-$os-$arch.zip" "$WORK/$os-$arch/$bin"
done

rm -rf "$WORK"
(cd "$OUT" && sha256sum envo-*.zip > SHA256SUMS)
echo "done: $(ls "$OUT" | wc -l) files in cli/$OUT"
