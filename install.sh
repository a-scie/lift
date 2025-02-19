#!/bin/sh
# Copyright 2024 Science project contributors.
# Licensed under the Apache License, Version 2.0 (see LICENSE).

set -eu

COLOR_RED="\e[31m"
COLOR_GREEN="\e[32m"
COLOR_YELLOW="\e[33m"
COLOR_RESET="\e[0m"

log() {
  printf "$@\n" >&2
}

die() {
  [ "$#" -gt 0 ] && log "${COLOR_RED}$*${COLOR_RESET}"
  exit 1
}

green() {
  [ "$#" -gt 0 ] && log "${COLOR_GREEN}$*${COLOR_RESET}"
}

warn() {
  [ "$#" -gt 0 ] && log "${COLOR_YELLOW}$*${COLOR_RESET}"
}

ensure_cmd() {
  local cmd="$1"
  command -v "$cmd" > /dev/null || die "This script requires the ${cmd} binary to be on \$PATH."
}

ISSUES_URL="https://github.com/a-scie/lift/issues"
_GC=""

ensure_cmd rm
gc() {
  if [ "$#" -gt 0 ]; then
    _GC=" $@"
  else
    # Check if $_GC has members to avoid "unbound variable" warnings if gc w/ arguments is never
    # called.
    if [ -n "${_GC}" ]; then
      rm -rf "${_GC}"
    fi
  fi
}

trap gc EXIT

ensure_cmd uname
determine_os() {
  local os

  os="$(uname -s)"
  if echo "${os}" | grep -E "[Ll]inux" >/dev/null; then
    echo linux
  elif echo "${os}" | grep -E "[Dd]arwin" >/dev/null; then
    echo macos
  elif echo "${os}" | grep -E "[Ww]indow|[Mm][Ii][Nn][Gg]" >/dev/null; then
    # Powershell reports something like: Windows_NT
    # Git bash reports something like: MINGW64_NT-10.0-22621
    echo windows
  else
    die "Science is not supported on this OS (${os}). Please reach out at ${ISSUES_URL} for help."
  fi
}

OS="$(determine_os)"

determine_variant() {
  if [ "${OS}" = "linux" ] && ldd /bin/sh 2>/dev/null | grep musl >/dev/null; then
    echo "musl-"
  else
    echo ""
  fi
}

determine_arch() {
  # Map platform architecture to released binary architecture.
  read_arch="$(uname -m)"
  case "$read_arch" in
    x86_64*)   echo "x86_64" ;;
    amd64*)    echo "x86_64" ;;
    arm64*)    echo "aarch64" ;;
    aarch64*)  echo "aarch64" ;;
    armv7l*)   echo "armv7l" ;;
    armv8l*)   echo "armv7l" ;;
    s390x*)    echo "s390x" ;;
    ppc64le*)  echo "powerpc64" ;;
    *)         die "unknown arch: ${read_arch}" ;;
  esac
}

ensure_cmd basename
ensure_cmd curl
fetch() {
  local url="$1"
  local dest_dir="$2"

  local dest
  dest="${dest_dir}/$(basename "${url}")"

  # N.B. Curl is included on Windows 10+:
  #   https://devblogs.microsoft.com/commandline/tar-and-curl-come-to-windows/
  curl --proto '=https' --tlsv1.2 -SfL --progress-bar -o "${dest}" "${url}"
}

ensure_cmd $([ "${OS}" = "macos" ] && echo "shasum" || echo "sha256sum")
sha256() {
  if [ "${OS}" = "macos" ]; then
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
install_from_url() {
  local url="$1"
  local dest="$2"

  local workdir
  workdir="$(mktemp -d)"
  gc "${workdir}"

  fetch "${url}.sha256" "${workdir}"
  fetch "${url}" "${workdir}" && green "Download completed successfully"
  (
    cd "${workdir}"

    if [ "${OS}" = "windows" ]; then
      # N.B. Windows sha256sum is sensitive to trailing \r in files.
      cat *.sha256 | tr -d "\r" > out.sanitized
      mv -f out.sanitized *.sha256
    fi

    sha256 -c ./*.sha256 >/dev/null &&
      green "Download matched it's expected sha256 fingerprint, proceeding" ||
        die "Download from ${url} did not match the fingerprint at ${url}.sha256"
  )
  rm "${workdir}/"*.sha256

  if [ "${OS}" = "macos" ]; then
    mkdir -p "$(dirname "${dest}")"
    install -m 755 "${workdir}/"* "${dest}"
  else
    install -D -m 755 "${workdir}/"* "${dest}"
  fi

  green "Installed ${url} to ${dest}"
}

ensure_cmd cat
usage() {
  cat << __EOF__
Usage: $0

Installs the \`science\` binary.

-h | --help: Print this help message.

-d | --bin-dir:
  The directory to install the science binary in, "~/.local/bin" by default.

-V | --version:
  The version of the science binary to install, the latest version by default.
  The available versions can be seen at:
    https://github.com/a-scie/lift/releases

__EOF__
}

INSTALL_PREFIX="${HOME}/.local/bin"
VERSION="latest/download"

# Parse arguments.
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help | -h)
      usage
      exit 0
      ;;
    --bin-dir | -d)
      INSTALL_PREFIX="$2"
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
VARIANT="$(determine_variant)"
DIRSEP=$([ "${OS}" = "windows" ] && echo "\\" || echo "/")
EXE_EXT=$([ "${OS}" = "windows" ] && echo ".exe" || echo "")

INSTALL_DEST="${INSTALL_PREFIX}${DIRSEP}science${EXE_EXT}"
DL_URL="https://github.com/a-scie/lift/releases/${VERSION}/science-fat-${VARIANT}${OS}-${ARCH}${EXE_EXT}"

green "Download URL is: ${DL_URL}"
install_from_url "${DL_URL}" "${INSTALL_DEST}"

# Warn if the install prefix is not on $PATH.
if ! echo ":$PATH:" | grep ":${INSTALL_PREFIX}:" >/dev/null; then
  warn "WARNING: ${INSTALL_PREFIX} is not detected on \$PATH"
  warn "You'll either need to invoke ${INSTALL_DEST} explicitly or else add ${INSTALL_PREFIX} \
to your shell's PATH."
fi
