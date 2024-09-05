#!/bin/bash
#
# A basic install wrapper for UNIX-based environments.
#

GITHUB_DOWNLOAD_BASE="https://github.com/a-scie/lift/releases/latest/download"
INSTALL_PREFIX="${HOME}/.local/bin"
INSTALL_DEST="${INSTALL_PREFIX}/science"

# Check if arch is available.
if ! command -v arch &> /dev/null; then
  echo "Error: arch command not found. Please install arch and try again." >&2
  exit 1
fi

# Map platform architecture to released binary architecture.
READ_ARCH="$(arch)"
case "$READ_ARCH" in
  x86_64*)   ARCH="x86_64" ;;
  amd64*)    ARCH="x86_64" ;;
  arm64*)    ARCH="aarch64" ;;
  aarch64*)  ARCH="aarch64" ;;
  *)        echo "unknown arch: $(READ_ARCH)"; exit 1 ;;
esac

# Map OS name to released binary OS names and platform-specific SHA checker invocation.
case "$OSTYPE" in
  darwin*)  OS="macos" SHASUM_TOOL="shasum" SHASUM_CMD="${SHASUM_TOOL} -a 256 -c -" ;;
  linux*)   OS="linux" SHASUM_TOOL="sha256sum" SHASUM_CMD="${SHASUM_TOOL} -c -" ;;
  msys*)    OS="windows" SHASUM_TOOL="sha256sum" SHASUM_CMD="${SHASUM_TOOL} -c -" ;;
  *)        echo "unsupported platform: ${OSTYPE}, please download manually from https://github.com/a-scie/lift/releases/"; exit 1 ;;
esac

# Check if a sha sum checking tool is available.
if ! command -v "${SHASUM_TOOL}" &> /dev/null; then
  echo "Error: ${SHASUM_TOOL} command not found. Please install ${SHASUM_TOOL} and try again." >&2
  exit 1
fi

# Check if curl is available.
if ! command -v curl &> /dev/null; then
  echo "Error: curl command not found. Please install curl and try again." >&2
  exit 1
fi

DL_FILE="science-fat-${OS}-${ARCH}"
DL_URL="${GITHUB_DOWNLOAD_BASE}/${DL_FILE}"
SHA_URL="${DL_URL}.sha256"

echo "Download URL is: ${DL_URL}"
echo "Checksum URL is: ${SHA_URL}"

echo "Ensuring ${INSTALL_PREFIX}"
mkdir -p "${INSTALL_PREFIX}"

curl -fLO --progress-bar "$DL_URL" && \
  curl -fL --progress-bar "$SHA_URL" | ${SHASUM_CMD} && \
  chmod +x "$DL_FILE" && \
  mv -v "$DL_FILE" "${INSTALL_DEST}"

echo "Installed ${DL_FILE} to ${INSTALL_DEST} - please ensure that ${INSTALL_PREFIX} is on your \$PATH"
