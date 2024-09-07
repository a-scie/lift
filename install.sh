#!/usr/bin/env bash
# Copyright 2024 Science project contributors.
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

ISSUES_URL="https://github.com/a-scie/lift/issues"
_GC=()

ensure_cmd rm
function gc() {
  if (($# > 0)); then
    _GC+=("$@")
  else
    # Check if $_GC has members to avoid "unbound variable" warnings if gc w/ arguments is never called.
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
  elif [[ "${os}" =~ [Ww]indow|[Mm][Ii][Nn][Gg] ]]; then
    # Powershell reports something like: Windows_NT
    # Git bash reports something like: MINGW64_NT-10.0-22621
    echo windows
  else
    die "Science is not supported on this OS (${os}). Please reach out at ${ISSUES_URL} for help."
  fi
}

OS="$(determine_os)"

function determine_arch() {
  # Map platform architecture to released binary architecture.
  read_arch="$(uname -m)"
  case "$read_arch" in
    x86_64*)   echo "x86_64" ;;
    amd64*)    echo "x86_64" ;;
    arm64*)    echo "aarch64" ;;
    aarch64*)  echo "aarch64" ;;
    *)        die "unknown arch: ${read_arch}" ;;
  esac
}

ensure_cmd basename
ensure_cmd curl
function fetch() {
  local url="$1"
  local dest_dir="$2"

  local dest
  dest="${dest_dir}/$(basename "${url}")"

  # N.B. Curl is included on Windows 10+: https://devblogs.microsoft.com/commandline/tar-and-curl-come-to-windows/
  curl --proto '=https' --tlsv1.2 -SfL --progress-bar -o "${dest}" "${url}"
}

ensure_cmd $([[ "${OS}" == "macos" ]] && echo "shasum" || echo "sha256sum")
function sha256() {
  if [[ "${OS}" == "macos" ]]; then
    shasum --algorithm 256 "$@"
  else
    sha256sum "$@"
  fi
}

ensure_cmd dirname
ensure_cmd mktemp
ensure_cmd install
ensure_cmd tr
ensure_cmd mv
function install_from_url() {
  local url="$1"
  local dest="$2"

  local workdir
  workdir="$(mktemp -d)"
  gc "${workdir}"

  fetch "${url}.sha256" "${workdir}"
  fetch "${url}" "${workdir}" && green "Download completed successfully"
  (
    cd "${workdir}"

    if [[ "${OS}" == "windows" ]]; then
      # N.B. Windows sha256sum is sensitive to trailing \r in files.
      cat *.sha256 | tr -d "\r" > out.sanitized
      mv -f out.sanitized *.sha256
    fi

    sha256 -c --status ./*.sha256 &&
      green "Download matched it's expected sha256 fingerprint, proceeding" ||
        die "Download from ${url} did not match the fingerprint at ${url}.sha256"
  )
  rm "${workdir}/"*.sha256

  if [[ "${OS}" == "macos" ]]; then
    mkdir -p "$(dirname "${dest}")"
    install -m 755 "${workdir}/"* "${dest}"
  else
    install -D -m 755 "${workdir}/"* "${dest}"
  fi

  green "Installed ${url} to ${dest}"
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
DIRSEP=$([[ "${OS}" == "windows" ]] && echo "\\" || echo "/")
INSTALL_DEST="${INSTALL_PREFIX}${DIRSEP}${INSTALL_FILE}"
DL_EXT=$([[ "${OS}" == "windows" ]] && echo ".exe" || echo "")
DL_URL="https://github.com/a-scie/lift/releases/${VERSION}/science-fat-${OS}-${ARCH}${DL_EXT}"

green "Download URL is: ${DL_URL}"
install_from_url "${DL_URL}" "${INSTALL_DEST}"

# Warn if the install prefix is not on $PATH.
if ! [[ ":$PATH:" == *":${INSTALL_PREFIX}:"* ]]; then
  warn "WARNING: ${INSTALL_PREFIX} is not detected on \$PATH"
  warn "You'll either need to invoke ${INSTALL_DEST} explicitly or else add ${INSTALL_PREFIX} to your shell's PATH."
fi
