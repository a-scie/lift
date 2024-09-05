#!/bin/bash
#
# A basic install wrapper for UNIX-based systems.
#

GITHUB_CHANGES_FILE="https://raw.githubusercontent.com/a-scie/lift/main/CHANGES.md"
GITHUB_DOWNLOAD_BASE="https://github.com/a-scie/lift/releases/latest/download"

# Check if curl is available.
if ! command -v curl &> /dev/null; then
  echo "Error: curl command not found. Please install curl and try again." >&2
  exit 1
fi

# Check if arch is available.
if ! command -v arch &> /dev/null; then
  echo "Error: arch command not found. Please install arch and try again." >&2
  exit 1
fi

# Map platform architecture to released binary architecture.
READ_ARCH="$(arch)"
case "$READ_ARCH" in
  x86_64*)   ARCH="x86_64" ;;
  arm64*)    ARCH="aarch64" ;;
  aarch64*)  ARCH="aarch64" ;;
  *)        echo "unknown arch: $(READ_ARCH)"; exit 1 ;;
esac

# Map OS name to released binary OS names and platform-specific SHA checker invocation.
case "$OSTYPE" in
  darwin*)  OS="macos" SHASUM_CMD="shasum -a 256 -c -" ;;
  linux*)   OS="linux" SHASUM_CMD="sha256sum -c -" ;;
  *)        echo "unknown platform: ${OSTYPE}"; exit 1 ;;
esac

DL_FILE="science-fat-${OS}-${ARCH}"
DL_URL="${GITHUB_DOWNLOAD_BASE}/${DL_FILE}"
SHA_URL="${DL_URL}.sha256"

echo "Download URL is: ${DL_URL}"
echo "Checksum URL is: ${SHA_URL}"

curl -fLO --progress-bar "$DL_URL" && \
  curl -fL --progress-bar "$SHA_URL" | ${SHASUM_CMD} && \
  chmod +x "$DL_FILE" && \
  mv -v "$DL_FILE" ~/bin/science
