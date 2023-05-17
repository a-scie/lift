# Contributing

The `science` tool is intended to be the primary tool used by applications to build scies. Although
the [`scie-jump`](https://github.com/a-scie/jump) provides everything needed to build a scie, it is
low-level and will always have some sharp corners, including its JSON lift manifest format.

Probably the most important ease-of-life improvement of `science` over direct `scie-jump` use is its
support of [provider](science/providers) plugins that know how to include appropriate interpreter
distributions to power the scie. If you know a particular interpreter ecosystem well and would like
to add `science` support for it, that would be wonderful.

Thank you in advance for your time and effort.

## Development Environment

You'll need just a few tools to hack on the scie-jump:
+ A Python 3.11 interpreter
+ The [`nox`](https://nox.thea.codes/en/stable/) tool.

## Development Cycle

You might want to open a [discussion](https://github.com/a-scie/lift/discussions) or [issue](
https://github.com/a-scie/lift/issues) to vet your idea first. It can often save overall effort and
lead to a better end result.

Before sending off changes you should run `nox`. This formats, lints, typecheck and tests the code.

To test changes to the `science` binary you can either use `nox -e run -- <args>` or else run \
`nox -e package` and test the resulting science binaries in `dist/`. Four files will be produced
there:
1. The science "thin" binary: `science-<os>-<arch>(.<ext>)`
2. The science "thin" binary fingerprint file: `science-<os>-<arch>(.<ext>).sha256`
3. The science "fat" binary: `science-fat-<os>-<arch>(.<ext>)`
4. The science "fat" binary fingerprint file: `science-fat-<os>-<arch>(.<ext>).sha256`

When you're ready to get additional eyes on your changes, submit a [pull request](
https://github.com/a-scie/lift/pulls).
