#!/usr/bin/env bash
# Copyright 2023 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

set -euo pipefail

COLOR_RED="\x1b[31m"
COLOR_GREEN="\x1b[32m"
COLOR_YELLOW="\x1b[33m"
COLOR_RESET="\x1b[0m"

function log() {
  echo -e "$@" 1>&2
}

function die() {
  (($# > 0)) && log "${COLOR_RED}$*${COLOR_RESET}"
  exit 1
}

function green() {
  (($# > 0)) && log "${COLOR_GREEN}$*${COLOR_RESET}"
}

function warn() {
  (($# > 0)) && log "${COLOR_YELLOW}$*${COLOR_RESET}"
}

function ensure_cmd() {
  local cmd="$1"
  command -v "$cmd" > /dev/null || die "This script requires the ${cmd} binary to be on the PATH."
}

GITHUB_DOWNLOAD_BASE="https://github.com/a-scie/lift/releases/latest/download"
INSTALL_PREFIX="${HOME}/.local/bin"
INSTALL_FILE="science"
INSTALL_DEST="${INSTALL_PREFIX}/${INSTALL_FILE}"

ensure_cmd arch

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

ensure_cmd "${SHASUM_TOOL}"
ensure_cmd curl

DL_FILE="science-fat-${OS}-${ARCH}"
DL_URL="${GITHUB_DOWNLOAD_BASE}/${DL_FILE}"
SHA_URL="${DL_URL}.sha256"

green "Download URL is: ${DL_URL}"
green "Checksum URL is: ${SHA_URL}"

log "Ensuring ${INSTALL_PREFIX}"
mkdir -p "${INSTALL_PREFIX}"

curl -fLO --progress-bar "$DL_URL" && \
  curl -fL --progress-bar "$SHA_URL" | ${SHASUM_CMD} && \
  chmod +x "$DL_FILE" && \
  mv -v "$DL_FILE" "${INSTALL_DEST}"

green "Installed ${DL_FILE} to ${INSTALL_DEST}"

# Warn if the install prefix is not on $PATH.
if ! [[ ":$PATH:" == *":${INSTALL_PREFIX}:"* ]]; then
  warn "WARNING: ${INSTALL_PREFIX} is not detected on \$PATH"
  warn "You'll either need to invoke ${INSTALL_DEST} explicitly or else add ${INSTALL_PREFIX} to your shell's PATH."
fi
