# Release Notes

## 0.10.2

This release brings two fixes for `science` on Windows:
+ Previously the default `science` cache location was
  `%USERPROFILE%\AppData\Local\science\science\Cache`. The redundant `science` subdirectory is now
  removed, resulting in a default of `%USERPROFILE%\AppData\Local\science\Cache`.
+ The intra-site links in the local docs served via `science doc open` now work. Previously they
  mistakenly contained `\` in some URL path components causing deep links to return to the home
  page.

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
