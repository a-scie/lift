# Release Notes

## 0.2.1

Fix command descriptions not being rendered in the JSON lift manifest of built scies.

## 0.2.0

Add support for specifying a custom base `nce` cache dir and upgrade the internal [PBS](
https://github.com/indygreg/python-build-standalone/) CPython 3.11.5.

## 0.1.3

Update the science internal Python distribution to [PBS](
https://github.com/indygreg/python-build-standalone/) CPython 3.11.4. This should make `science`
executable out of the box on more Linux distros.

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
