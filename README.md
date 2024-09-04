# A scie lift

[![GitHub](https://img.shields.io/github/license/a-scie/lift)](LICENSE)
[![Github Actions CI](https://github.com/a-scie/lift/actions/workflows/ci.yml/badge.svg)](https://github.com/a-scie/lift/actions/workflows/ci.yml)
[![Discord](https://img.shields.io/discord/1113502044922322954)](https://scie.app/discord)

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
for Windows, Linux and macOS for both aarch64 and x86-64. For each of these platforms
there are two varieties, "thin" and "fat". The "fat" varieties are named `science-fat-*`, include
a hermetic CPython 3.12 distribution from the [Python Build Standalone]() project and are larger as
a result. The "thin" varieties have the CPython 3.12 distribution gouged out and are smaller as a
result. In its place a [`ptex`](https://github.com/a-scie/ptex) binary is included that fills in the
CPython 3.12 distribution by fetching it when the "thin" `science` binary is first run.

You can install the latest `science` release using the `install.sh` script like so:

```
$ curl -LSsf https://raw.githubusercontent.com/a-scie/lift/main/install.sh | bash
...
$ ~/bin/science -V
```

The high level documentation is currently thin! The command line help is pretty decent though; so
try there 1st starting with just running `science` with no arguments.

If you'd like to build you own version, see the [contribution guide](CONTRIBUTING.md). There are
build instructions there.

## Contribute

See the [contribution guide](CONTRIBUTING.md) if you're interested in hacking on `science` or
improving its documentation.
