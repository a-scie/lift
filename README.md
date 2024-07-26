# A scie lift

[![GitHub](https://img.shields.io/github/license/a-scie/lift)](LICENSE)
[![Github Actions CI (x86_64 Linux / MacOS / Windows)](https://github.com/a-scie/lift/actions/workflows/ci.yml/badge.svg)](https://github.com/a-scie/lift/actions/workflows/ci.yml)

Delivers `science`, a high level tool to build scies with.

The `science` tool is intended to be the primary tool used by applications to build scies. Although
the [`scie-jump`](https://github.com/a-scie/jump) provides everything needed to build a scie, it is
low-level and will always have some sharp corners, including its JSON lift manifest format.

The `science` binary is itself a scie built with `science` using the application manifest at
[lift.toml](lift.toml).

## Installing

You'll need to download the correct binary for your system, mark it as executable and place it on
your $PATH somewhere.

The binaries are released via [GitHub Releases](https://github.com/a-scie/lift/releases)
for Windows x86_64 and Linux and macOS for both aarch64 and x86_64. For each of these platforms
there are two varieties, "thin" and "fat". The "fat" varieties are named `science-fat-*`, include
a hermetic CPython 3.12 distribution from the [Python Build Standalone]() project and are larger as
a result. The "thin" varieties have the CPython 3.12 distribution gouged out and are smaller as a
result. In its place a [`ptex`](https://github.com/a-scie/ptex) binary is included that fills in the
CPython 3.12 distribution by fetching it when the "thin" `science` binary is first run.

I run on Linux x86_64; so I install a stable release like so:
```
curl -fLO \
  https://github.com/a-scie/lift/releases/download/v0.1.0/science-linux-x86_64
curl -fL \
  https://github.com/a-scie/lift/releases/download/v0.1.0/science-linux-x86_64.sha256 \
  | sha256sum -c -
chmod +x science-linux-x86_64 && mv science-linux-x86_64 ~/bin/science
```

The high level documentation is currently thin! The command line help is pretty decent though; so
try there 1st starting with just running `science` with no arguments.

If you'd like to build you own version, see the [contribution guide](CONTRIBUTING.md). There are
build instructions there.

## Contribute

See the [contribution guide](CONTRIBUTING.md) if you're interested in hacking on `science` or
improving its documentation.
