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
  command -v "$cmd" > /dev/null || die "This script requires the ${cmd} binary to be on \$PATH."
}

_GC=()

ensure_cmd rm
function gc() {
  if (($# > 0)); then
    _GC+=("$@")
  else
    # Check $_GC validity to avoid "unbound variable" warnings if gc w/ arguments is never called.
    if ! [ ${#_GC[@]} -eq 0 ]; then
      rm -rf "${_GC[@]}"
    fi
  fi
}

trap gc EXIT

ensure_cmd uname
function determine_os() {
  local os

  os="$(uname -s)"
  if [[ "${os}" =~ [Ll]inux ]]; then
    echo linux
  elif [[ "${os}" =~ [Dd]arwin ]]; then
    echo macos
  elif [[ "${os}" =~ [Ww]in|[Mm][Ii][Nn][Gg] ]]; then
    # Powershell reports something like: Windows_NT
    # Git bash reports something like: MINGW64_NT-10.0-22621
    echo windows
  else
    die "Science is not supported on this OS (${os}). Please reach out at https://github.com/a-scie/lift/issues for help."
  fi
}

OS="$(determine_os)"

ensure_cmd arch
function determine_arch() {
  # Map platform architecture to released binary architecture.
  read_arch="$(arch)"
  case "$read_arch" in
    x86_64*)   echo "x86_64" ;;
    amd64*)    echo "x86_64" ;;
    arm64*)    echo "aarch64" ;;
    aarch64*)  echo "aarch64" ;;
    *)        die "unknown arch: $(read_arch)" ;;
  esac
}

ensure_cmd basename
ensure_cmd $([[ "${OS}" == "windows" ]] && echo "pwsh" || echo "curl")
function fetch() {
  local url="$1"
  local dest_dir="$2"

  local dest
  dest="${dest_dir}/$(basename "${url}")"

  if [[ "${OS}" == "windows" ]]; then
    pwsh -c "Invoke-WebRequest -OutFile ${dest} -Uri ${url}"
  else
    curl --proto '=https' --tlsv1.2 -sSfL -o "${dest}" "${url}"
  fi
}

ensure_cmd $([[ "${OS}" == "macos" ]] && echo "shasum" || echo "sha256sum")
function sha256() {
  if [[ "${OS}" == "macos" ]]; then
    shasum --algorithm 256 "$@"
  else
    sha256sum "$@"
  fi
}

ensure_cmd mktemp
ensure_cmd install
function install_from_url() {
  local url="$1"
  local dest="$2"

  local workdir
  workdir="$(mktemp -d)"
  gc "${workdir}"

  fetch "${url}.sha256" "${workdir}"
  fetch "${url}" "${workdir}"
  (
    cd "${workdir}"
    sha256 -c --status ./*.sha256 ||
      die "Download from ${url} did not match the fingerprint at ${url}.sha256"
  )
  rm "${workdir}/"*.sha256
  if [[ "${OS}" == "macos" ]]; then
    mkdir -p "$(dirname "${dest}")"
    install -m 755 "${workdir}/"* "${dest}"
  else
    install -D -m 755 "${workdir}/"* "${dest}"
  fi
}

ensure_cmd cat
function usage() {
  cat << __EOF__
Usage: $0

Installs the \`science\` binary.

-h | --help: Print this help message.

-d | --bin-dir:
  The directory to install the science binary in, "~/.local/bin" by default.

-b | --base-name:
  The name to use for the science binary, "science" by default.

-V | --version:
  The version of the science binary to install, the latest version by default.
  The available versions can be seen at:
    https://github.com/a-scie/lift/releases

__EOF__
}

INSTALL_PREFIX="${HOME}/.local/bin"
INSTALL_FILE="science"
VERSION="latest/download"

# Parse arguments.
while (($# > 0)); do
  case "$1" in
    --help | -h)
      usage
      exit 0
      ;;
    --bin-dir | -d)
      INSTALL_PREFIX="$2"
      shift
      ;;
    --base-name | -b)
      INSTALL_FILE="$2"
      shift
      ;;
    --version | -V)
      VERSION="download/v${2}"
      shift
      ;;
    *)
      usage
      die "Unexpected argument: ${1}\n"
      ;;
  esac
  shift
done

ARCH="$(determine_arch)"
GITHUB_DOWNLOAD_BASE="https://github.com/a-scie/lift/releases/${VERSION}"
INSTALL_DEST="${INSTALL_PREFIX}/${INSTALL_FILE}"
DL_FILE="science-fat-${OS}-${ARCH}"
DL_URL="${GITHUB_DOWNLOAD_BASE}/${DL_FILE}"

green "Download URL is: ${DL_URL}"

log "Ensuring ${INSTALL_PREFIX}"
mkdir -p "${INSTALL_PREFIX}"

install_from_url "${DL_URL}" "${INSTALL_DEST}"
green "Installed ${DL_FILE} to ${INSTALL_DEST}"

# Warn if the install prefix is not on $PATH.
if ! [[ ":$PATH:" == *":${INSTALL_PREFIX}:"* ]]; then
  warn "WARNING: ${INSTALL_PREFIX} is not detected on \$PATH"
  warn "You'll either need to invoke ${INSTALL_DEST} explicitly or else add ${INSTALL_PREFIX} to your shell's PATH."
fi
