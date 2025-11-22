# Release Notes

## 0.15.3

This release fixes handling of the case of a scie with no files. These would build previously, but
then fail to run. This is a decidedly unlikely corner-case usage in the real world, but can be a
valid use.

## 0.15.2

This release fixes validation of custom `scie_jump`s with some portion of their digest filled out.
Now, if you specify a `size` or a `fingerprint` or both for the `lift.scie_jump.digest`, the
corresponding property of the downloaded `scie-jump` binary will be validated or else the scie
build will fail with an informative message.

## 0.15.1

This release fixes a bug present since the initial 0.1.0 release for `--hash shake_*`. The SHAKE
family of hash algorithms requires a length when obtaining a digest unlike all other Python
guaranteed hash algorithms. Previously, we did not pass a length, leading to failure when building a
scie; now we just drop support for these hash algorithms instead trusting someone will speak up when
they have a need for SHAKE.

## 0.15.0

This release adds support for all `*-full` flavor builds to the [PBS][PBS] provider. Notably, this
enables selecting free-threaded CPython builds. As a convenience, instead of specifying a `flavor`
to select a free-threaded CPython build, you can append a `t` suffix to the version; e.g.: `3.14t`
and the provider will select the appropriate free-threaded performance-optimized build for your
targeted platform.

## 0.14.0

This release adds support for CPython pre-releases to the [PBS][PBS] provider and upgrades the
science internal Python distribution to [PBS][PBS] CPython 3.13.9.

## 0.13.0

This release adds support for Linux riscv64 and upgrades the science internal Python distribution
to [PBS][PBS] CPython 3.13.7.

## 0.12.9

This release fixes the PythonBuildStandalone provider GitHub API usage when probing the latest
release.

## 0.12.8

This release fixes the PythonBuildStandalone provider to avoid making API calls for Python versions
it knows are not supported.

## 0.12.7

Unreleased.

## 0.12.6

Unreleased.

## 0.12.5

Unreleased.

## 0.12.4

This release fixes building Unix scies on Windows. Previously, the unix scie would contain
interpreter provider paths joined using the Windows `\` separator instead of `/`.

## 0.12.3

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.11.

## 0.12.2

This release fixes a long standing bug in plumbing `SCIENCE_AUTH_<normalized_host>_BEARER` env var
based bearer token auth through to http(s) requests to the host.

## 0.12.1

This release fixes science to support scies where the scie name matches one of the lift file names.

## 0.12.0

This release adds support for targeting musl libc systems and dogfoods this to ship a `science`
scie for 64 bit musl Linux.

## 0.11.3

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.9.

## 0.11.2

This release fixes a bug introduced in the 0.11.0 release whereby a `ptex` binary was always
included in each built scie even when the scie did not use `ptex`. This was functionally harmless
but did bloat the size of the resulting scie binary by ~5MB.

## 0.11.1

This release brings two fixes for `science` on Windows:
+ Previously the default `science` cache location was
  `%USERPROFILE%\AppData\Local\science\science\Cache`. The redundant `science` subdirectory is now
  removed, resulting in a default of `%USERPROFILE%\AppData\Local\science\Cache`.
+ The intra-site links in the local docs served via `science doc open` now work. Previously they
  mistakenly contained `\` in some URL path components causing deep links to return to the home
  page.

## 0.11.0

This release brings a new `science download` family of commands for downloading `ptex` binaries,
`scie-jump` binaries and provider distributions for offline use. To complement this, the
corresponding lift manifest configuration tables now accept a `base_url` option to point to the
location of these offline downloads.

## 0.10.1

This release fixes `science` to retry failed HTTP(S) fetches when appropriate.

## 0.10.0

This release adds support for Linux powerpc64le and Linux s390x.

## 0.9.0

This release adds support for Linux ARM (armv7l and armv8l 32 bit mode).

## 0.8.2

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.8.

## 0.8.1

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.7.

## 0.8.0

Add support for `--no-use-platform-suffix` as a complement to `--use-platform-suffix`. Without
specifying either, auto-disambiguation is still used to add a platform suffix whenever the
set of target platforms is not just the current platform, but you can also now force a platform
suffix to never be used by specifying `--no-use-platform-suffix`.

## 0.7.1

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.6.

## 0.7.0

This release adds support for Windows ARM64. 

> [!NOTE]
> The `science` binaries shipped for Windows ARM64 are powered by an x86-64 [PBS][PBS] CPython
> that runs under Windows Prism emulation for x86-64 binaries. As such, you will experience a
> significantly slower first run when Prism populates its instruction translation caches.

## 0.6.1

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.5.

## 0.6.0

Add an interpreter provider for [PyPy](https://pypy.org/) that provides the distributions they
release at https://downloads.python.org/pypy/.

## 0.5.0

Add support to the PythonBuildStandalone interpreter provider for the new `install_only_stripped`
distribution flavor introduced in the [20240726 PBS release](
https://github.com/astral-sh/python-build-standalone/releases/tag/20240726) and use this flavor to
ship smaller science fat binaries.

## 0.4.3

Fix science URL fetching code to gracefully ignore a `~/.netrc` that is a directory when configuring
authentication for the fetch.

## 0.4.2

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.4.

## 0.4.1

This release fixes missing attestations for Linux ARM64 artifacts.

## 0.4.0

Update dependencies and configure releases to include artifact attestations in Sigstore.

## 0.3.4

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.3.

## 0.3.3

Fix `science doc open` to use a local documentation server. This works around all the problems
you encounter trying to get a documentation site to function like the production via file:// URLs.

## 0.3.2

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.2 and perform Mac
aarch64 releases on GitHub hosted runners.

## 0.3.1

Upgrade the science internal Python distribution to [PBS][PBS] CPython 3.12.1 and fix some docs.

## 0.3.0

The unrecognized lift manifest configuration data error message now includes suggestions when the
unrecognized configuration is likely a typo.

## 0.2.2

Unrecognized lift manifest configuration data now generates an informative error instead of
silently skipping the unrecognized configuration.

## 0.2.1

Fix command descriptions not being rendered in the JSON lift manifest of built scies.

## 0.2.0

Add support for specifying a custom base `nce` cache dir and upgrade the science internal Python
distribution to [PBS][PBS] CPython 3.11.5.

## 0.1.3

Update the science internal Python distribution to [PBS][PBS] CPython 3.11.4. This should make
`science` executable out of the box on more Linux distros.

## 0.1.2

This release brings two fixes prompted by [scie-pants](https://github.com/pantsbuild/scie-pants)
adoption of `science`:
+ Fix science binary url in build info when using `--include-provenance`.
+ Fix the generated JSON lift manifest to position the ptex file 1st instead of last so that the
  last file specified by the user can take the spot of the zip trailer.

## 0.1.1

Fix provenance (`science lift --include-provenance ...`) to include the correct download URL for
the science binary used to build the scie.

## 0.1.0

The 1st public release of the project.

[PBS]: https://github.com/astral-sh/python-build-standalone/
