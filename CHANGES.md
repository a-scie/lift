# Release Notes

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
